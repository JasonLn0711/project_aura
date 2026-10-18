"""Private JSON-lines worker protocol; stdout is exclusively machine readable."""
import base64
import contextlib
import json
import sys
import traceback


def main():
    from aura.audio.reuse_model import ReuseModel
    from aura.audio.reuse_stream import StreamingEnhancer
    from aura.audio.reuse_offline import enhance_wav
    from aura.audio.reuse_policy import POLICIES, REFERENCE, SPEECH_GUARD, SourceSpeechProtection
    import numpy as np
    model = stream = None
    policy = REFERENCE
    evidence = SourceSpeechProtection()

    def predict(spectrum):
        if policy == REFERENCE:
            return model.predict(spectrum)
        center = stream.frames * stream.hop
        return model.predict(spectrum, protect_speech=evidence.protected(center - stream.hop, center + stream.hop))

    for line in sys.stdin:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                action = request['action']
                if action == 'load':
                    policy = request.get('live_policy', REFERENCE)
                    if policy not in POLICIES or (request['mode'] != 'live' and policy != REFERENCE):
                        raise ValueError('Unsupported RE-USE live policy')
                    model = ReuseModel(request['mode'], request['root'])
                    model.live_policy = policy
                    evidence = SourceSpeechProtection()
                    stream = StreamingEnhancer(predict) if request['mode'] == 'live' else None
                    result = {**model.receipt, 'live_policy': policy}
                elif action == 'push':
                    samples = np.frombuffer(base64.b64decode(request['pcm'], validate=True), '<i2').astype(np.float32) / 32768
                    if policy == SPEECH_GUARD:
                        evidence.push(len(samples), request.get('source_speech'))
                    output = stream.push(samples)
                    result = {'pcm': base64.b64encode((np.clip(output, -1, 32767 / 32768) * 32768).astype('<i2').tobytes()).decode(),
                              'diagnostics': getattr(model, 'diagnostics', {})}
                elif action == 'flush':
                    output = stream.flush()
                    result = {'pcm': base64.b64encode((np.clip(output, -1, 32767 / 32768) * 32768).astype('<i2').tobytes()).decode(),
                              'diagnostics': getattr(model, 'diagnostics', {})}
                elif action == 'reset':
                    if request.get('new_interval'):
                        if stream.received != stream.emitted or not stream.closed:
                            raise ValueError('Flush the preceding interval before starting another')
                    model.reset_stream()
                    if request.get('new_interval'):
                        evidence = SourceSpeechProtection()
                        stream = StreamingEnhancer(predict)
                    result = {'reset': True}
                elif action == 'file':
                    if model is None or model.mode != 'offline':
                        raise ValueError('Offline RE-USE must be loaded before file processing')
                    def progress(done, total):
                        print(json.dumps({'progress': {'completed_samples': done, 'total_samples': total}}), file=sys.__stdout__, flush=True)
                    path = enhance_wav(request['source'], request['target'], model.offline, progress)
                    result = {'path': str(path), **model.receipt}
                else:
                    raise ValueError('Unknown RE-USE operation')
            print(json.dumps({'ok': True, 'result': result}), flush=True)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({'ok': False, 'error': str(exc)}), flush=True)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
