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
    import numpy as np
    model = stream = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                action = request['action']
                if action == 'load':
                    model = ReuseModel(request['mode'], request['root'])
                    stream = StreamingEnhancer(model.predict) if request['mode'] == 'live' else None
                    result = model.receipt
                elif action == 'push':
                    samples = np.frombuffer(base64.b64decode(request['pcm'], validate=True), '<i2').astype(np.float32) / 32768
                    output = stream.push(samples)
                    result = {'pcm': base64.b64encode((np.clip(output, -1, 32767 / 32768) * 32768).astype('<i2').tobytes()).decode()}
                elif action == 'flush':
                    output = stream.flush()
                    result = {'pcm': base64.b64encode((np.clip(output, -1, 32767 / 32768) * 32768).astype('<i2').tobytes()).decode()}
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
