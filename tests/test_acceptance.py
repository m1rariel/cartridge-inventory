"""Acceptance checks against real SQLite files; never touch user data."""
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from cartridge_app.service import Service, ValidationError
from cartridge_app.storage import Storage
from cartridge_app.xlsx import export_inventory


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.path = self.directory / 'inventory.sqlite3'
        self.storage = Storage(self.path)
        self.service = Service(self.storage)
        self.today = date.today().isoformat()

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def restart(self):
        self.storage.close()
        self.storage = Storage(self.path)
        self.service = Service(self.storage)

    def test_leading_zeroes_restart_and_xlsx_text(self):
        self.service.save_profile('ООО «Пример»', 'Иван Иванов')
        self.service.add('0001', 'Модель & <A>', 'Принтер 1')
        self.restart()
        self.assertEqual(self.service.get('0001')['id'], '0001')
        export = export_inventory(self.service.list(), self.directory / 'warehouse.xlsx', self.service.profile())
        with zipfile.ZipFile(export) as z:
            self.assertIsNone(z.testzip())
            root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            cell = root.find('.//s:c[@r="A5"]', ns)
            self.assertEqual(cell.attrib['t'], 'inlineStr')
            self.assertEqual(cell.find('s:is/s:t', ns).text, '0001')
            self.assertEqual(root.find('.//s:c[@r="B5"]/s:is/s:t', ns).text, 'Модель & <A>')
            self.assertEqual(root.find('.//s:c[@r="A1"]/s:is/s:t', ns).text, 'Организация')
            self.assertEqual(root.find('.//s:c[@r="B1"]/s:is/s:t', ns).text, 'ООО «Пример»')
            self.assertEqual(root.find('.//s:c[@r="A2"]/s:is/s:t', ns).text, 'Ответственный')
            self.assertEqual(root.find('.//s:c[@r="B2"]/s:is/s:t', ns).text, 'Иван Иванов')
            self.assertEqual(root.find('.//s:autoFilter', ns).attrib['ref'], 'A4:E5')
            self.assertEqual(len(root.findall('.//s:mergeCell', ns)), 2)

    def test_duplicate_rejected_same_model_allowed(self):
        self.service.add('0001', 'Одна модель')
        self.service.add('0002', 'Одна модель')
        with self.assertRaisesRegex(ValidationError, 'уже существует'):
            self.service.add('0001', 'Другая модель')

    def test_remove_from_stock_preserves_history_and_reserves_id(self):
        self.service.save_profile('Организация', 'Ответственный')
        self.service.add('0001', 'Модель', 'Принтер')
        removed = self.service.remove('0001')
        self.assertEqual(removed['name'], 'Модель')
        self.assertEqual(self.service.list(), [])
        with self.assertRaisesRegex(ValidationError, 'не найден'):
            self.service.get('0001')
        with self.assertRaisesRegex(ValidationError, 'уже существует'):
            self.service.add('0001', 'Новая модель')
        history = self.service.history('0001')
        self.assertEqual([item['action'] for item in history], ['Удаление со склада', 'Добавление'])
        self.assertEqual(history[0]['old_status'], 'Готов')
        self.assertEqual(history[0]['new_status'], 'Готов')
        self.assertEqual(history[0]['organization'], 'Организация')
        self.assertEqual(json.loads(history[0]['details'])['name'], 'Модель')
        self.restart()
        self.assertEqual(self.service.list(), [])
        self.assertEqual(len(self.service.history('0001')), 2)

    def test_remove_history_failure_rolls_back_archive(self):
        self.service.add('0001', 'Модель')
        with patch.object(self.storage, 'add_history', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.remove('0001')
        self.assertEqual([row['id'] for row in self.service.list()], ['0001'])
        self.assertEqual(len(self.service.history()), 1)

    def test_refill_items_become_lost_after_exactly_seven_days(self):
        now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
        cases = {
            'old': now - timedelta(days=7, microseconds=1),
            'exact': now - timedelta(days=7),
            'recent': now - timedelta(days=7) + timedelta(microseconds=1),
        }
        for ident in cases:
            self.service.add(ident, 'Модель')
            self.service.operate(ident, 'send', self.today)
        with self.storage.transaction():
            for ident, sent_at in cases.items():
                self.storage.connection.execute(
                    "UPDATE history SET recorded_at=? WHERE cartridge_id=? AND action='Отправление'",
                    (sent_at.isoformat(), ident))
        changed = self.service.mark_overdue_lost(now)
        self.assertCountEqual([item['id'] for item in changed], ['old', 'exact'])
        self.assertEqual(self.service.get('old')['status'], 'Утерян')
        self.assertEqual(self.service.get('exact')['status'], 'Утерян')
        self.assertEqual(self.service.get('recent')['status'], 'На заправке')
        lost_entry = self.service.history('exact')[0]
        self.assertEqual(lost_entry['action'], 'Автоматическое признание утерянным')
        self.assertEqual(lost_entry['old_status'], 'На заправке')
        self.assertEqual(lost_entry['new_status'], 'Утерян')
        self.assertEqual(self.service.mark_overdue_lost(now), [])

    def test_lost_transition_and_history_are_atomic(self):
        self.service.add('0001', 'Модель')
        self.service.operate('0001', 'send', self.today)
        overdue = (datetime.now().astimezone() - timedelta(days=8)).isoformat()
        with self.storage.transaction():
            self.storage.connection.execute(
                "UPDATE history SET recorded_at=? WHERE cartridge_id='0001' AND action='Отправление'",
                (overdue,))
        with patch.object(self.storage, 'add_history', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.mark_overdue_lost()
        self.assertEqual(self.service.get('0001')['status'], 'На заправке')
        self.assertEqual(len(self.service.history('0001')), 2)

    def _make_v1_database(self, path):
        connection = sqlite3.connect(path)
        connection.executescript('''
            CREATE TABLE cartridges (
                id TEXT PRIMARY KEY NOT NULL CHECK(typeof(id)='text' AND length(trim(id))>0),
                name TEXT NOT NULL CHECK(length(trim(name))>0),
                printers TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('Готов','На заправке','Списан','Утерян')),
                operation_date TEXT NOT NULL
            );
            CREATE TABLE profile (
                id INTEGER PRIMARY KEY CHECK(id=1),
                organization TEXT NOT NULL DEFAULT '',
                full_name TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO profile(id,organization,full_name) VALUES(1,'Старая организация','Старый сотрудник');
            CREATE TABLE history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cartridge_id TEXT NOT NULL REFERENCES cartridges(id),
                action TEXT NOT NULL,
                old_status TEXT CHECK(old_status IS NULL OR old_status IN ('Готов','На заправке','Списан','Утерян')),
                new_status TEXT NOT NULL CHECK(new_status IN ('Готов','На заправке','Списан','Утерян')),
                operation_date TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                organization TEXT NOT NULL DEFAULT '',
                full_name TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                details TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX history_cartridge ON history(cartridge_id, id);
        ''')
        connection.execute('INSERT INTO cartridges(id,name,printers,status,operation_date) VALUES(?,?,?,?,?)',
                           ('0007', 'Старая модель', '', 'Готов', self.today))
        connection.execute('PRAGMA application_id=1128354388')
        connection.execute('PRAGMA user_version=1')
        connection.commit()
        connection.close()

    def test_v1_database_and_backup_migrate_without_losing_user_data(self):
        legacy_path = self.directory / 'legacy-v1.sqlite3'
        self._make_v1_database(legacy_path)
        legacy = Storage(legacy_path)
        try:
            self.assertEqual(legacy.connection.execute('PRAGMA user_version').fetchone()[0], 2)
            migrated_service = Service(legacy)
            self.assertEqual(migrated_service.get('0007')['name'], 'Старая модель')
            self.assertEqual(migrated_service.profile()['organization'], 'Старая организация')
        finally:
            legacy.close()
        self.service.restore(legacy_path)
        self.assertEqual(self.service.get('0007')['name'], 'Старая модель')
        self.assertEqual(self.service.profile()['full_name'], 'Старый сотрудник')

    def test_required_fields_and_numeric_id(self):
        for args in [('', 'Модель'), ('1', ' '), (1, 'Модель')]:
            with self.subTest(args=args), self.assertRaises(ValidationError):
                self.service.add(*args)
        self.assertEqual(self.service.list(), [])

    def test_edit_changes_only_selected_instance(self):
        self.service.add('0001', 'Общая модель')
        self.service.add('0002', 'Общая модель')
        changed = self.service.edit('0001', 'Уточнённая модель', 'HP 1010; Canon')
        self.assertEqual(changed['id'], '0001')
        self.assertEqual(changed['printers'], 'HP 1010; Canon')
        self.assertEqual(self.service.get('0002')['name'], 'Общая модель')
        details = json.loads(self.service.history('0001')[0]['details'])
        self.assertEqual(details['old']['name'], 'Общая модель')
        self.restart()
        self.assertEqual(self.service.get('0001')['name'], 'Уточнённая модель')

    def test_send_then_receive_and_history(self):
        self.service.add('0001', 'A')
        self.assertEqual(self.service.operate('0001', 'send', self.today)['status'], 'На заправке')
        self.assertEqual(self.service.operate('0001', 'receive', self.today)['status'], 'Готов')
        history = self.service.history('0001')
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]['old_status'], 'На заправке')
        self.assertEqual(history[0]['new_status'], 'Готов')
        self.assertEqual(history[0]['operation_date'], self.today)
        self.assertIsNotNone(datetime.fromisoformat(history[0]['recorded_at']).tzinfo)

    def test_receive_batch_is_atomic_and_logs_all_returns(self):
        for ident in ('0001', '0002'):
            self.service.add(ident, 'Одна модель')
            self.service.operate(ident, 'send', self.today)
        result = self.service.receive_many(['0001', '0002'], self.today)
        self.assertEqual([item['status'] for item in result], ['Готов', 'Готов'])
        self.assertEqual(self.service.get('0001')['status'], 'Готов')
        self.assertEqual(self.service.get('0002')['status'], 'Готов')
        self.assertEqual(sum(item['action'] == 'Прибытие' for item in self.service.history()), 2)

        for ident in ('0003', '0004'):
            self.service.add(ident, 'Одна модель')
            self.service.operate(ident, 'send', self.today)
        original = self.storage.add_history
        calls = [0]
        def fail_on_second(record):
            calls[0] += 1
            if calls[0] == 2:
                raise sqlite3.OperationalError('disk full')
            original(record)
        with patch.object(self.storage, 'add_history', side_effect=fail_on_second):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.receive_many(['0003', '0004'], self.today)
        self.assertEqual(self.service.get('0003')['status'], 'На заправке')
        self.assertEqual(self.service.get('0004')['status'], 'На заправке')

    def test_receive_batch_rejects_unknown_ready_duplicate_and_bad_date(self):
        self.service.add('0001', 'A')
        with self.assertRaisesRegex(ValidationError, 'уже есть|повторяющиеся'):
            self.service.receive_many(['0001', '0001'], self.today)
        with self.assertRaisesRegex(ValidationError, 'не найден'):
            self.service.preview_receive('missing', self.today)
        with self.assertRaisesRegex(ValidationError, 'недоступн'):
            self.service.preview_receive('0001', self.today)
        with self.assertRaises(ValidationError):
            self.service.receive_many(['0001'], 'not-a-date')
        self.assertEqual(self.service.get('0001')['status'], 'Готов')

    def test_send_batch_is_atomic_and_logs_all_shipments(self):
        for ident in ('0001', '0002'):
            self.service.add(ident, 'Одна модель')
        sent = self.service.send_many(['0001', '0002'], self.today)
        self.assertEqual([item['status'] for item in sent], ['На заправке', 'На заправке'])
        self.assertEqual(sum(item['action'] == 'Отправление' for item in self.service.history()), 2)

        for ident in ('0003', '0004'):
            self.service.add(ident, 'Одна модель')
        original = self.storage.add_history
        calls = [0]
        def fail_on_second(record):
            calls[0] += 1
            if calls[0] == 2:
                raise sqlite3.OperationalError('disk full')
            original(record)
        with patch.object(self.storage, 'add_history', side_effect=fail_on_second):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.send_many(['0003', '0004'], self.today)
        self.assertEqual(self.service.get('0003')['status'], 'Готов')
        self.assertEqual(self.service.get('0004')['status'], 'Готов')

    def test_invalid_transitions_are_atomic(self):
        self.service.add('1', 'A')
        with self.assertRaises(ValidationError):
            self.service.operate('1', 'receive', self.today)
        self.service.operate('1', 'send', self.today)
        with self.assertRaises(ValidationError):
            self.service.operate('1', 'send', self.today)
        self.assertEqual(self.service.get('1')['status'], 'На заправке')
        self.assertEqual(len(self.service.history()), 2)
        with self.storage.transaction():
            self.storage.update_cartridge('1', {'status': 'Утерян'})
        for action in ('send', 'receive', 'write_off'):
            with self.subTest(action=action), self.assertRaises(ValidationError):
                self.service.operate('1', action, self.today, confirmed=True)
        self.assertEqual(len(self.service.history()), 2)

    def test_write_off_confirmation_and_terminal_status(self):
        self.service.add('1', 'A')
        with self.assertRaises(ValidationError):
            self.service.operate('1', 'write_off', self.today, confirmed=False)
        self.assertEqual(self.service.get('1')['status'], 'Готов')
        self.assertEqual(len(self.service.history()), 1)
        self.service.operate('1', 'write_off', self.today, confirmed=True)
        self.assertEqual(self.service.history()[0]['reason'], '')
        self.assertEqual(self.service.get('1')['status'], 'Списан')
        for action in ('send', 'receive', 'write_off'):
            with self.subTest(action=action), self.assertRaises(ValidationError):
                self.service.operate('1', action, self.today, confirmed=True)
        with self.assertRaises(ValidationError):
            self.service.edit('1', 'B')
        self.assertEqual(len(self.service.history()), 2)

    def test_write_off_from_refill(self):
        self.service.add('1', 'A')
        self.service.operate('1', 'send', self.today)
        self.service.operate('1', 'write_off', self.today, confirmed=True)
        self.assertEqual(self.service.history()[0]['old_status'], 'На заправке')

    def test_write_off_batch_requires_one_confirmation_and_is_atomic(self):
        self.service.add('0001', 'A')
        self.service.add('0002', 'A')
        self.service.operate('0002', 'send', self.today)
        with self.assertRaisesRegex(ValidationError, 'Подтвердите списание'):
            self.service.write_off_many(['0001', '0002'], self.today)
        self.assertEqual(self.service.get('0001')['status'], 'Готов')
        self.assertEqual(self.service.get('0002')['status'], 'На заправке')
        result = self.service.write_off_many(['0001', '0002'], self.today, confirmed=True)
        self.assertEqual([item['status'] for item in result], ['Списан', 'Списан'])

        self.service.add('0003', 'A')
        self.service.add('0004', 'A')
        original = self.storage.add_history
        calls = [0]
        def fail_on_second(record):
            calls[0] += 1
            if calls[0] == 2:
                raise sqlite3.OperationalError('disk full')
            original(record)
        with patch.object(self.storage, 'add_history', side_effect=fail_on_second):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.write_off_many(['0003', '0004'], self.today, confirmed=True)
        self.assertEqual(self.service.get('0003')['status'], 'Готов')
        self.assertEqual(self.service.get('0004')['status'], 'Готов')

    def test_unknown_id_invalid_and_backward_dates(self):
        with self.assertRaisesRegex(ValidationError, 'не найден'):
            self.service.get('missing')
        self.service.add('1', 'A', operation_date='2025-10-02')
        for value in ('02.10.2025', '2025-02-30', '', '2025-10-01'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.service.operate('1', 'send', value)
        self.assertEqual(self.service.get('1')['status'], 'Готов')
        self.assertEqual(len(self.service.history()), 1)

    def test_profile_snapshot_and_restart(self):
        self.service.save_profile('Организация 1', 'Иван Иванов')
        self.service.add('1', 'A')
        self.service.save_profile('Организация 2', 'Пётр Петров')
        self.service.operate('1', 'send', self.today)
        self.restart()
        self.assertEqual(self.service.profile()['organization'], 'Организация 2')
        rows = self.service.history()
        self.assertEqual(rows[0]['full_name'], 'Пётр Петров')
        self.assertEqual(rows[1]['organization'], 'Организация 1')
        self.assertEqual(rows[1]['full_name'], 'Иван Иванов')

    def test_history_failure_rolls_back_status_and_create(self):
        self.service.add('1', 'A')
        with patch.object(self.storage, 'add_history', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.operate('1', 'send', self.today)
            with self.assertRaises(sqlite3.OperationalError):
                self.service.add('2', 'B')
            with self.assertRaises(sqlite3.OperationalError):
                self.service.edit('1', 'Changed')
        self.restart()
        self.assertEqual(self.service.get('1')['status'], 'Готов')
        self.assertEqual(self.service.get('1')['name'], 'A')
        self.assertIsNone(self.storage.get_cartridge('2'))
        self.assertEqual(len(self.service.history()), 1)

    def test_backup_restore_and_safety_copy(self):
        self.service.save_profile('Компания', 'Сотрудник')
        self.service.add('0001', 'A')
        backup = self.service.backup(self.directory / 'backup.sqlite3')
        self.service.operate('0001', 'send', self.today)
        self.service.add('0002', 'A')
        safety = self.service.restore(backup)
        self.assertTrue(safety.is_file())
        self.assertEqual(len(self.service.list()), 1)
        self.assertEqual(self.service.get('0001')['status'], 'Готов')
        self.assertEqual(self.service.profile()['organization'], 'Компания')
        self.restart()
        self.assertEqual(len(self.service.history()), 1)
        self.service.restore(safety)
        self.assertEqual(len(self.service.list()), 2)
        self.assertEqual(self.service.get('0001')['status'], 'На заправке')

    def test_bad_restore_and_self_backup_preserve_data(self):
        self.service.add('1', 'A')
        bad = self.directory / 'bad.sqlite3'
        bad.write_bytes(b'not a database')
        with self.assertRaises((ValueError, sqlite3.DatabaseError)):
            self.service.restore(bad)
        with self.assertRaises(ValueError):
            self.service.backup(self.path)
        with self.assertRaises(ValueError):
            self.service.restore(self.path)
        self.restart()
        self.assertEqual(self.service.get('1')['name'], 'A')

    def test_search_filter_sort(self):
        self.service.add('002', 'Canon')
        self.service.add('001', 'HP')
        self.service.operate('002', 'send', self.today)
        self.assertEqual([r['id'] for r in self.service.list(query='cAn')], ['002'])
        self.assertEqual([r['id'] for r in self.service.list(query='001')], ['001'])
        self.assertEqual([r['id'] for r in self.service.list(status='Готов')], ['001'])
        self.assertEqual([r['id'] for r in self.service.list(sort_by='name')], ['002', '001'])
        self.assertEqual(self.service.list(query='нет совпадений'), [])

    def test_id_sort_uses_natural_order_and_keeps_leading_zero_ids(self):
        for ident in ('10', '2', '1', '001'):
            self.service.add(ident, 'Одна модель')
        self.assertEqual([r['id'] for r in self.service.list(sort_by='id')],
                         ['1', '001', '2', '10'])
        self.assertEqual([r['id'] for r in self.service.list(sort_by='id', descending=True)],
                         ['10', '2', '001', '1'])

    def test_export_failure_preserves_existing_destination(self):
        self.service.add('1', 'A')
        path = self.directory / 'existing.xlsx'
        path.write_bytes(b'previous export')
        with patch('cartridge_app.xlsx.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                export_inventory(self.service.list(), path)
        self.assertEqual(path.read_bytes(), b'previous export')
        self.assertEqual(list(self.directory.glob('.export-*')), [])

    def test_formula_like_id_exported_as_literal(self):
        self.service.add('=1+1', 'A')
        path = export_inventory(self.service.list(), self.directory / 'literal.xlsx')
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(root.findall('.//{*}f'), [])
            cell = root.find('.//{*}c[@r="A5"]')
            self.assertEqual(cell.attrib['t'], 'inlineStr')
            self.assertEqual(cell.attrib['r'], 'A5')
            self.assertEqual(cell.find('./{*}is/{*}t').text, '=1+1')


if __name__ == '__main__':
    unittest.main()
