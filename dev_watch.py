"""Restart the Windows development app when shared source files change."""
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / 'cartridge_app'
POLL_SECONDS = 0.4
STABLE_SECONDS = 0.8


def source_state():
    paths = [ROOT / 'run.py']
    if APP_DIR.exists():
        paths.extend(p for p in APP_DIR.rglob('*.py') if '__pycache__' not in p.parts)
    state = []
    for path in sorted(paths):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        state.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(state)


def start_app():
    print('Starting app from shared source files. Save a .py file to refresh the window.', flush=True)
    return subprocess.Popen([sys.executable, '-m', 'cartridge_app'], cwd=str(ROOT))


def stop_app(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main():
    print('Watching:', ROOT, flush=True)
    baseline = source_state()
    process = start_app()
    pending_state = None
    changed_at = None
    try:
        while True:
            time.sleep(POLL_SECONDS)
            if process.poll() is not None:
                print('App window closed. Watcher stopped.', flush=True)
                return process.returncode or 0
            current = source_state()
            if current == baseline:
                pending_state = None
                changed_at = None
                continue
            if current != pending_state:
                pending_state = current
                changed_at = time.monotonic()
                continue
            if time.monotonic() - changed_at >= STABLE_SECONDS:
                print('Source changed. Restarting app...', flush=True)
                stop_app(process)
                baseline = current
                process = start_app()
                pending_state = None
                changed_at = None
    except KeyboardInterrupt:
        print('\nStopping watcher.', flush=True)
        stop_app(process)
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
