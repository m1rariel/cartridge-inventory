import unittest

from cartridge_app.clipboard import shortcut_action


class ClipboardShortcutTests(unittest.TestCase):
    def test_russian_layout_shortcuts(self):
        self.assertEqual(shortcut_action('Cyrillic_es', platform='darwin'), 'copy')
        self.assertEqual(shortcut_action('Cyrillic_em', platform='darwin'), 'paste')
        self.assertEqual(shortcut_action('Cyrillic_che', platform='darwin'), 'cut')
        self.assertEqual(shortcut_action('Cyrillic_ef', platform='darwin'), 'select_all')

    def test_windows_virtual_key_shortcuts_ignore_current_layout(self):
        self.assertEqual(shortcut_action('Cyrillic_es', 67, 'win32'), 'copy')
        self.assertEqual(shortcut_action('Cyrillic_em', 86, 'win32'), 'paste')
        self.assertEqual(shortcut_action('Cyrillic_che', 88, 'win32'), 'cut')
        self.assertEqual(shortcut_action('Cyrillic_ef', 65, 'win32'), 'select_all')

    def test_other_shortcuts_are_left_for_tk_default_bindings(self):
        self.assertIsNone(shortcut_action('Cyrillic_ya', 81, 'win32'))
        self.assertIsNone(shortcut_action('Left', 37, 'win32'))


if __name__ == '__main__':
    unittest.main()
