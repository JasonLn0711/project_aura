"""One CUDA owner with bounded failure/shutdown, independent of capture control."""
import concurrent.futures
import multiprocessing
import os
import threading


def _run(pipe):
    from aura.session_runtime import execute
    try:
        while True:
            task = pipe.recv()
            if task is None:
                return
            kind, payload = task
            try:
                pipe.send((True, execute(kind, payload)))
            except Exception as exc:
                pipe.send((False, exc))
    except (EOFError, BrokenPipeError):
        pass
    finally:
        pipe.close()


class InferenceWorker:
    def __init__(self):
        context = multiprocessing.get_context('spawn')
        self.pipe, child = context.Pipe()
        self.process = context.Process(target=_run, args=(child,), name='aura-gpu-worker', daemon=True)
        self.process.start()
        child.close()
        self.closed = threading.Event()

    def submit(self, _function, kind, payload):
        future = concurrent.futures.Future()
        try:
            timeout = float(os.environ.get('AURA_WORKER_WATCHDOG_SECONDS', '300'))
            if not 0 < timeout <= 86400:
                raise ValueError('AURA_WORKER_WATCHDOG_SECONDS must be in (0, 86400]')
            self.pipe.send((kind, payload))
            import time
            deadline = time.monotonic() + timeout
            while not self.pipe.poll(.1):
                if self.closed.is_set() or not self.process.is_alive():
                    raise RuntimeError('Inference worker exited; retained audio can be recovered')
                if time.monotonic() >= deadline:
                    self.shutdown()
                    raise RuntimeError('Inference safety watchdog expired; retained audio can be recovered')
            success, value = self.pipe.recv()
            if success:
                future.set_result(value)
            else:
                future.set_exception(value)
        except (EOFError, BrokenPipeError, OSError) as exc:
            future.set_exception(RuntimeError(f'Inference worker connection failed: {exc}'))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def shutdown(self):
        if self.closed.is_set():
            return
        self.closed.set()
        try:
            self.pipe.send(None)
        except (OSError, EOFError):
            pass
        self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=2)
        self.pipe.close()
