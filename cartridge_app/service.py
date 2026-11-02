"""Правила учёта экземпляров; не зависят от Tkinter и реализации хранилища."""
from datetime import date, datetime, timedelta
import json
import re
from . import error_codes


class ValidationError(ValueError):
    """Ожидаемая ошибка ввода с сообщением для пользователя."""
    def __init__(self, message, voice_code=None):
        super().__init__(message)
        self.voice_code = voice_code


STATUSES = ('Готов', 'На заправке', 'Списан', 'Утерян')
TRANSITIONS = {
    'send': {'Готов': 'На заправке'},
    'receive': {'На заправке': 'Готов'},
    'write_off': {'Готов': 'Списан', 'На заправке': 'Списан'},
}
ACTION_NAMES = {
    'create': 'Добавление', 'edit': 'Редактирование',
    'send': 'Отправление', 'receive': 'Прибытие', 'write_off': 'Списание',
    'remove': 'Удаление со склада',
    'lost': 'Автоматическое признание утерянным',
    'import': 'Импорт из Excel',
}
LOST_AFTER = timedelta(days=7)


def _natural_id_key(value):
    """Sort text IDs naturally (2 before 10) without changing their stored form."""
    parts = tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                  for part in re.findall(r'\d+|\D+', value))
    # Numeric-equivalent IDs such as "1" and "001" remain distinct and stable.
    return parts, len(value), value.casefold(), value


def _text(value, label, required=False):
    if not isinstance(value, str):
        raise ValidationError(f'Поле «{label}» должно быть текстом.')
    result = value.strip()
    if required and not result:
        raise ValidationError(f'Заполните поле «{label}».')
    # XML 1.0 / XLSX cannot represent these control characters.
    if any(ord(c) < 32 and c not in '\t\n\r' for c in result):
        raise ValidationError(f'Поле «{label}» содержит недопустимые управляющие символы.')
    if len(result) > 32767:
        raise ValidationError(f'Поле «{label}» слишком длинное (максимум 32767 символов).')
    return result


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValidationError('Укажите дату в формате ГГГГ-ММ-ДД, например 2026-10-28.',
                              error_codes.INVALID_OPERATION_DATE)
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValidationError('Такой даты не существует. Проверьте день, месяц и год.',
                              error_codes.INVALID_OPERATION_DATE) from None


class Service:
    def __init__(self, storage):
        self.storage = storage

    def get(self, id):
        id = _text(id, 'ID', required=True)
        record = self.storage.get_cartridge(id)
        if record is None or record.get('removed_at') is not None:
            raise ValidationError(f'Картридж с ID «{id}» не найден.', error_codes.CARTRIDGE_NOT_FOUND)
        return {key: record[key] for key in ('id', 'name', 'printers', 'status', 'operation_date')}

    def list(self, query='', status='', sort_by='id', descending=False):
        if status and status not in STATUSES:
            raise ValidationError('Выбран неизвестный статус.')
        if sort_by not in ('id', 'name', 'printers', 'status', 'operation_date'):
            raise ValidationError('Неизвестный столбец сортировки.')
        query = _text(query, 'Поиск').casefold()
        records = [r for r in self.storage.list_cartridges()
                   if (not status or r['status'] == status)
                   and (query in r['id'].casefold() or query in r['name'].casefold())]
        if sort_by == 'id':
            return sorted(records, key=lambda r: _natural_id_key(r['id']), reverse=descending)
        return sorted(records, key=lambda r: (r[sort_by].casefold(), r['id']), reverse=descending)

    def _history(self, record, action, old_status, operation_date, details=None):
        profile = self.storage.get_profile()
        self.storage.add_history({
            'cartridge_id': record['id'], 'action': ACTION_NAMES[action],
            'old_status': old_status, 'new_status': record['status'],
            'operation_date': operation_date,
            'recorded_at': datetime.now().astimezone().isoformat(timespec='microseconds'),
            'organization': profile['organization'], 'full_name': profile['full_name'],
            'details': json.dumps(details or {}, ensure_ascii=False),
        })

    def add(self, id, name, printers='', operation_date=None):
        record = {
            'id': _text(id, 'ID', required=True),
            'name': _text(name, 'Наименование картриджа', required=True),
            'printers': _text(printers, 'Подходящие принтеры'),
            'status': 'Готов',
            'operation_date': _date(date.today().isoformat() if operation_date is None else operation_date),
        }
        with self.storage.transaction():
            if self.storage.get_cartridge(record['id']) is not None:
                raise ValidationError(f'Картридж с ID «{record["id"]}» уже существует. Введите другой ID.')
            self._ensure_catalog_value('model', record['name'])
            for printer in self._printer_names(record['printers']):
                self._ensure_catalog_value('printer', printer)
            self.storage.insert_cartridge(record)
            self._history(record, 'create', None, record['operation_date'], details={'new': record})
        return record

    @staticmethod
    def _prepare_inventory_import(records):
        if not isinstance(records, list) or not records:
            raise ValidationError('В файле нет складских экземпляров для импорта.')
        prepared, seen = [], set()
        for number, row in enumerate(records, 1):
            if not isinstance(row, dict):
                raise ValidationError(f'Строка {number}: неверный формат записи.')
            record = {
                'id': _text(row.get('id'), 'ID', required=True),
                'name': _text(row.get('name'), 'Наименование картриджа', required=True),
                'printers': _text(row.get('printers', ''), 'Подходящие принтеры'),
                'status': _text(row.get('status'), 'Статус', required=True),
                'operation_date': _date(row.get('operation_date')),
            }
            if record['status'] not in STATUSES:
                raise ValidationError(f'Строка {number}: неизвестный статус «{record["status"]}».')
            if record['id'] in seen:
                raise ValidationError(f'ID «{record["id"]}» повторяется в импортируемом файле.')
            seen.add(record['id'])
            prepared.append(record)
        return prepared

    def preview_inventory_import(self, records):
        """Validate an entire import without changing the database."""
        prepared = self._prepare_inventory_import(records)
        collisions = [item['id'] for item in prepared
                      if self.storage.get_cartridge(item['id']) is not None]
        if collisions:
            shown = ', '.join(f'«{value}»' for value in collisions[:8])
            more = f' и ещё {len(collisions) - 8}' if len(collisions) > 8 else ''
            raise ValidationError('Импорт отменён: ID уже заняты в базе: ' + shown + more +
                                  '. Существующие записи не изменены.')
        return prepared

    def import_inventory(self, records, source_name=''):
        """Append a complete XLSX stock snapshot atomically; never update existing IDs."""
        prepared = self._prepare_inventory_import(records)
        with self.storage.transaction():
            collisions = [item['id'] for item in prepared
                          if self.storage.get_cartridge(item['id']) is not None]
            if collisions:
                shown = ', '.join(f'«{value}»' for value in collisions[:8])
                more = f' и ещё {len(collisions) - 8}' if len(collisions) > 8 else ''
                raise ValidationError('Импорт отменён: ID уже заняты в базе: ' + shown + more +
                                      '. Существующие записи не изменены.')
            for record in prepared:
                self._ensure_catalog_value('model', record['name'])
                for printer in self._printer_names(record['printers']):
                    self._ensure_catalog_value('printer', printer)
                self.storage.insert_cartridge(record)
                self._history(record, 'import', None, record['operation_date'], details={
                    'source': source_name, 'imported_status': record['status'],
                })
        return len(prepared)

    def remove(self, id):
        """Remove an item from active stock while preserving its ID and history."""
        with self.storage.transaction():
            record = self.get(id)
            removed_at = datetime.now().astimezone().isoformat(timespec='microseconds')
            operation_date = max(date.today().isoformat(), record['operation_date'])
            self.storage.remove_cartridge(record['id'], removed_at)
            self._history(record, 'remove', record['status'], operation_date, details={
                'name': record['name'], 'printers': record['printers'],
                'status': record['status'], 'removed_at': removed_at,
            })
        return record

    def mark_overdue_lost(self, now=None):
        """Mark refill shipments lost after 7 real days, with an atomic history entry."""
        current = now or datetime.now().astimezone()
        if not isinstance(current, datetime) or current.tzinfo is None:
            raise ValidationError('Для проверки срока требуется дата и время с часовым поясом.')
        current = current.astimezone()
        changed = []
        with self.storage.transaction():
            candidates = [item for item in self.storage.list_cartridges()
                          if item['status'] == 'На заправке']
            prepared = []
            for item in candidates:
                sending = next((entry for entry in self.storage.list_history(item['id'])
                                if entry['action'] == ACTION_NAMES['send']), None)
                if sending is None:
                    continue
                try:
                    sent_at = datetime.fromisoformat(sending['recorded_at'])
                except (TypeError, ValueError):
                    raise ValidationError('Время отправления в журнале повреждено.') from None
                if sent_at.tzinfo is None:
                    raise ValidationError('Время отправления в журнале не содержит часовой пояс.')
                if current >= sent_at + LOST_AFTER:
                    operation_date = max(current.date().isoformat(), item['operation_date'])
                    prepared.append((item, operation_date, (sent_at + LOST_AFTER).astimezone().isoformat()))
            for item, operation_date, deadline in prepared:
                record = dict(item, status='Утерян', operation_date=operation_date)
                self.storage.update_cartridge(item['id'], {
                    'status': 'Утерян', 'operation_date': operation_date,
                })
                self._history(record, 'lost', item['status'], operation_date,
                              details={'deadline': deadline, 'automatic': True})
                changed.append(record)
        return changed

    def edit(self, id, name, printers=''):
        name = _text(name, 'Наименование картриджа', required=True)
        printers = _text(printers, 'Подходящие принтеры')
        with self.storage.transaction():
            previous = self.get(id)
            if previous['status'] == 'Списан':
                raise ValidationError('Списанный картридж нельзя редактировать.',
                                      error_codes.WRITTEN_OFF_ACTION_BLOCKED)
            if previous['name'] == name and previous['printers'] == printers:
                return previous
            operation_date = max(date.today().isoformat(), previous['operation_date'])
            fields = {'name': name, 'printers': printers, 'operation_date': operation_date}
            self._ensure_catalog_value('model', name)
            for printer in self._printer_names(printers):
                self._ensure_catalog_value('printer', printer)
            record = dict(previous, **fields)
            self.storage.update_cartridge(previous['id'], fields)
            self._history(record, 'edit', previous['status'], operation_date, details={
                'old': {'name': previous['name'], 'printers': previous['printers']},
                'new': {'name': name, 'printers': printers},
            })
        return record

    @staticmethod
    def _printer_names(value):
        return [part.strip() for part in re.split(r'[,;\n]+', value) if part.strip()]

    def _ensure_catalog_value(self, kind, name):
        if name.casefold() not in {value.casefold() for value in self.storage.list_catalog(kind)}:
            self.storage.add_catalog_name(kind, name)

    def catalogs(self):
        return {'models': self.storage.list_catalog('model'),
                'printers': self.storage.list_catalog('printer')}

    def add_catalog_name(self, kind, name):
        return self._catalog_mutation('add', kind, name)

    def rename_catalog_name(self, kind, old_name, new_name):
        old_name = _text(old_name, 'Наименование', required=True)
        new_name = _text(new_name, 'Наименование', required=True)
        if kind not in ('model', 'printer'):
            raise ValidationError('Неизвестный справочник.')
        with self.storage.transaction():
            names = self.storage.list_catalog(kind)
            if old_name not in names:
                raise ValidationError('Наименование не найдено в справочнике.',
                                      error_codes.CATALOG_NAME_NOT_FOUND)
            if new_name != old_name and new_name.casefold() in {value.casefold() for value in names}:
                raise ValidationError('Такое наименование уже есть в справочнике.')
            self.storage.rename_catalog_name(kind, old_name, new_name)
        return new_name

    def delete_catalog_name(self, kind, name):
        name = _text(name, 'Наименование', required=True)
        if kind not in ('model', 'printer'):
            raise ValidationError('Неизвестный справочник.')
        with self.storage.transaction():
            if name not in self.storage.list_catalog(kind):
                raise ValidationError('Наименование не найдено в справочнике.',
                                      error_codes.CATALOG_NAME_NOT_FOUND)
            self.storage.delete_catalog_name(kind, name)

    def _catalog_mutation(self, action, kind, name):
        name = _text(name, 'Наименование', required=True)
        if kind not in ('model', 'printer'):
            raise ValidationError('Неизвестный справочник.')
        with self.storage.transaction():
            if name.casefold() in {value.casefold() for value in self.storage.list_catalog(kind)}:
                raise ValidationError('Такое наименование уже есть в справочнике.')
            self.storage.add_catalog_name(kind, name)
        return name

    def merge_catalogs(self, payload):
        """Merge an exported catalog document; existing entries are never deleted."""
        if not isinstance(payload, dict) or payload.get('version') != 1:
            raise ValidationError('Формат файла справочника не поддерживается.')
        cleaned = {}
        for key, kind in (('models', 'model'), ('printers', 'printer')):
            values = payload.get(key)
            if not isinstance(values, list):
                raise ValidationError('В файле справочника отсутствует корректный список.')
            names = []
            seen = set()
            for value in values:
                name = _text(value, 'Наименование', required=True)
                if name.casefold() not in seen:
                    names.append(name)
                    seen.add(name.casefold())
            cleaned[kind] = names
        added = {'models': 0, 'printers': 0}
        with self.storage.transaction():
            for key, kind in (('models', 'model'), ('printers', 'printer')):
                existing = {name.casefold() for name in self.storage.list_catalog(kind)}
                for name in cleaned[kind]:
                    if name.casefold() not in existing:
                        self.storage.add_catalog_name(kind, name)
                        existing.add(name.casefold())
                        added[key] += 1
        return added

    def operate(self, id, action, operation_date, confirmed=False):
        if action not in TRANSITIONS:
            raise ValidationError('Неизвестная операция.')
        operation_date = _date(operation_date)
        if action == 'write_off' and confirmed is not True:
            raise ValidationError('Списание не подтверждено. Данные не изменены.')
        with self.storage.transaction():
            previous = self.get(id)
            target = TRANSITIONS[action].get(previous['status'])
            if target is None:
                raise ValidationError(f'Операция «{ACTION_NAMES[action]}» недоступна для статуса «{previous["status"]}».',
                                      self._transition_voice_code(action, previous['status']))
            if operation_date < previous['operation_date']:
                raise ValidationError(f'Дата операции не может быть раньше последней операции ({previous["operation_date"]}).',
                                      error_codes.INVALID_OPERATION_DATE)
            fields = {'status': target, 'operation_date': operation_date}
            record = dict(previous, **fields)
            self.storage.update_cartridge(previous['id'], fields)
            self._history(record, action, previous['status'], operation_date)
        return record

    def preview_transition(self, id, action, operation_date):
        """Validate one scanned item without changing the database."""
        if action not in ('send', 'receive', 'write_off'):
            raise ValidationError('Эта операция не поддерживает пакетное сканирование.')
        operation_date = _date(operation_date)
        previous = self.get(id)
        target = TRANSITIONS[action].get(previous['status'])
        if target is None:
            direction = {'send': 'отправление', 'receive': 'прибытие',
                         'write_off': 'списание'}[action]
            raise ValidationError(f"Операция «{direction}» недоступна для ID «{previous['id']}» со статусом «{previous['status']}».",
                                  self._transition_voice_code(action, previous['status']))
        if operation_date < previous['operation_date']:
            raise ValidationError(f"Дата операции не может быть раньше последней операции ({previous['operation_date']}).",
                                  error_codes.INVALID_OPERATION_DATE)
        return previous

    @staticmethod
    def _transition_voice_code(action, status):
        # Special terminal statuses take precedence over the generic action/status message.
        if status == 'Списан' and action in ('send', 'receive'):
            return error_codes.WRITTEN_OFF_ACTION_BLOCKED
        if status == 'Утерян' and action in ('send', 'receive', 'write_off'):
            return error_codes.LOST_ACTION_BLOCKED
        if action == 'send':
            return error_codes.DISPATCH_NOT_READY
        if action == 'receive':
            return error_codes.ARRIVAL_NOT_AT_REFILL
        return None

    def preview_receive(self, id, operation_date):
        return self.preview_transition(id, 'receive', operation_date)

    def preview_send(self, id, operation_date):
        return self.preview_transition(id, 'send', operation_date)

    def preview_write_off(self, id, operation_date):
        return self.preview_transition(id, 'write_off', operation_date)

    def _operate_many(self, ids, action, operation_date, confirmed=False):
        if not ids:
            raise ValidationError('Отсканируйте хотя бы один ID.')
        if action not in ('send', 'receive', 'write_off'):
            raise ValidationError('Эта операция не поддерживает пакетное сканирование.')
        if action == 'write_off' and confirmed is not True:
            raise ValidationError('Подтвердите списание партии. Данные не изменены.')
        normalized = [_text(value, 'ID', required=True) for value in ids]
        if len(set(normalized)) != len(normalized):
            raise ValidationError('В списке есть повторяющиеся ID.')
        operation_date = _date(operation_date)
        updated = []
        with self.storage.transaction():
            prepared = []
            for ident in normalized:
                previous = self.get(ident)
                target = TRANSITIONS[action].get(previous['status'])
                if target is None:
                    direction = {'send': 'отправление', 'receive': 'прибытие',
                                 'write_off': 'списание'}[action]
                    raise ValidationError(f"Операция «{direction}» недоступна для ID «{ident}» со статусом «{previous['status']}».",
                                          self._transition_voice_code(action, previous['status']))
                if operation_date < previous['operation_date']:
                    raise ValidationError(f"Для ID «{ident}» дата не может быть раньше последней операции ({previous['operation_date']}).",
                                          error_codes.INVALID_OPERATION_DATE)
                prepared.append((previous, target))
            for previous, target in prepared:
                record = dict(previous, status=target, operation_date=operation_date)
                self.storage.update_cartridge(previous['id'], {
                    'status': target, 'operation_date': operation_date,
                })
                self._history(record, action, previous['status'], operation_date)
                updated.append(record)
        return updated

    def receive_many(self, ids, operation_date):
        """Return a scanned batch to stock as one all-or-nothing transaction."""
        return self._operate_many(ids, 'receive', operation_date)

    def send_many(self, ids, operation_date):
        """Send a scanned batch for refill as one all-or-nothing transaction."""
        return self._operate_many(ids, 'send', operation_date)

    def write_off_many(self, ids, operation_date, confirmed=False):
        """Write off a scanned batch after one explicit batch confirmation."""
        return self._operate_many(ids, 'write_off', operation_date, confirmed=confirmed)

    def profile(self):
        return self.storage.get_profile()

    def save_profile(self, organization, full_name):
        organization = _text(organization, 'Организация')
        full_name = _text(full_name, 'ФИО')
        with self.storage.transaction():
            self.storage.save_profile(organization, full_name)

    def history(self, id=None):
        if id is not None:
            id = _text(id, 'ID', required=True)
            if self.storage.get_cartridge(id) is None:
                raise ValidationError(f'Картридж с ID «{id}» не найден.', error_codes.CARTRIDGE_NOT_FOUND)
        return self.storage.list_history(id)

    def backup(self, path):
        return self.storage.backup(path)

    def restore(self, path):
        return self.storage.restore(path)
