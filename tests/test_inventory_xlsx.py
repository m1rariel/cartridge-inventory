"""Inventory workbook migration and failure-safety checks."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import xml.etree.ElementTree as ET

from cartridge_app.inventory_xlsx import import_inventory_xlsx
from cartridge_app.service import Service, ValidationError
from cartridge_app.storage import Storage
from cartridge_app.xlsx import export_inventory


class InventoryXlsxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Storage(self.root / 'inventory.sqlite3')
        self.service = Service(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def workbook(self, records=None, profile=None):
        records = records or [
            {'id': '0001', 'name': 'Модель A', 'printers': 'HP 1; Canon 2',
             'status': 'На заправке', 'operation_date': '2026-10-30'},
            {'id': '0002', 'name': 'Модель A', 'printers': 'HP 1',
             'status': 'Готов', 'operation_date': '2026-11-01'},
        ]
        return export_inventory(records, self.root / 'Склад.xlsx', profile=profile)

    def test_previous_version_export_imports_all_records_and_keeps_ids_as_text(self):
        source = self.workbook(profile={'organization': 'Старая организация', 'full_name': 'Старый сотрудник'})
        records = import_inventory_xlsx(source)
        self.assertEqual([row['id'] for row in records], ['0001', '0002'])
        preview = self.service.preview_inventory_import(records)
        self.assertEqual(self.service.list(), [])
        self.assertEqual(self.service.import_inventory(preview, source.name), 2)
        self.assertEqual(self.service.get('0001')['status'], 'На заправке')
        self.assertEqual(self.service.get('0001')['operation_date'], '2026-10-30')
        self.assertEqual(self.service.get('0001')['id'], '0001')
        self.assertEqual(self.service.profile(), {'organization': '', 'full_name': ''})
        self.assertEqual(self.service.catalogs(), {
            'models': ['Модель A'], 'printers': ['Canon 2', 'HP 1']})
        history = self.service.history('0001')[0]
        self.assertEqual(history['action'], 'Импорт из Excel')
        self.assertEqual(history['old_status'], None)
        self.assertEqual(history['new_status'], 'На заправке')
        self.assertEqual(history['details'], '{"source": "Склад.xlsx", "imported_status": "На заправке"}')

    def test_collision_aborts_whole_import_including_archived_ids(self):
        self.service.add('0002', 'Уже есть')
        self.service.add('0003', 'Будет удалён')
        self.service.remove('0003')
        records = import_inventory_xlsx(self.workbook())
        with self.assertRaisesRegex(ValidationError, 'уже заняты'):
            self.service.preview_inventory_import(records)
        with self.assertRaisesRegex(ValidationError, 'уже заняты'):
            self.service.import_inventory(records)
        self.assertEqual([item['id'] for item in self.service.list()], ['0002'])
        self.assertEqual(self.service.catalogs(), {'models': ['Будет удалён', 'Уже есть'], 'printers': []})

    def test_mid_import_storage_error_rolls_back_stock_history_and_catalogs(self):
        records = import_inventory_xlsx(self.workbook())
        actual = self.db.add_history
        calls = {'count': 0}

        def fail_second(record):
            calls['count'] += 1
            if calls['count'] == 2:
                raise sqlite3.OperationalError('disk full')
            return actual(record)

        with patch.object(self.db, 'add_history', side_effect=fail_second):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.import_inventory(records, 'source.xlsx')
        self.assertEqual(self.service.list(), [])
        self.assertEqual(self.service.history(), [])
        self.assertEqual(self.service.catalogs(), {'models': [], 'printers': []})

    def test_numeric_id_or_date_are_rejected_to_prevent_silent_conversion(self):
        path = self.workbook()
        replacement = self.root / 'numeric-id.xlsx'
        namespace = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with zipfile.ZipFile(path, 'r') as source, zipfile.ZipFile(replacement, 'w') as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename == 'xl/worksheets/sheet1.xml':
                    root = ET.fromstring(payload)
                    cell = root.find('.//s:c[@r="A5"]', namespace)
                    cell.attrib.pop('t', None)
                    for child in list(cell):
                        cell.remove(child)
                    ET.SubElement(cell, f'{{{namespace["s"]}}}v').text = '1'
                    payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                target.writestr(info, payload)
        with self.assertRaisesRegex(ValueError, 'ID.*текст'):
            import_inventory_xlsx(replacement)

    def test_duplicate_id_in_file_and_invalid_status_or_date_are_rejected(self):
        duplicate = self.workbook(records=[
            {'id': '0001', 'name': 'A', 'printers': '', 'status': 'Готов', 'operation_date': '2026-11-01'},
            {'id': '0001', 'name': 'B', 'printers': '', 'status': 'Готов', 'operation_date': '2026-11-01'},
        ])
        with self.assertRaisesRegex(ValueError, 'повторяется'):
            import_inventory_xlsx(duplicate)
        invalid_status = [{'id': '1', 'name': 'Модель', 'printers': '',
                           'status': 'Неизвестно', 'operation_date': '2026-11-01'}]
        with self.assertRaisesRegex(ValidationError, 'неизвестный статус'):
            self.service.preview_inventory_import(invalid_status)
        invalid_date = [{'id': '1', 'name': 'Модель', 'printers': '',
                         'status': 'Готов', 'operation_date': '2026-02-30'}]
        with self.assertRaises(ValidationError):
            self.service.preview_inventory_import(invalid_date)
        self.assertEqual(self.service.list(), [])


if __name__ == '__main__':
    unittest.main()
