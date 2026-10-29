"""Independent settings acceptance checks, isolated from user's actual data."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cartridge_app.preferences import (
    PreferencesStore, Settings, color_contrast, contrast_warning,
    recommended_text_color,
)


class PreferencesAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.defaults = Settings(theme='light', language='ru')
        self.defaults_patch = patch('cartridge_app.preferences.default_settings', return_value=self.defaults)
        self.defaults_patch.start()
        self.store = PreferencesStore(self.root)

    def tearDown(self):
        self.defaults_patch.stop()
        self.temporary.cleanup()

    def test_missing_corrupt_and_unsupported_settings_use_defaults(self):
        self.assertEqual(self.store.load(), self.defaults)
        for raw in ('{bad json', 'null', '[]', '{"version":999,"settings":{"theme":"dark"}}'):
            with self.subTest(raw=raw):
                self.store.path.write_text(raw, encoding='utf-8')
                self.assertEqual(self.store.load(), self.defaults)
                self.assertEqual(self.store.path.read_text(encoding='utf-8'), raw)

    def test_invalid_loaded_fields_fallback_but_valid_fields_survive(self):
        self.store.path.write_text(json.dumps({'version': 1, 'settings': {
            'theme': 'dark', 'language': 'xx', 'font_size': True,
            'font_family': 'invented', 'accent_color': 'red',
            'text_color_light': '#ABCDEF', 'text_color_dark': '#xyzxyz',
            'background_mode': 'custom', 'background_filename': '../external.png',
            'background_overlay': 81,
        }}), encoding='utf-8')
        settings = self.store.load()
        self.assertEqual(settings.theme, 'dark')
        self.assertEqual(settings.language, self.defaults.language)
        self.assertEqual(settings.font_size, self.defaults.font_size)
        self.assertEqual(settings.font_family, self.defaults.font_family)
        self.assertEqual(settings.accent_color, self.defaults.accent_color)
        self.assertEqual(settings.text_color_light, '#abcdef')
        self.assertEqual(settings.text_color_dark, self.defaults.text_color_dark)
        self.assertEqual(settings.background_mode, 'default')
        self.assertIsNone(settings.background_filename)
        self.assertEqual(settings.background_overlay, self.defaults.background_overlay)

    def test_preferences_persist_after_new_store_and_reset_preserves_inventory(self):
        # Independent settings/reset must never modify any neighbouring business file.
        database = self.root / 'inventory.sqlite3'
        backup = self.root / 'backups' / 'copy.sqlite3'
        backup.parent.mkdir()
        database.write_bytes(b'inventory sentinel')
        backup.write_bytes(b'backup sentinel')
        values = dict(theme='dark', language='en', font_family='Arial', font_size=18,
                      accent_color='#123ABC', text_color_light='#112233',
                      text_color_dark='#eeeeee', background_mode='custom',
                      background_filename='photo.png', background_overlay=-25)
        changed = self.store.update(**values)
        self.assertEqual(changed.accent_color, '#123abc')
        self.assertEqual(PreferencesStore(self.root).load(), changed)
        self.assertEqual(self.store.reset(), self.defaults)
        self.assertEqual(PreferencesStore(self.root).load(), self.defaults)
        self.assertEqual(database.read_bytes(), b'inventory sentinel')
        self.assertEqual(backup.read_bytes(), b'backup sentinel')

    def test_bad_user_edits_do_not_write_or_change_current_settings(self):
        original = self.store.update(theme='dark')
        before = self.store.path.read_bytes()
        cases = [dict(font_size=8), dict(font_size=25), dict(font_size=True),
                 dict(background_overlay=-81), dict(background_overlay=81),
                 dict(background_overlay=False), dict(language='fr'), dict(theme='auto'),
                 dict(font_family='unknown'), dict(accent_color='#123'),
                 dict(text_color_light='white'), dict(text_color_dark=None),
                 dict(background_mode='unknown'), dict(unknown_setting=1)]
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.store.update(**values)
                self.assertEqual(self.store.settings, original)
                self.assertEqual(self.store.path.read_bytes(), before)

    def test_limits_are_inclusive(self):
        self.assertEqual(self.store.update(font_size=9, background_overlay=-80).font_size, 9)
        self.assertEqual(self.store.update(font_size=24, background_overlay=80).background_overlay, 80)

    def test_failed_replace_keeps_prior_file_and_memory_on_update_and_reset(self):
        before_settings = self.store.update(theme='dark', font_size=20)
        before_bytes = self.store.path.read_bytes()
        with patch('cartridge_app.preferences.os.replace', side_effect=OSError('simulated disk failure')):
            for operation in (lambda: self.store.update(language='en'), self.store.reset):
                with self.assertRaises(OSError):
                    operation()
                self.assertEqual(self.store.path.read_bytes(), before_bytes)
                self.assertEqual(self.store.settings, before_settings)
                self.assertEqual(list(self.root.glob('.preferences-*.tmp')), [])

    def test_contrast_known_values_and_recommended_colors(self):
        self.assertEqual(color_contrast('#000000', '#ffffff'), 21.0)
        self.assertEqual(color_contrast('#ffffff', '#000000'), 21.0)
        self.assertEqual(color_contrast('#ffffff', '#ffffff'), 1.0)
        self.assertTrue(contrast_warning('#eeeeee', '#ffffff'))
        self.assertFalse(contrast_warning('#000000', '#ffffff'))
        self.assertFalse(contrast_warning(recommended_text_color('light'), '#ffffff'))
        self.assertFalse(contrast_warning(recommended_text_color('dark'), '#162238'))
        with self.assertRaises(ValueError):
            color_contrast('red', '#ffffff')


from cartridge_app.image_store import ImageStore, ImageStoreError
try:
    from PIL import Image
except ImportError:
    Image = None


class SystemThemeAcceptanceTests(unittest.TestCase):
    def test_default_follows_system_and_explicit_theme_bypasses_probe(self):
        from cartridge_app.preferences import default_settings, effective_theme
        self.assertEqual(Settings().theme, 'system')
        with patch('cartridge_app.preferences.system_language', return_value='ru'):
            self.assertEqual(default_settings().theme, 'system')
        with patch('cartridge_app.preferences.system_theme', return_value='dark') as probe:
            self.assertEqual(effective_theme('system'), 'dark')
            probe.assert_called_once_with()
        with patch('cartridge_app.preferences.system_theme', return_value='dark') as probe:
            self.assertEqual(effective_theme('light'), 'light')
            self.assertEqual(effective_theme('dark'), 'dark')
            probe.assert_not_called()


class ImageStorageIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = ImageStore(self.root)
        self.store.directory.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temporary.cleanup()

    def test_reset_removes_only_managed_assets_and_not_inventory(self):
        database = self.root / 'inventory.sqlite3'
        preferences = self.root / 'preferences.json'
        unrelated = self.store.directory / 'unrelated.png'
        managed = self.store.directory / 'background-test.png'
        nested = self.store.directory / 'background-folder'
        nested.mkdir()
        for path in (database, preferences, unrelated, managed):
            path.write_bytes(b'keep')
        self.store.reset()
        self.assertFalse(managed.exists())
        for path in (database, preferences, unrelated):
            self.assertEqual(path.read_bytes(), b'keep')
        self.assertTrue(nested.is_dir())

    def test_remove_rejects_external_paths_and_unknown_names(self):
        outside = self.root / 'background-external.png'
        outside.write_bytes(b'keep')
        for path in ('../background-external.png', str(outside), 'missing.png'):
            with self.subTest(path=path), self.assertRaises(ImageStoreError):
                self.store.remove(path)
        self.assertEqual(outside.read_bytes(), b'keep')
        managed = self.store.directory / 'background-test.png'
        managed.write_bytes(b'image')
        self.store.remove(managed.name)
        self.assertFalse(managed.exists())

    def test_missing_pillow_is_a_user_readable_error_without_writing(self):
        with patch.dict('sys.modules', {'PIL': None}):
            with self.assertRaisesRegex(ImageStoreError, 'недоступна'):
                self.store.validate_and_save(self.root / 'sample.png')
        self.assertEqual(list(self.store.directory.iterdir()), [])


@unittest.skipIf(Image is None, 'Pillow отсутствует: проверка настоящего декодирования изображений недоступна')
class ImageDecodeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = ImageStore(self.root)
        self.store.directory.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temporary.cleanup()

    def create_image(self, fmt='PNG', size=(120, 80)):
        path = self.root / ('source.' + fmt.lower())
        with Image.new('RGB', size, '#345678') as image:
            image.save(path, format=fmt)
        return path

    def test_jpeg_png_and_webp_are_copied_then_load_without_original(self):
        for fmt in ('JPEG', 'PNG', 'WEBP'):
            with self.subTest(fmt=fmt):
                source = self.create_image(fmt)
                original_bytes = source.read_bytes()
                metadata = self.store.validate_and_save(source)
                filename = metadata['filename']
                stored = self.store.directory / filename
                self.assertEqual(stored.read_bytes(), original_bytes)
                self.assertEqual((metadata['width'], metadata['height']), (120, 80))
                source.unlink()
                with self.store.load_image(filename, (60, 60)) as loaded:
                    self.assertLessEqual(loaded.width, 60)
                    self.assertLessEqual(loaded.height, 60)
                    self.assertEqual(loaded.size, (60, 40))
                self.store.remove(filename)
                self.assertFalse(stored.exists())

    def test_corrupt_empty_and_unsupported_content_is_rejected(self):
        bad = self.root / 'bad.png'
        for content in (b'', b'not an image', b'\x89PNG\r\n\x1a\ntruncated'):
            bad.write_bytes(content)
            with self.subTest(content=content), self.assertRaises(ImageStoreError):
                self.store.validate_and_save(bad)
        with self.assertRaises(ImageStoreError):
            self.store.validate_and_save(self.create_image('GIF'))
        self.assertEqual(list(self.store.directory.iterdir()), [])

    def test_missing_file_is_rejected(self):
        with self.assertRaises(ImageStoreError):
            self.store.validate_and_save(self.root / 'missing.png')

    def test_file_size_dimension_and_pixel_limits(self):
        large = self.root / 'large.png'
        with large.open('wb') as stream:
            stream.truncate(10 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ImageStoreError, '10 МБ'):
            self.store.validate_and_save(large)
        with self.assertRaisesRegex(ImageStoreError, '6000'):
            self.store.validate_and_save(self.create_image(size=(6001, 1)))
        # Real decodable image; lower the configured pixel limit to avoid a large allocation.
        source = self.create_image(size=(120, 80))
        with patch('cartridge_app.image_store.MAX_PIXELS', 9000):
            with self.assertRaisesRegex(ImageStoreError, 'мегапикселя'):
                self.store.validate_and_save(source)
        self.assertEqual(list(self.store.directory.iterdir()), [])

    def test_failed_commit_keeps_source_and_cleans_temp(self):
        source = self.create_image()
        before = source.read_bytes()
        with patch('cartridge_app.image_store.os.replace', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):
                self.store.validate_and_save(source)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(list(self.store.directory.iterdir()), [])

    def test_invalid_thumbnail_bounds_are_rejected(self):
        metadata = self.store.validate_and_save(self.create_image())
        with self.assertRaises(ImageStoreError):
            self.store.load_image(metadata['filename'], (-1, 10))


class SettingsDialogCallbackTests(unittest.TestCase):
    def make_dialog(self):
        from unittest.mock import Mock
        from cartridge_app.settings_dialog import SettingsDialog
        dialog = SettingsDialog.__new__(SettingsDialog)
        dialog.app = Mock()
        dialog.app.language = 'ru'
        dialog.app.ask_confirmation.return_value = False
        dialog.window = None
        dialog.pending_background = None
        dialog.rebuild = Mock()
        return dialog

    def test_cancel_reset_does_not_change_preferences_or_assets(self):
        dialog = self.make_dialog()
        dialog.reset_settings()
        dialog.app.ask_confirmation.assert_called_once()
        dialog.app.reset_preferences.assert_not_called()
        dialog.app.image_store.reset.assert_not_called()

    def test_cancel_pending_image_removes_only_pending_asset(self):
        dialog = self.make_dialog()
        dialog.pending_background = {'filename': 'background-pending.png'}
        dialog.cancel_pending_background()
        dialog.app.image_store.remove.assert_called_once_with('background-pending.png')
        dialog.app.save_preferences.assert_not_called()
        self.assertIsNone(dialog.pending_background)
        dialog.rebuild.assert_called_once()

    def test_missing_old_background_does_not_delete_new_committed_asset(self):
        dialog = self.make_dialog()
        with tempfile.TemporaryDirectory() as temporary:
            image_store = ImageStore(temporary)
            image_store.directory.mkdir(parents=True, exist_ok=True)
            current = image_store.directory / 'background-new.png'
            current.write_bytes(b'already validated image')
            dialog.app.image_store = image_store
            preferences = PreferencesStore(temporary)
            dialog.app.settings = preferences.update(background_mode='custom', background_filename='background-missing.png')
            def save_preferences(**changes):
                dialog.app.settings = preferences.update(**changes)
                return True
            dialog.app.save_preferences.side_effect = save_preferences
            dialog.pending_background = {'filename': current.name}
            dialog.apply_pending_background()
            self.assertTrue(current.exists(), 'Successful new background must survive failed old-file cleanup')
            dialog.pending_background = {'filename': current.name}
            dialog.app.apply_background.side_effect = RuntimeError('simulated renderer failure after commit')
            dialog.apply_pending_background()
            self.assertTrue(current.exists(), 'A committed background must survive subsequent rendering errors')
            self.assertEqual(PreferencesStore(temporary).load().background_filename, current.name)

    def test_failed_preference_save_does_not_rebuild_dialog(self):
        dialog = self.make_dialog()
        dialog.app.save_preferences.return_value = False
        dialog._save(theme='dark')
        dialog.app.save_preferences.assert_called_once_with(theme='dark')
        dialog.rebuild.assert_not_called()


import os


@unittest.skipUnless(os.environ.get('RUN_GUI_TESTS') == '1', 'Настоящий Tk-сеанс недоступен; RUN_GUI_TESTS=1 включает проверку панели')
class SettingsRealTkTests(unittest.TestCase):
    def test_settings_panel_constructs_switches_theme_and_closes(self):
        import tkinter as tk
        from cartridge_app.service import Service
        from cartridge_app.storage import Storage
        from cartridge_app.ui import App
        from cartridge_app.settings_dialog import SettingsDialog
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            storage = Storage(directory / 'inventory.sqlite3')
            root = tk.Tk()
            try:
                with patch('cartridge_app.ui.data_directory', return_value=directory):
                    app = App(root, Service(storage), PreferencesStore(directory), ImageStore(directory))
                root.update()
                dialog = SettingsDialog(app)
                root.update()
                initial = app.settings.theme
                dialog.theme_button.invoke()
                root.update()
                self.assertNotEqual(app.settings.theme, initial)
                self.assertEqual(PreferencesStore(directory).load().theme, app.settings.theme)
                dialog.close()
                root.update()
                self.assertFalse(dialog.window.winfo_exists())
            finally:
                root.destroy()
                storage.close()
