"""Private JSONL worker. Run with the separately locked Nemotron interpreter."""
import json
import sys
import subprocess
from pathlib import Path

# Direct script execution deliberately avoids importing AURA's main environment.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from aura.diarization.nemotron import MODEL_ID, MODEL_REVISION, TRANSFORMERS_REVISION


class Engine:
    def __init__(self):
        import torch
        from transformers import AutoProcessor, AutoModelForAudioFrameClassification
        if not torch.cuda.is_available():
            raise RuntimeError('Nemotron requires CUDA; CPU fallback is disabled')
        torch.set_num_threads(2)
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION, local_files_only=True)
        self.processor.set_streaming_mode('low_latency')
        self.model = AutoModelForAudioFrameClassification.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, local_files_only=True, dtype=torch.float32).to('cuda').eval()
        self.source = self.decoder = None
        self.reset_state()
        import numpy as np
        # Warm up without retaining a synthetic speaker history.
        self.predict(np.zeros(self.processor.num_samples_first_audio_chunk, dtype=np.float32), False)
        self.reset_state()

    def reset_state(self):
        self.cache = None
        self.frame = 0
        self.buffer = bytearray()
        self.buffer_start = self.read_samples = 0
        self.done = False

    def close_source(self):
        if self.source:
            self.source.close()
            self.source = None
        if self.decoder:
            if self.decoder.poll() is None:
                self.decoder.terminate()
            try:
                self.decoder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.decoder.kill()
                self.decoder.wait()
            self.decoder = None

    def reset(self, path, media=False):
        self.close_source()
        self.reset_state()
        self.media = media
        path = Path(path)
        if media:
            if not path.is_file():
                raise ValueError('Source audio does not exist')
            self.decoder = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
                '-ar', '16000', '-ac', '1', '-f', 's16le', '-'], stdout=subprocess.PIPE, stderr=sys.stderr)
            self.source = self.decoder.stdout
        else:
            self.path = path
        return {'reset': True}

    def predict(self, samples, final):
        import numpy as np
        inputs = self.processor(samples, sampling_rate=16000, is_streaming=True,
            is_first_audio_chunk=self.frame == 0, is_last_audio_chunk=final, return_tensors='pt').to('cuda')
        with self.torch.inference_mode():
            output = self.model(**inputs, speaker_cache=self.cache)
        self.cache = output.speaker_cache
        logits = output.logits
        count = logits.shape[1]
        # Final padding may extend beyond the source; it must never extend timestamps.
        if final:
            count = min(count, max(0, (self.read_samples + 159) // 160 - self.frame))
            logits = logits[:, :count]
        turns = self.processor.extract_speaker_dict(logits)[0] if count else []
        offset = self.frame / 100
        end = min((self.frame + count) / 100, self.read_samples / 16000) if final else (self.frame + count) / 100
        result = [dict(start=round(t['Start'] + offset, 5), end=round(min(t['End'] + offset, end), 5),
                       speaker=f"SPEAKER_{t['Speaker']:02d}") for t in turns]
        result = [t for t in result if t['end'] > t['start']]
        active = [f'SPEAKER_{i:02d}' for i, x in enumerate((logits[0, -1].sigmoid() > .5).tolist()) if x] if count else []
        self.frame += count
        return dict(turns=result, active=active, processed_sample=min(self.frame * 160, self.read_samples), done=final)

    def advance(self, available=None, final=False):
        import numpy as np
        if self.done:
            return dict(turns=[], active=[], processed_sample=self.read_samples, done=True)
        p = self.processor
        start = 0 if self.frame == 0 else p.audio_chunk_start(self.frame)
        size = p.num_samples_first_audio_chunk if self.frame == 0 else p.num_samples_per_audio_chunk
        needed = start + size
        if self.media:
            raw = self.source.read(max(0, needed - self.read_samples) * 2)
            eof = len(raw) < max(0, needed - self.read_samples) * 2
            if eof and self.decoder.wait(timeout=10) != 0:
                raise RuntimeError('Audio decoder failed; source was preserved')
        else:
            if type(available) is not int or available < self.read_samples:
                raise ValueError('Available sample cursor must be monotonic')
            if not final and available < needed:
                return dict(turns=[], active=[], processed_sample=self.frame * 160, done=False, waiting=True)
            end = min(needed, available)
            if end > self.read_samples:
                with self.path.open('rb') as source:
                    source.seek(self.read_samples * 2)
                    raw = source.read((end - self.read_samples) * 2)
                if len(raw) != (end - self.read_samples) * 2:
                    raise RuntimeError('Published PCM interval is incomplete')
            else:
                raw = b''
            eof = final and available <= needed
        if len(raw) % 2:
            raise ValueError('Incomplete PCM sample')
        self.buffer.extend(raw)
        self.read_samples += len(raw) // 2
        if self.read_samples == 0 and eof:
            self.done = True
            return dict(turns=[], active=[], processed_sample=0, done=True)
        offset = max(0, start - self.buffer_start)
        samples = np.frombuffer(bytes(self.buffer[offset * 2:]), dtype='<i2').astype(np.float32) / 32768
        result = self.predict(samples, eof)
        self.done = eof
        if not eof:
            next_start = p.audio_chunk_start(self.frame)
            remove = next_start - self.buffer_start
            del self.buffer[:remove * 2]
            self.buffer_start = next_start
        return result


def main():
    engine = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
            command = request.pop('command')
            if command == 'load':
                engine = engine or Engine()
                result = dict(model_id=MODEL_ID, model_revision=MODEL_REVISION,
                    transformers_revision=TRANSFORMERS_REVISION, device='cuda', dtype='float32')
            elif command == 'reset':
                result = engine.reset(**request)
            elif command == 'advance':
                result = engine.advance(**request)
            else:
                raise ValueError('Unknown Nemotron command')
        except Exception as exc:
            import traceback
            traceback.print_exc(file=sys.stderr)
            result = {'error': f'{type(exc).__name__}: {exc}'}
        print(json.dumps(result), flush=True)
    if engine:
        engine.close_source()


if __name__ == '__main__':
    main()
