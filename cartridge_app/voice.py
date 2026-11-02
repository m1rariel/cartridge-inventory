"""Offline playback for bundled Russian validation messages."""
from collections import deque
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def _resource_directory():
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        return Path(bundle) / 'cartridge-voices-grigory'
    return Path(__file__).resolve().parent.parent / 'cartridge-voices-grigory'


class _WindowsMCI:
    """Use the Windows multimedia subsystem; no player or package is installed."""
    alias = 'cartridgeVoice'

    def __init__(self, root):
        self.root = root
        self.dll = ctypes.WinDLL('winmm')
        self.send = self.dll.mciSendStringW
        self.send.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p)
        self.send.restype = ctypes.c_uint
        self.timer = None
        self.finished = None
        self.opened = False

    def _command(self, value, response=None):
        result = self.send(value, response, len(response) if response is not None else 0, None)
        if result:
            raise OSError(f'MCI error {result}')
        return response.value if response is not None else ''

    def play(self, path, finished):
        self.stop()
        self._command(f'open "{path}" type MPEGVideo alias {self.alias}')
        self.opened = True
        self.finished = finished
        try:
            self._command(f'play {self.alias}')
        except Exception:
            self.stop()
            raise
        self._poll()

    def _poll(self):
        try:
            state = self._command(f'status {self.alias} mode', ctypes.create_unicode_buffer(32))
            if state.casefold() == 'stopped':
                callback = self.finished
                self._close()
                if callback:
                    callback()
                return
            self.timer = self.root.after(100, self._poll)
        except Exception:
            callback = self.finished
            self._close()
            if callback:
                callback()

    def _close(self):
        if self.timer is not None:
            try:
                self.root.after_cancel(self.timer)
            except Exception:
                pass
            self.timer = None
        if self.opened:
            try:
                self._command(f'close {self.alias}')
            except Exception:
                pass
            self.opened = False
        self.finished = None

    def stop(self):
        if self.opened:
            try:
                self._command(f'stop {self.alias}')
            except Exception:
                pass
        self._close()


class _ProcessPlayer:
    """Small desktop-development fallback (afplay on macOS, ffplay on Linux)."""
    def __init__(self, root, executable, arguments):
        self.root, self.executable, self.arguments = root, executable, arguments
        self.process = None
        self.timer = None
        self.finished = None

    def play(self, path, finished):
        self.stop()
        self.process = subprocess.Popen(
            [self.executable, *self.arguments, str(path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=(os.name != 'nt'))
        self.finished = finished
        self._poll()

    def _poll(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.timer = self.root.after(100, self._poll)
            return
        callback = self.finished
        self.process = None
        self.finished = None
        self.timer = None
        if callback:
            callback()

    def stop(self):
        if self.timer is not None:
            try:
                self.root.after_cancel(self.timer)
            except Exception:
                pass
            self.timer = None
        process, self.process = self.process, None
        self.finished = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass


def _default_backend(root):
    try:
        if sys.platform == 'win32':
            return _WindowsMCI(root)
        if sys.platform == 'darwin':
            executable = shutil.which('afplay')
            return _ProcessPlayer(root, executable, []) if executable else None
        executable = shutil.which('ffplay')
        return _ProcessPlayer(root, executable, ['-nodisp', '-autoexit', '-loglevel', 'quiet']) if executable else None
    except Exception:
        return None


class VoicePlayer:
    """Serialize audio phrases and silently ignore all playback failures."""

    def __init__(self, root, enabled=True, directory=None, backend=None):
        self.root = root
        self.enabled = bool(enabled)
        self.directory = Path(directory) if directory else _resource_directory()
        self.backend = backend if backend is not None else _default_backend(root)
        self.queue = deque()
        self.current = None
        self._generation = 0
        self._closed = False
        try:
            manifest = json.loads((self.directory / 'manifest.json').read_text(encoding='utf-8'))
            self.files = {
                item['id']: item['file'] for item in manifest
                if isinstance(item, dict) and isinstance(item.get('id'), str)
                and isinstance(item.get('file'), str)
                and Path(item['file']).name == item['file']
                and Path(item['file']).suffix.lower() == '.mp3'
            }
        except Exception:
            self.files = {}
        try:
            root.bind('<Destroy>', self._on_destroy, add='+')
        except Exception:
            pass

    def _on_destroy(self, event):
        if getattr(event, 'widget', None) is self.root:
            self.close()

    def play(self, code):
        if self._closed or not self.enabled or self.backend is None:
            return
        filename = self.files.get(code)
        if not filename or not (self.directory / filename).is_file():
            return
        self.queue.append(code)
        if self.current is None:
            self._start_next()

    def _start_next(self):
        if self._closed or not self.enabled or self.backend is None or self.current is not None:
            return
        while self.queue:
            code = self.queue.popleft()
            filename = self.files.get(code)
            path = self.directory / filename if filename else None
            if path is None or not path.is_file():
                continue
            self.current = code
            generation = self._generation
            try:
                self.backend.play(path, lambda: self._finished(generation))
                return
            except Exception:
                self.current = None

    def _finished(self, generation):
        if generation != self._generation or self._closed:
            return
        self.current = None
        try:
            self.root.after_idle(self._start_next)
        except Exception:
            self.close()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            self.queue.clear()
            self.current = None
            self._generation += 1
            try:
                if self.backend:
                    self.backend.stop()
            except Exception:
                pass
        elif self.current is None:
            self._start_next()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.queue.clear()
        self.current = None
        self._generation += 1
        try:
            if self.backend:
                self.backend.stop()
        except Exception:
            pass
