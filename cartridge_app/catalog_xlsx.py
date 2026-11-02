"""Import/export XLSX catalog workbooks using the standard library only."""
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile
from xml.etree import ElementTree as ET


MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
DOC_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CONTENT_TYPES = 'http://schemas.openxmlformats.org/package/2006/content-types'
MAX_UNPACKED_SIZE = 25 * 1024 * 1024
_CELL = re.compile(r'^([A-Z]+)')
_MODEL_HEADERS = {
    'картриджи', 'картридж', 'моделькартриджа', 'наименованиекартриджа',
    'модель', 'наименование', 'название', 'name', 'model',
    'cartridge', 'cartridges', 'cartridgemodel', 'cartridgemodels', 'models',
}
_GENERIC_NAME_HEADERS = {'наименование', 'название', 'name', 'model'}
_PRINTER_HEADERS = {
    'принтер', 'принтеры', 'совместимые принтеры', 'подходящие принтеры',
    'printer', 'printers', 'compatibleprinters',
}


def _normalized(value):
    return re.sub(r'[\s_]+', '', str(value or '').strip().casefold().replace('ё', 'е'))


def _column_index(address):
    match = _CELL.match(address or '')
    if not match:
        return None
    result = 0
    for character in match.group(1):
        result = result * 26 + ord(character) - 64
    return result - 1


def _worksheet_rows(archive, name, shared_strings):
    try:
        root = ET.fromstring(archive.read(name))
    except (KeyError, ET.ParseError) as error:
        raise ValueError('Не удалось прочитать лист Excel. Проверьте файл.') from error
    sheet_data = root.find(f'{{{MAIN}}}sheetData')
    if sheet_data is None:
        return []
    rows = []
    for row in sheet_data.findall(f'{{{MAIN}}}row'):
        values = []
        for cell in row.findall(f'{{{MAIN}}}c'):
            index = _column_index(cell.get('r'))
            if index is None or index > 16383:
                continue
            while len(values) <= index:
                values.append('')
            kind = cell.get('t')
            if kind == 'inlineStr':
                value = ''.join(node.text or '' for node in cell.iter(f'{{{MAIN}}}t'))
            else:
                stored = cell.find(f'{{{MAIN}}}v')
                value = stored.text if stored is not None and stored.text else ''
                if kind == 's' and value:
                    try:
                        value = shared_strings[int(value)]
                    except (ValueError, IndexError):
                        raise ValueError('В книге Excel повреждён список текстовых значений.') from None
                elif kind == 'b':
                    value = ''
            values[index] = value
        rows.append(values)
    return rows


def _workbook_sheets(archive):
    try:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
    except (KeyError, ET.ParseError) as error:
        raise ValueError('Файл не является поддерживаемой книгой Excel .xlsx.') from error
    targets = {}
    for relation in relationships.findall(f'{{{PKG_REL}}}Relationship'):
        target = relation.get('Target', '')
        if target.startswith('/'):
            resolved = target.lstrip('/')
        else:
            resolved = os.path.normpath(os.path.join('xl', target)).replace('\\', '/')
        path = PurePosixPath(resolved)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Книга Excel содержит недопустимый путь листа.')
        targets[relation.get('Id')] = str(path)
    sheets = []
    for sheet in workbook.findall(f'.//{{{MAIN}}}sheet'):
        relationship_id = sheet.get(f'{{{DOC_REL}}}id')
        target = targets.get(relationship_id)
        if target:
            sheets.append((sheet.get('name', ''), target))
    if not sheets:
        raise ValueError('В книге Excel не найдено ни одного листа.')
    return sheets


def _shared_strings(archive):
    try:
        root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    except KeyError:
        return []
    except ET.ParseError as error:
        raise ValueError('В книге Excel повреждён список текстовых значений.') from error
    return [''.join(node.text or '' for node in item.iter(f'{{{MAIN}}}t'))
            for item in root.findall(f'{{{MAIN}}}si')]


def _split_printers(value):
    return [part.strip() for part in re.split(r'[,;\n]+', str(value or '')) if part.strip()]


def _collect(values, split=False):
    result = []
    seen = set()
    for value in values:
        candidates = _split_printers(value) if split else [str(value or '').strip()]
        for name in candidates:
            key = name.casefold()
            if name and key not in seen:
                seen.add(key)
                result.append(name)
    return result


def import_catalogs_xlsx(path):
    """Read catalog columns or the cartridge/printer columns of an inventory export."""
    path = Path(path)
    if path.suffix.lower() != '.xlsx':
        raise ValueError('Поддерживаются книги Excel в формате .xlsx. Старый формат .xls не поддерживается.')
    if not path.is_file():
        raise ValueError('Файл Excel не найден.')
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_UNPACKED_SIZE:
                raise ValueError('Книга Excel слишком большая для импорта (максимум 25 МБ распакованных данных).')
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError('Книга Excel повреждена. Импорт отменён.')
            shared = _shared_strings(archive)
            sheets = [(title, _worksheet_rows(archive, target, shared))
                      for title, target in _workbook_sheets(archive)]
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError('Не удалось прочитать файл Excel. Проверьте, что это неповреждённый .xlsx.') from error

    models, printers = [], []
    found_columns = False
    model_aliases = {_normalized(item) for item in _MODEL_HEADERS}
    printer_aliases = {_normalized(item) for item in _PRINTER_HEADERS}
    for sheet_name, rows in sheets:
        name_key = _normalized(sheet_name)
        named_model_sheet = name_key in {'картриджи', 'моделикартриджей', 'cartridges', 'models'}
        named_printer_sheet = name_key in {'принтеры', 'printers'}
        header_rows = []
        for row_index, row in enumerate(rows):
            model_column = None
            printer_column = None
            for column, value in enumerate(row):
                header = _normalized(value)
                if header in _GENERIC_NAME_HEADERS:
                    if named_printer_sheet:
                        printer_column = column
                    else:
                        model_column = column
                elif header in model_aliases:
                    model_column = column
                elif header in printer_aliases:
                    printer_column = column
            if model_column is not None or printer_column is not None:
                header_rows.append((row_index, model_column, printer_column))
        if header_rows:
            found_columns = True
            for row_index, model_column, printer_column in header_rows:
                for row in rows[row_index + 1:]:
                    if model_column is not None and model_column < len(row):
                        models.append(row[model_column])
                    if printer_column is not None and printer_column < len(row):
                        printers.extend(_split_printers(row[printer_column]))
        elif named_model_sheet or named_printer_sheet:
            found_columns = True
            target = models if named_model_sheet else printers
            for row in rows:
                if row and _normalized(row[0]) not in model_aliases | printer_aliases:
                    target.extend(_split_printers(row[0]) if named_printer_sheet else [row[0]])

    models = _collect(models)
    printers = _collect(printers, split=True)
    if not found_columns:
        raise ValueError('Не найдены столбцы «Картриджи» и «Принтеры». Используйте шаблон импорта справочников.')
    if not models and not printers:
        raise ValueError('В книге Excel не найдены наименования для импорта.')
    return {'version': 1, 'models': models, 'printers': printers}


def export_catalogs_xlsx(catalogs, destination):
    """Write a simple two-column workbook template, without formulas or Excel dependency."""
    destination = Path(destination)
    if destination.suffix.lower() != '.xlsx':
        raise ValueError('Укажите имя файла с расширением .xlsx.')
    models, printers = catalogs.get('models', []), catalogs.get('printers', [])
    root = ET.Element('worksheet', xmlns=MAIN)
    data = ET.SubElement(root, 'sheetData')
    rows = [['Картриджи', 'Принтеры']]
    rows.extend([[models[i] if i < len(models) else '',
                  printers[i] if i < len(printers) else '']
                 for i in range(max(len(models), len(printers)))])
    for number, values in enumerate(rows, 1):
        row = ET.SubElement(data, 'row', r=str(number))
        for column, value in enumerate(values):
            if not value:
                continue
            cell = ET.SubElement(row, 'c', r=f'{chr(65 + column)}{number}', t='inlineStr')
            inline = ET.SubElement(cell, 'is')
            text = ET.SubElement(inline, 't', {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'})
            text.text = str(value)
    worksheet = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    parts = {
        '[Content_Types].xml': b'''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>''',
        '_rels/.rels': b'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''',
        'xl/workbook.xml': f'''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{MAIN}" xmlns:r="{DOC_REL}"><sheets><sheet name="Справочники" sheetId="1" r:id="rId1"/></sheets></workbook>'''.encode('utf-8'),
        'xl/_rels/workbook.xml.rels': b'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''',
        'xl/worksheets/sheet1.xml': worksheet,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.catalog-export-', suffix='.xlsx', dir=str(destination.parent))
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, content in parts.items():
                archive.writestr(name, content)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination
