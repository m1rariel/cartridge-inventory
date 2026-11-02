import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cartridge_app import __main__ as application


class StartupTests(unittest.TestCase):
    def test_application_opens_without_authorization_prompt(self):
        root = Mock()
        storage = Mock()
        service = object()
        with patch.object(application.tk, 'Tk', return_value=root), \
             patch.object(application, 'data_directory', return_value=Path('/temporary/app-data')), \
             patch.object(application, 'Storage', return_value=storage) as storage_factory, \
             patch.object(application, 'Service', return_value=service), \
             patch.object(application, 'App') as app_factory:
            application.main()

        storage_factory.assert_called_once_with(Path('/temporary/app-data') / 'inventory.sqlite3')
        app_factory.assert_called_once_with(root, service)
        root.deiconify.assert_called_once()
        root.mainloop.assert_called_once()
        storage.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
