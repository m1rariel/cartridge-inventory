"""SQLite storage, isolated from UI and business rules.

Every mutation belongs to an explicit transaction owned by the service. Backups
are consistent SQLite snapshots, never raw copies of an open database.
"""
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
import os
import sqlite3
import tempfile
import uuid

APPLICATION_ID = 0x43415254
SCHEMA_VERSION = 2
STATUSES = ('Готов', 'На заправке', 'Списан', 'Утерян')
CARTRIDGE_COLUMNS = ('id', 'name', 'printers', 'status', 'operation_date')
HISTORY_COLUMNS = ('cartridge_id', 'action', 'old_status', 'new_status',
                   'operation_date', 'recorded_at', 'organization', 'full_name',
                   'reason', 'details')
EXPECTED_COLUMNS = {
    'cartridges': CARTRIDGE_COLUMNS + ('removed_at',),
    'profile': ('id', 'organization', 'full_name'),
    'history': ('id',) + HISTORY_COLUMNS,
}
LEGACY_COLUMNS_V1 = {
    'cartridges': CARTRIDGE_COLUMNS,
    'profile': ('id', 'organization', 'full_name'),
    'history': ('id',) + HISTORY_COLUMNS,
}
SCHEMA = """
CREATE TABLE cartridges (
 id TEXT PRIMARY KEY NOT NULL CHECK(typeof(id)='text' AND length(trim(id))>0),
 name TEXT NOT NULL CHECK(length(trim(name))>0),
 printers TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL CHECK(status IN ('Готов','На заправке','Списан','Утерян')),
 operation_date TEXT NOT NULL,
 removed_at TEXT
);
CREATE TABLE profile (
 id INTEGER PRIMARY KEY CHECK(id=1),
 organization TEXT NOT NULL DEFAULT '',
 full_name TEXT NOT NULL DEFAULT ''
);
INSERT INTO profile(id, organization, full_name) VALUES(1,'','');
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
"""


class Storage:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), isolation_level=None, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.execute('PRAGMA synchronous=FULL')
        try:
            tables = self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not tables and self.connection.execute('PRAGMA user_version').fetchone()[0] == 0:
                self.connection.executescript(
                    'BEGIN IMMEDIATE;\n' + SCHEMA +
                    '\nPRAGMA application_id=%d; PRAGMA user_version=%d; COMMIT;'
                    % (APPLICATION_ID, SCHEMA_VERSION))
            else:
                self._upgrade_legacy(self.connection)
            self._validate(self.connection)
        except BaseException:
            self.connection.close()
            raise

    @contextmanager
    def transaction(self):
        if self.connection.in_transaction:
            raise RuntimeError('Вложенная транзакция не поддерживается.')
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield self
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def _require_transaction(self):
        if not self.connection.in_transaction:
            raise RuntimeError('Изменение данных требует транзакции.')

    def get_cartridge(self, id):
        row = self.connection.execute('SELECT * FROM cartridges WHERE id=?', (id,)).fetchone()
        return dict(row) if row is not None else None

    def list_cartridges(self):
        columns = ','.join(CARTRIDGE_COLUMNS)
        return [dict(row) for row in self.connection.execute(
            'SELECT ' + columns + ' FROM cartridges WHERE removed_at IS NULL ORDER BY id')]

    def remove_cartridge(self, id, removed_at):
        self._require_transaction()
        cursor = self.connection.execute(
            'UPDATE cartridges SET removed_at=? WHERE id=? AND removed_at IS NULL',
            (removed_at, id))
        if cursor.rowcount != 1:
            raise ValueError('Картридж с указанным ID не найден.')

    def insert_cartridge(self, record):
        self._require_transaction()
        if not isinstance(record['id'], str):
            raise ValueError('ID должен быть текстом.')
        self.connection.execute(
            'INSERT INTO cartridges(id,name,printers,status,operation_date) VALUES(?,?,?,?,?)',
            tuple(record[column] for column in CARTRIDGE_COLUMNS))

    def update_cartridge(self, id, fields):
        self._require_transaction()
        if not fields:
            return
        if not set(fields).issubset(set(CARTRIDGE_COLUMNS) - {'id'}):
            raise ValueError('Недопустимое поле изменения; ID неизменяем.')
        columns = list(fields)
        cursor = self.connection.execute(
            'UPDATE cartridges SET ' + ','.join(column + '=?' for column in columns) + ' WHERE id=?',
            tuple(fields[column] for column in columns) + (id,))
        if cursor.rowcount != 1:
            raise ValueError('Картридж с указанным ID не найден.')

    def get_profile(self):
        row = self.connection.execute('SELECT organization,full_name FROM profile WHERE id=1').fetchone()
        return dict(row)

    def save_profile(self, organization, full_name):
        self._require_transaction()
        self.connection.execute('UPDATE profile SET organization=?,full_name=? WHERE id=1',
                                (organization, full_name))

    def add_history(self, record):
        self._require_transaction()
        values = dict(record)
        for key in ('reason', 'details', 'organization', 'full_name'):
            values.setdefault(key, '')
        self.connection.execute('INSERT INTO history(' + ','.join(HISTORY_COLUMNS) +
                                ') VALUES(' + ','.join('?' for _ in HISTORY_COLUMNS) + ')',
                                tuple(values[column] for column in HISTORY_COLUMNS))

    def list_history(self, cartridge_id=None):
        sql, args = 'SELECT * FROM history', ()
        if cartridge_id is not None:
            sql += ' WHERE cartridge_id=?'
            args = (cartridge_id,)
        return [dict(row) for row in self.connection.execute(sql + ' ORDER BY id DESC', args)]

    @staticmethod
    def _validate(connection):
        """Reject foreign, corrupt and unsupported databases before changing live data."""
        if connection.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID:
            raise ValueError('Файл не является резервной копией приложения «Учёт картриджей».')
        if connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
            raise ValueError('Версия базы данных не поддерживается этой версией программы.')
        if [row[0] for row in connection.execute('PRAGMA integrity_check')] != ['ok']:
            raise ValueError('База данных повреждена. Восстановление отменено.')
        for table, expected in EXPECTED_COLUMNS.items():
            actual = tuple(row[1] for row in connection.execute('PRAGMA table_info(' + table + ')'))
            if actual != expected:
                raise ValueError('Структура базы данных не соответствует приложению.')
        objects = connection.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        allowed = {('table', name) for name in EXPECTED_COLUMNS} | {('index', 'history_cartridge')}
        if any(tuple(row) not in allowed for row in objects):
            raise ValueError('База данных содержит неподдерживаемые объекты.')
        if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('В базе нарушены связи журнала и картриджей.')
        profile = connection.execute('SELECT id,organization,full_name FROM profile').fetchall()
        if len(profile) != 1 or profile[0][0] != 1 or not all(isinstance(x, str) for x in profile[0][1:]):
            raise ValueError('Профиль в базе данных повреждён.')
        for row in connection.execute('SELECT id,name,printers,status,operation_date,removed_at FROM cartridges'):
            if (not all(isinstance(value, str) for value in row[:5]) or not row[0].strip()
                    or not row[1].strip() or row[3] not in STATUSES):
                raise ValueError('Некорректная запись картриджа в базе данных.')
            Storage._validate_date(row[4])
            if row[5] is not None:
                try:
                    timestamp = datetime.fromisoformat(row[5])
                    if timestamp.tzinfo is None:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise ValueError('Некорректное время удаления картриджа.') from None
        for row in connection.execute('SELECT old_status,new_status,operation_date,recorded_at FROM history'):
            if row[0] is not None and row[0] not in STATUSES or row[1] not in STATUSES:
                raise ValueError('Некорректный статус в журнале.')
            Storage._validate_date(row[2])
            try:
                timestamp = datetime.fromisoformat(row[3])
                if timestamp.tzinfo is None:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError('Некорректное время записи в журнале.') from None

    @staticmethod
    def _upgrade_legacy(connection):
        """Apply the known v1→v2 soft-removal migration without replacing user data."""
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version != 1 or connection.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID:
            raise ValueError('Версия базы данных не поддерживается этой версией программы.')
        for table, expected in LEGACY_COLUMNS_V1.items():
            actual = tuple(row[1] for row in connection.execute('PRAGMA table_info(' + table + ')'))
            if actual != expected:
                raise ValueError('Структура старой базы данных не соответствует приложению; миграция отменена.')
        objects = connection.execute(
            "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        allowed = {('table', name) for name in LEGACY_COLUMNS_V1} | {('index', 'history_cartridge')}
        if any(tuple(row) not in allowed for row in objects):
            raise ValueError('Старая база содержит неподдерживаемые объекты; миграция отменена.')
        if [row[0] for row in connection.execute('PRAGMA integrity_check')] != ['ok']:
            raise ValueError('База данных повреждена; миграция отменена.')
        if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('В базе нарушены связи журнала и картриджей; миграция отменена.')
        connection.execute('BEGIN IMMEDIATE')
        try:
            connection.execute('ALTER TABLE cartridges ADD COLUMN removed_at TEXT')
            connection.execute('PRAGMA user_version=%d' % SCHEMA_VERSION)
            Storage._validate(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _validate_date(value):
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError('Некорректная дата в базе данных.') from None

    def _check_idle(self):
        if self.connection.in_transaction:
            raise RuntimeError('Дождитесь завершения текущей операции.')

    def backup(self, destination):
        self._check_idle()
        destination = Path(destination).expanduser().resolve()
        if destination == self.path or (destination.exists() and os.path.samefile(destination, self.path)):
            raise ValueError('Нельзя записать резервную копию поверх рабочей базы.')
        if str(destination) in (str(self.path) + '-journal', str(self.path) + '-wal', str(self.path) + '-shm'):
            raise ValueError('Выберите другое имя резервной копии.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.cartridge-backup-', suffix='.sqlite3', dir=str(destination.parent))
        os.close(fd)
        try:
            with sqlite3.connect(temporary) as output:
                self.connection.backup(output)
                self._validate(output)
            # Explicitly close before replace: Windows disallows replacing open files.
            output.close()
            with open(temporary, 'rb') as snapshot:
                os.fsync(snapshot.fileno())
            os.replace(temporary, destination)
        finally:
            if 'output' in locals():
                output.close()
            if os.path.exists(temporary):
                os.unlink(temporary)
        return destination

    def restore(self, source):
        self._check_idle()
        source = Path(source).expanduser().resolve()
        if not source.is_file():
            raise ValueError('Файл резервной копии не найден.')
        if source == self.path or os.path.samefile(source, self.path):
            raise ValueError('Выберите резервную копию, а не текущую базу.')
        # Freeze source before validation, so a changing file cannot bypass checks.
        snapshot = sqlite3.connect(':memory:')
        try:
            incoming = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
            try:
                incoming.backup(snapshot)
            finally:
                incoming.close()
            self._upgrade_legacy(snapshot)
            self._validate(snapshot)
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            safety = self.path.parent / 'backups' / ('before-restore-' + stamp + '-' + uuid.uuid4().hex[:8] + '.sqlite3')
            self.backup(safety)
            # SQLite backup replaces destination within SQLite's own transaction:
            # readers never observe a partially copied database, including on failure.
            snapshot.backup(self.connection)
            self.connection.execute('PRAGMA foreign_keys=ON')
            return safety
        except sqlite3.DatabaseError as exc:
            raise ValueError('Не удалось восстановить резервную копию: ' + str(exc)) from exc
        finally:
            snapshot.close()

    def close(self):
        self.connection.close()
