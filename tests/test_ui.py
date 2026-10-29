"""Callback checks without display; opt-in real Tk smoke on supported desktops."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cartridge_app.service import Service
from cartridge_app.storage import Storage
from cartridge_app.ui import App


class CallbackTests(unittest.TestCase):
    def test_background_resize_does_not_show_startup_save_error(self):
        app = App.__new__(App)
        app.root = Mock()
        app._bg_timer = None
        App._background_resized(app)
        app.root.after.assert_called_once()
        callback = app.root.after.call_args.args[1]
        app.apply_background = Mock()
        callback()
        app.apply_background.assert_called_once_with(report_error=False)

    def test_overdue_check_refreshes_warehouse_and_schedules_next_check(self):
        app = App.__new__(App)
        app.root = Mock()
        app.service = Mock()
        app.service.mark_overdue_lost.return_value = [{'id': '0001'}]
        app.current_screen = 'warehouse'
        app._lost_check_error_shown = False
        app.language = 'ru'
        app.t = Mock(side_effect=lambda source, **values: source.format(**values))
        app.refresh = Mock()
        app.show_dialog = Mock()
        App._check_overdue_lost(app)
        app.refresh.assert_called_once()
        app.show_dialog.assert_called_once()
        app.root.after.assert_called_once_with(60_000, app._check_overdue_lost)

    def _remove_dialog_app(self, confirmed):
        app = App.__new__(App)
        app.language = 'ru'
        app._selected_id = Mock(return_value='0001')
        app.t = Mock(side_effect=lambda source, **values: source.format(**values))
        app.ask_confirmation = Mock(return_value=confirmed)
        app.service = Mock()
        app.service.get.return_value = {
            'id': '0001', 'name': 'Модель', 'status': 'Готов'}
        app.refresh = Mock()
        app._error = Mock()
        return app

    def test_remove_from_stock_waits_for_confirmation(self):
        app = self._remove_dialog_app(confirmed=False)
        App.remove_dialog(app)
        app.ask_confirmation.assert_called_once()
        app.service.remove.assert_not_called()
        app.refresh.assert_not_called()

    def test_remove_from_stock_removes_selected_item_after_confirmation(self):
        app = self._remove_dialog_app(confirmed=True)
        App.remove_dialog(app)
        app.service.remove.assert_called_once_with('0001')
        app.refresh.assert_called_once()

    def test_scanned_ids_are_staged_and_one_commit_receives_the_batch(self):
        app = App.__new__(App)
        app.root = Mock()
        app.batch_action = 'receive'
        app.batch_scan = Mock(get=lambda: '0001', set=Mock())
        app.batch_date = Mock(get=lambda: '2026-10-29')
        app.batch_ids = []
        app.batch_tree = Mock()
        app.batch_count = Mock()
        app.batch_submit = Mock()
        app.batch_feedback = Mock()
        app.service = Mock()
        app.service.preview_receive.return_value = {
            'id': '0001', 'name': 'Модель', 'status': 'На заправке'}
        app.service.preview_transition.return_value = {
            'id': '0001', 'name': 'Модель', 'status': 'На заправке'}
        self.assertEqual(app._scan_incoming(), 'break')
        app.service.receive_many.assert_not_called()
        self.assertEqual(app.batch_ids, ['0001'])
        app._commit_operation_batch()
        app.service.receive_many.assert_called_once_with(['0001'], '2026-10-29')

    def test_scanned_ids_are_staged_and_one_commit_sends_the_batch(self):
        app = App.__new__(App)
        app.root = Mock()
        app.batch_action = 'send'
        app.batch_scan = Mock(get=lambda: '0001', set=Mock())
        app.batch_date = Mock(get=lambda: '2026-10-29')
        app.batch_ids = []
        app.batch_tree = Mock()
        app.batch_count = Mock()
        app.batch_submit = Mock()
        app.batch_feedback = Mock()
        app.service = Mock()
        app.service.preview_transition.return_value = {
            'id': '0001', 'name': 'Модель', 'status': 'Готов'}
        self.assertEqual(app._scan_incoming(), 'break')
        app.service.send_many.assert_not_called()
        self.assertEqual(app.batch_ids, ['0001'])
        app._commit_operation_batch()
        app.service.send_many.assert_called_once_with(['0001'], '2026-10-29')

    def test_rescanning_sent_id_reports_error_without_changing_batch(self):
        app = App.__new__(App)
        app.root = Mock()
        app.batch_action = 'send'
        app.batch_scan = Mock(get=lambda: '0001', set=Mock())
        app.batch_date = Mock(get=lambda: '2026-10-29')
        app.batch_ids = []
        app.batch_tree = Mock()
        app.batch_count = Mock()
        app.batch_submit = Mock()
        app.batch_feedback = Mock()
        app.language = 'ru'
        app.service = Mock()
        app.service.preview_transition.side_effect = ValueError(
            'Операция «отправление» недоступна для ID «0001» со статусом «На заправке».')
        with patch('cartridge_app.ui.transition_label') as show_feedback:
            self.assertEqual(App._scan_incoming(app), 'break')
        self.assertEqual(app.batch_ids, [])
        app.batch_tree.insert.assert_not_called()
        app.batch_count.configure.assert_not_called()
        self.assertIn('На заправке', show_feedback.call_args.args[2])

    def test_scanned_ids_are_staged_and_one_commit_writes_off_the_batch(self):
        app = App.__new__(App)
        app.root = Mock()
        app.batch_action = 'write_off'
        app.batch_scan = Mock(get=lambda: '0001', set=Mock())
        app.batch_date = Mock(get=lambda: '2026-10-29')
        app.batch_ids = []
        app.batch_tree = Mock()
        app.batch_count = Mock()
        app.batch_submit = Mock()
        app.batch_feedback = Mock()
        app.service = Mock()
        app.service.preview_transition.return_value = {
            'id': '0001', 'name': 'Модель', 'status': 'Готов'}
        self.assertEqual(app._scan_incoming(), 'break')
        app.service.write_off_many.assert_not_called()
        self.assertEqual(app.batch_ids, ['0001'])
        app._commit_operation_batch()
        app.service.write_off_many.assert_called_once_with(['0001'], '2026-10-29', confirmed=True)


@unittest.skipUnless(os.environ.get('RUN_GUI_TESTS') == '1', 'Требуется рабочий графический сеанс Tk; RUN_GUI_TESTS=1')
class RealTkSmokeTests(unittest.TestCase):
    def test_all_screens_and_id_selection(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory) / 'ui.sqlite3')
            root = tk.Tk()
            try:
                service = Service(storage)
                service.add('0001', 'Модель')
                app = App(root, service)
                root.geometry('900x600')
                root.update()
                app.show_warehouse()
                root.update()
                app.tree.selection_set(app.tree.get_children()[0])
                self.assertEqual(app._selected_id(), '0001')
                expected = {'send': 'На заправке', 'receive': 'Готов', 'write_off': 'Списан'}
                for action in ('send', 'receive', 'write_off'):
                    app.show_operation(action)
                    root.update()
                    app.batch_scan.set('0001')
                    app._scan_incoming()
                    self.assertEqual(app.batch_ids, ['0001'])
                    app._commit_operation_batch()
                    self.assertEqual(service.get('0001')['status'], expected[action])
                for screen in (app.show_profile, app.show_history, app.show_main):
                    screen()
                    root.update()
            finally:
                root.destroy()
                storage.close()
