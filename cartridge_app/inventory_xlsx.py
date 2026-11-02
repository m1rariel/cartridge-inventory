"""Strict reader for warehouse workbooks exported by this application."""
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

from .catalog_xlsx import (MAX_UNPACKED_SIZE, MAIN, _column_index,
                           _shared_strings, _workbook_sheets)


HEADERS = {
    'id': {'id', 'идентификатор'},
    'name': {'наименованиекартриджа'},
    'printers': {'подходящиепринтеры', 'совместимыепринтеры'},
    'status': {'статус'},
    'operation_date': {'дата', 'датапоследнейоперации'},
}


def _key(value):
    return ''.join(str(value or '').casefold().replace('ё', 'е').split())


def _worksheet_typed_rows(archive, member, shared):
    try:
        root = ET.fromstring(archive.read(member))
    except (KeyError, ET.ParseError) as error:
        raise ValueError('Не удалось прочитать лист Excel. Проверьте файл.') from error
    data = root.find(f'{{{MAIN}}}sheetData')
    if data is None:
        return []
    rows = []
    for row_number, row in enumerate(data.findall(f'{{{MAIN}}}row'), 1):
        cells = {}
        for cell in row.findall(f'{{{MAIN}}}c'):
            column = _column_index(cell.get('r'))
            if column is None or column > 16383:
                continue
            if cell.find(f'{{{MAIN}}}f') is not None:
                raise ValueError(f'В строке {row_number} найдена формула. Сохраните значения в Excel и повторите экспорт.')
            kind = cell.get('t')
            if kind == 'inlineStr':
                value = ''.join(node.text or '' for node in cell.iter(f'{{{MAIN}}}t'))
            else:
                stored = cell.find(f'{{{MAIN}}}v')
                value = stored.text if stored is not None and stored.text else ''
                if kind == 's' and value:
                    try:
                        value = shared[int(value)]
                    except (ValueError, IndexError):
                        raise ValueError('В книге Excel повреждён список текстовых значений.') from None
                elif kind == 'b':
                    value = ''
            cells[column] = (value, kind)
        rows.append((row.get('r', str(row_number)), cells))
    return rows


def import_inventory_xlsx(path):
    """Parse an exported inventory table; IDs and dates must be explicit text."""
    path = Path(path)
    if path.suffix.lower() != '.xlsx':
        raise ValueError('Для переноса склада поддерживается только книга Excel .xlsx; формат .xls не поддерживается.')
    if not path.is_file():
        raise ValueError('Файл Excel не найден.')
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_UNPACKED_SIZE:
                raise ValueError('Книга Excel слишком большая для импорта (максимум 25 МБ распакованных данных).')
            if archive.testzip():
                raise ValueError('Книга Excel повреждена. Импорт отменён.')
            shared = _shared_strings(archive)
            sheets = _workbook_sheets(archive)
            worksheet = next((rows for _name, member in sheets
                              if (rows := _worksheet_typed_rows(archive, member, shared))), [])
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError('Не удалось прочитать файл Excel. Проверьте, что это неповреждённый .xlsx.') from error

    header_at = None
    columns = {}
    for index, (row_number, cells) in enumerate(worksheet):
        found = {}
        for column, (value, _kind) in cells.items():
            normalized = _key(value)
            for field, aliases in HEADERS.items():
                if normalized in aliases:
                    if field in found:
                        raise ValueError(f'В строке {row_number} повторяется заголовок «{field}».')
                    found[field] = column
        if set(found) == set(HEADERS):
            header_at, columns = index, found
            break
    if header_at is None:
        raise ValueError('Не найдена таблица склада с колонками ID, Наименование картриджа, Подходящие принтеры, Статус и Дата.')

    records, seen = [], set()
    for row_number, cells in worksheet[header_at + 1:]:
        values = {}
        for field, column in columns.items():
            value, kind = cells.get(column, ('', 'inlineStr'))
            value = str(value).strip()
            if field in ('id', 'operation_date') and value and kind not in ('inlineStr', 's', 'str'):
                label = 'ID' if field == 'id' else 'Дата'
                raise ValueError(f'В строке {row_number} поле «{label}» должно быть сохранено как текст. Проверьте исходный Excel.')
            values[field] = value
        if not any(values.values()):
            continue
        if not values['id']:
            raise ValueError(f'В строке {row_number} не заполнен ID.')
        if values['id'] in seen:
            raise ValueError(f'ID «{values["id"]}» повторяется в файле (строка {row_number}).')
        seen.add(values['id'])
        records.append(values)
    if not records:
        raise ValueError('В книге Excel нет строк складских экземпляров для импорта.')
    return records
