"""XLSX catalog import/export tests; no Excel installation is required."""
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch

from cartridge_app.catalog_xlsx import export_catalogs_xlsx, import_catalogs_xlsx
from cartridge_app.settings_dialog import SettingsDialog
from cartridge_app.xlsx import export_inventory


class CatalogXlsxTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_catalog_template_round_trips_and_deduplicates(self):
        path = export_catalogs_xlsx({
            'models': ['HP 12A', 'Canon 725'],
            'printers': ['HP LaserJet 1010', 'Canon LBP 6000'],
        }, self.root / 'catalogs.xlsx')
        self.assertTrue(zipfile.is_zipfile(path))
        payload = import_catalogs_xlsx(path)
        self.assertEqual(payload, {
            'version': 1,
            'models': ['HP 12A', 'Canon 725'],
            'printers': ['HP LaserJet 1010', 'Canon LBP 6000'],
        })

    def test_inventory_export_columns_import_as_catalogs(self):
        path = export_inventory([
            {'id': '0001', 'name': 'HP 12A', 'printers': 'HP 1010; HP 1020',
             'status': 'Готов', 'operation_date': '2026-11-02'},
            {'id': '0002', 'name': 'HP 12A', 'printers': 'hp 1010',
             'status': 'Готов', 'operation_date': '2026-11-02'},
        ], self.root / 'inventory.xlsx')
        payload = import_catalogs_xlsx(path)
        self.assertEqual(payload['models'], ['HP 12A'])
        self.assertEqual(payload['printers'], ['HP 1010', 'HP 1020'])

    def test_named_sheets_with_shared_string_cells(self):
        path = self.root / 'two-sheets.xlsx'
        shared = '''<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>HP 12A</t></si><si><t>Модель</t></si><si><t>HP 1010</t></si><si><t>Принтер</t></si></sst>'''
        workbook = '''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Картриджи" sheetId="1" r:id="rId1"/><sheet name="Принтеры" sheetId="2" r:id="rId2"/></sheets></workbook>'''
        relationships = '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/><Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>'''
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('xl/workbook.xml', workbook)
            archive.writestr('xl/_rels/workbook.xml.rels', relationships)
            archive.writestr('xl/sharedStrings.xml', shared)
            archive.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>0</v></c></row></sheetData></worksheet>')
            archive.writestr('xl/worksheets/sheet2.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>3</v></c></row><row r="2"><c r="A2" t="s"><v>2</v></c></row></sheetData></worksheet>')
        self.assertEqual(import_catalogs_xlsx(path), {
            'version': 1, 'models': ['HP 12A'], 'printers': ['HP 1010']})

    def test_old_xls_and_unrecognized_workbook_have_readable_errors(self):
        old = self.root / 'old.xls'
        old.write_bytes(b'legacy excel')
        with self.assertRaisesRegex(ValueError, '.xls'):
            import_catalogs_xlsx(old)
        invalid = self.root / 'invalid.xlsx'
        invalid.write_bytes(b'not an xlsx file')
        with self.assertRaisesRegex(ValueError, 'Excel'):
            import_catalogs_xlsx(invalid)

    def test_settings_import_routes_xlsx_into_catalog_merge(self):
        dialog = SettingsDialog.__new__(SettingsDialog)
        dialog.window = Mock()
        dialog.app = Mock()
        dialog.app.t.side_effect = lambda text, **values: text.format(**values)
        dialog.app.service.merge_catalogs.return_value = {'models': 1, 'printers': 2}
        payload = {'version': 1, 'models': ['Модель'], 'printers': ['Принтер']}
        with patch('cartridge_app.settings_dialog.filedialog.askopenfilename', return_value='catalogs.xlsx'), \
             patch('cartridge_app.settings_dialog.import_catalogs_xlsx', return_value=payload):
            SettingsDialog.import_catalogs(dialog)
        dialog.app.service.merge_catalogs.assert_called_once_with(payload)
        dialog.app.show_dialog.assert_called_once()


if __name__ == '__main__':
    unittest.main()
