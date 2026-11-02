import unittest
from unittest.mock import patch

from cartridge_app import auth
from cartridge_app.__main__ import authorize


class AccessKeyTests(unittest.TestCase):
    def test_verifier_accepts_key_and_ignores_outer_whitespace(self):
        salt = b'test-access-salt'
        expected_key = 'test-only-key'
        with patch.object(auth, '_SALT', salt), patch.object(auth, '_ITERATIONS', 1200):
            expected_digest = auth.derive_key_digest(expected_key, salt)
            with patch.object(auth, '_EXPECTED', expected_digest):
                self.assertTrue(auth.verify_access_key('  test-only-key\n'))
                self.assertFalse(auth.verify_access_key('wrong-key'))

    def test_verifier_rejects_empty_non_text_and_oversized_values(self):
        self.assertFalse(auth.verify_access_key(''))
        self.assertFalse(auth.verify_access_key('  '))
        self.assertFalse(auth.verify_access_key(None))
        self.assertFalse(auth.verify_access_key('x' * 161))

    def test_cancelled_prompt_does_not_authenticate_or_show_error(self):
        with patch('cartridge_app.__main__.install_clipboard_shortcuts'), \
             patch('cartridge_app.__main__.simpledialog.askstring', return_value=None), \
             patch('cartridge_app.__main__.verify_access_key') as verify, \
             patch('cartridge_app.__main__.messagebox.showerror') as show_error:
            self.assertFalse(authorize(object()))
        verify.assert_not_called()
        show_error.assert_not_called()

    def test_invalid_key_is_rejected_with_feedback(self):
        with patch('cartridge_app.__main__.install_clipboard_shortcuts'), \
             patch('cartridge_app.__main__.simpledialog.askstring', return_value='invalid'), \
             patch('cartridge_app.__main__.verify_access_key', return_value=False), \
             patch('cartridge_app.__main__.messagebox.showerror') as show_error:
            self.assertFalse(authorize(object()))
        show_error.assert_called_once()

    def test_valid_key_opens_the_application(self):
        with patch('cartridge_app.__main__.install_clipboard_shortcuts'), \
             patch('cartridge_app.__main__.simpledialog.askstring', return_value='valid'), \
             patch('cartridge_app.__main__.verify_access_key', return_value=True), \
             patch('cartridge_app.__main__.messagebox.showerror') as show_error:
            self.assertTrue(authorize(object()))
        show_error.assert_not_called()


if __name__ == '__main__':
    unittest.main()
