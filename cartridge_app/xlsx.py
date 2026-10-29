"""Small OOXML writer: no Excel dependency, every cell explicitly text."""
import os
import tempfile
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
HEADERS = ['ID', 'Наименование картриджа', 'Подходящие принтеры', 'Статус', 'Дата']
KEYS = ['id', 'name', 'printers', 'status', 'operation_date']


def _xml(element):
    return tostring(element, encoding='utf-8', xml_declaration=True)


def _safe_text(value):
    text = str(value if value is not None else '')
    if len(text) > 32767:
        raise ValueError('Значение превышает ограничение XLSX: 32767 символов.')
    if any(ord(c) < 32 and c not in '\t\n\r' for c in text):
        raise ValueError('Текст содержит недопустимые для XLSX управляющие символы.')
    return text


def export_inventory(records, destination, profile=None):
    destination = Path(destination)
    if destination.suffix.lower() != '.xlsx':
        raise ValueError('Укажите имя файла с расширением .xlsx.')
    root = Element('worksheet', xmlns=NS)
    views = SubElement(root, 'sheetViews')
    view = SubElement(views, 'sheetView', workbookViewId='0')
    SubElement(view, 'pane', ySplit='4', topLeftCell='A5', activePane='bottomLeft', state='frozen')
    cols = SubElement(root, 'cols')
    for i, width in enumerate((20, 38, 48, 20, 16), 1):
        SubElement(cols, 'col', min=str(i), max=str(i), width=str(width), customWidth='1')
    data = SubElement(root, 'sheetData')
    profile = profile or {}
    rows = [
        ['Организация', profile.get('organization', ''), '', '', ''],
        ['Ответственный', profile.get('full_name', ''), '', '', ''],
        ['', '', '', '', ''],
        HEADERS,
    ] + [[r[k] for k in KEYS] for r in records]
    if len(rows) > 1048576:
        raise ValueError('Слишком много строк для одного листа XLSX.')
    for number, values in enumerate(rows, 1):
        row = SubElement(data, 'row', r=str(number))
        for col, value in enumerate(values):
            if value == '':
                continue
            cell = SubElement(row, 'c', r=f'{chr(65+col)}{number}', t='inlineStr')
            inline = SubElement(cell, 'is')
            txt = SubElement(inline, 't', {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'})
            txt.text = _safe_text(value)
    SubElement(root, 'autoFilter', ref=f'A4:E{len(rows)}')
    SubElement(root, 'mergeCells', count='2')
    merges = root[-1]
    SubElement(merges, 'mergeCell', ref='B1:E1')
    SubElement(merges, 'mergeCell', ref='B2:E2')
    SubElement(root, 'pageMargins', left='0.25', right='0.25', top='0.45', bottom='0.45', header='0.2', footer='0.2')
    SubElement(root, 'pageSetup', orientation='landscape', fitToWidth='1', fitToHeight='0')
    parts = {
        '[Content_Types].xml': b'''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>''',
        '_rels/.rels': b'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''',
        'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="'+NS+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Склад" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': b'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''',
        'xl/worksheets/sheet1.xml': _xml(root),
    }
    fd, temporary = tempfile.mkstemp(prefix='.export-', suffix='.xlsx', dir=str(destination.parent))
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
