"""Offline voice assets, error IDs, mute behavior and serialized playback."""
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from cartridge_app.voice import VoicePlayer


ROOT = Path(__file__).resolve().parents[1]
VOICE_DIR = ROOT / 'cartridge-voices-grigory'


class QueueRoot:
    def __init__(self):
        self.destroy_handler = None

    def bind(self, sequence, handler, add=None):
        self.destroy_handler = handler

    def after_idle(self, callback):
        callback()


class DeferredBackend:
    def __init__(self):
        self.started = []
        self.completions = []
        self.stop_count = 0

    def play(self, path, finished):
        self.started.append(path.name)
        self.completions.append(finished)

    def stop(self):
        self.stop_count += 1


class VoiceTests(unittest.TestCase):
    def test_manifest_matches_all_local_audio_resources(self):
        manifest = json.loads((VOICE_DIR / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest), 8)
        for item in manifest:
            audio = VOICE_DIR / item['file']
            self.assertTrue(audio.is_file(), item['id'])
            self.assertEqual(audio.read_bytes()[:2], b'\xff\xfb')
            self.assertGreater(audio.stat().st_size, 1000)
            self.assertGreater(item['duration_seconds'], 0)

    def test_audio_assets_are_included_by_windows_build_command(self):
        script = (ROOT / 'build-windows.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('--add-data "cartridge-voices-grigory;cartridge-voices-grigory"', script)

    def test_messages_are_serialized_and_muting_stops_current_and_pending_audio(self):
        root = QueueRoot()
        backend = DeferredBackend()
        voice = VoicePlayer(root, directory=VOICE_DIR, backend=backend)
        voice.play('cartridge_not_found')
        voice.play('dispatch_not_ready')
        voice.play('arrival_not_at_refill')
        self.assertEqual(backend.started, ['cartridge_not_found.mp3'])
        backend.completions.pop(0)()
        self.assertEqual(backend.started, ['cartridge_not_found.mp3', 'dispatch_not_ready.mp3'])
        voice.set_enabled(False)
        self.assertEqual(backend.stop_count, 1)
        self.assertEqual(list(voice.queue), [])
        backend.completions.pop(0)()
        self.assertEqual(len(backend.started), 2)
        voice.play('arrival_not_at_refill')
        self.assertEqual(len(backend.started), 2)

    def test_unknown_code_and_missing_resource_are_silent(self):
        root = QueueRoot()
        backend = DeferredBackend()
        voice = VoicePlayer(root, directory=VOICE_DIR, backend=backend)
        voice.play('not-an-error-code')
        self.assertEqual(backend.started, [])
        voice.close()
        self.assertEqual(backend.stop_count, 1)


if __name__ == '__main__':
    unittest.main()
