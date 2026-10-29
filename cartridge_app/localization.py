"""Translations for static application UI. User supplied text stays untouched."""
from datetime import date, datetime
from datetime import datetime
import re


EN = {
    'Учёт картриджей': 'Cartridge inventory',
    'Локальный склад • Каждый ID — отдельный физический экземпляр': 'Local inventory • Each ID is a separate physical item',
    '← Главное меню': '← Main menu', 'Профиль': 'Profile', 'Настройки': 'Settings',
    'Все права защищены.': 'All rights reserved.', 'All rights reserved.': 'All rights reserved.',
    'Открыть настройки': 'Open settings', 'Выбрать цвет': 'Choose color',
    'Установить этот фон': 'Use this background',
    'Размер текста должен быть от 9 до 24.': 'Text size must be between 9 and 24.',
    'База SQLite': 'SQLite database', 'Все файлы': 'All files', 'Резервная копия': 'Backup',
    'Картриджи-': 'Cartridges-', 'Склад-': 'Inventory-',
    'Экземпляров в списке: {count}': 'Items in list: {count}', '{old} → Списан': '{old} → Written off',
    'Работает без интернета. Изменения сохраняются после подтверждения.': 'Works offline. Changes are saved after confirmation.',
    'Склад': 'Inventory', 'Отправление': 'Dispatch', 'Прибытие': 'Return', 'Списание': 'Write-off',
    'Поиск по ID и наименованию. Нажмите заголовок столбца для сортировки.': 'Search by ID or name. Select a column heading to sort.',
    'Поиск': 'Search', 'Все статусы': 'All statuses', 'Готов': 'Ready', 'На заправке': 'Refilling', 'Списан': 'Written off', 'Утерян': 'Lost',
    '+ Добавить': '+ Add item', 'ID': 'ID', 'Наименование картриджа': 'Cartridge name', 'Подходящие принтеры': 'Compatible printers', 'Статус': 'Status', 'Дата': 'Date',
    'Редактировать': 'Edit', 'История': 'History', 'Экспорт списка в XLSX': 'Export list to XLSX',
    'Список пуст. Добавьте картридж или измените условия поиска.': 'No items found. Add a cartridge or change your search.',
    'Выберите экземпляр': 'Select an item', 'Сначала выберите строку в таблице.': 'Select a row in the table first.',
    'Редактирование экземпляра': 'Edit item', 'Новый экземпляр': 'New item', 'Наименование': 'Name',
    'ID *': 'ID *', 'Наименование *': 'Name *', '* Обязательные поля. ID после создания не меняется.\nНаименование и принтеры меняются только у этого экземпляра.': '* Required fields. ID cannot be changed after creation.\nName and printers apply only to this item.',
    'Отмена': 'Cancel', 'Сохранить': 'Save', 'Неизвестная операция.': 'Unknown operation.',
    'Сканируйте ID картриджей, возвращённых из заправки.': 'Scan IDs of cartridges returned from refill.',
    'Сканируйте ID картриджей, отправляемых на заправку.': 'Scan IDs of cartridges being sent for refill.',
    'Сканируйте ID картриджей, которые нужно списать.': 'Scan IDs of cartridges to write off.',
    ' Каждый ID добавляется в список по Enter; после сканирования подтвердите всю партию одной кнопкой.': ' Press Enter after each ID to stage it; confirm the whole batch with one button when scanning is complete.',
    'Принять партию в склад': 'Accept batch into inventory', 'Отправить партию на заправку': 'Send batch for refill', 'Списать партию': 'Write off batch',
    'Дата операции (ГГГГ-ММ-ДД)': 'Operation date (YYYY-MM-DD)', 'Сканируйте ID': 'Scan ID', 'Ожидание сканирования.': 'Ready to scan.',
    'Дата операции (ДД.ММ.ГГГГ)': 'Operation date (MM/DD/YYYY)',
    'Введите дату в формате ДД.ММ.ГГГГ.': 'Enter the date as MM/DD/YYYY.',
    'В партии: 0': 'In batch: 0', 'В партии: {count}': 'In batch: {count}',
    'На заправке → Готов': 'Refilling → Ready', 'Готов → На заправке': 'Ready → Refilling',
    'Наименование картриджа': 'Cartridge name', 'Добавлен: {id} — {name}': 'Added: {id} — {name}',
    'Принято в склад: {count}. Статус экземпляров — «Готов».': 'Accepted into inventory: {count}. Items are now “Ready”.',
    'Отправлено на заправку: {count}. Статус экземпляров — «На заправке».': 'Sent for refill: {count}. Items are now “Refilling”.',
    'Списано экземпляров: {count}.': 'Items written off: {count}.',
    'Можно сканировать следующую партию.': ' You can scan the next batch.',
    'Организация и ФИО сохраняются в каждой новой записи журнала. Старые записи не меняются.': 'Organization and name are saved with each new history entry. Older entries do not change.',
    'Организация': 'Organization', 'ФИО': 'Full name', 'Сохранить профиль': 'Save profile', 'Данные профиля сохранены.': 'Profile saved.',
    'База данных: ': 'Database: ', 'Создать резервную копию': 'Create backup', 'Восстановить из копии': 'Restore backup', 'Открыть журнал всех операций': 'Open full history',
    'Сохранить резервную копию': 'Save backup', 'Копия сохранена:\n': 'Backup saved:\n', 'Выберите резервную копию': 'Select a backup',
    'Текущие данные будут заменены содержимым выбранной копии, включая профиль и журнал. Перед заменой будет сохранена страховочная копия.\n\nПродолжить?': 'Current data, including profile and history, will be replaced by the selected backup. A safety copy will be created first.\n\nContinue?',
    'Восстановление базы': 'Restore database', 'Восстановление завершено': 'Restore complete', 'Данные восстановлены. Предыдущая база сохранена:\n': 'Data restored. Previous database saved to:\n',
    'Экспорт текущего списка': 'Export current list', 'Книга Excel': 'Excel workbook', 'Экспорт': 'Export', 'Экспортировано экземпляров: {count}\n{path}': 'Items exported: {count}\n{path}',
    'Журнал операций': 'Operation history', 'Журнал всех экземпляров. Выберите запись, чтобы прочитать полные сведения.': 'History for all items. Select an entry to see full details.',
    'Действие': 'Action', 'Было': 'Previous', 'Стало': 'New', 'Дата операции': 'Operation date', 'Время записи': 'Recorded at',
    'Записей: {count}. Выберите запись в таблице.': '{count} entries. Select a row in the table.', 'Операций пока нет.': 'No operations yet.',
    'Создание': 'Created', 'Редактирование': 'Edited', 'Изменения': 'Changes',
    'Не удалось прочитать или сохранить данные. Проверьте доступ к файлу и свободное место.\n\n{error}': 'Could not read or save data. Check file access and available space.\n\n{error}',
    'Не удалось выполнить действие. Данные не подтверждены; проверьте результат перед повтором.\n\n{error}': 'The action could not be completed. Changes were not confirmed; check the result before trying again.\n\n{error}',
    'Не удалось выполнить действие': 'Action failed', 'Списанный экземпляр нельзя редактировать.': 'A written-off item cannot be edited.',
    'ID «{id}» уже есть в этой партии.': 'ID “{id}” is already in this batch.', 'Изменение статуса': 'Status change',
    'Настройки': 'Settings', 'Оформление': 'Appearance', 'Язык': 'Language', 'Русский': 'Russian', 'Английский': 'English',
    'Светлая тема': 'Light theme', 'Тёмная тема': 'Dark theme', 'Включить светлую тему': 'Switch to light theme', 'Включить тёмную тему': 'Switch to dark theme',
    'Шрифт': 'Font', 'Размер текста': 'Text size', 'Сбросить размер': 'Reset size', 'Основной цвет': 'Accent color',
    'Цвет текста для светлой темы': 'Text color for light theme', 'Цвет текста для тёмной темы': 'Text color for dark theme',
    'Цвет текста имеет недостаточный контраст и может быть плохо читаем.': 'Text color contrast is too low and may be hard to read.',
    'Восстановить рекомендуемый цвет': 'Restore recommended color', 'Фон приложения': 'App background', 'Выбрать изображение': 'Choose image',
    'Заменить изображение': 'Replace image', 'Удалить пользовательский фон': 'Remove custom background', 'Стандартный фон': 'Default background',
    'Удалить со склада': 'Remove from inventory', 'Удалить картридж': 'Delete cartridge', 'Удаление со склада': 'Removal from inventory',
    'Убрать «{name}» (ID {id}) со склада? Экземпляр исчезнет из активного склада, но запись в журнале сохранится. ID повторно использовать нельзя.\n\nПродолжить?': 'Remove “{name}” (ID {id}) from inventory? The item will disappear from active inventory, but its history will be retained. The ID cannot be reused.\n\nContinue?',
    'Автоматически отмечены как утерянные ({count}): {ids}': 'Automatically marked as lost ({count}): {ids}',
    'Автоматическое признание утерянным': 'Automatically marked as lost',
    'Затемнение / осветление': 'Darken / lighten', 'Файл изображения': 'Image file', 'Предварительный просмотр': 'Preview',
    'JPEG, PNG или WebP, до 10 МБ, до 24 Мп. Изображение остаётся на этом компьютере.': 'JPEG, PNG or WebP, up to 10 MB and 24 MP. The image stays on this computer.',
    'О приложении': 'About', 'Сбросить настройки': 'Reset settings', 'Закрыть': 'Close', 'Применить': 'Apply',
    'ОК': 'OK', 'Продолжить': 'Continue',
    'Экземпляр недоступен': 'Item unavailable',
    'Не удалось запустить приложение': 'Could not start the application',
    'Проверьте доступ к каталогу данных. Существующие данные не удалены.\n\n': 'Check access to the data folder. Existing data has not been deleted.\n\n',
    'Сброс настроек': 'Reset settings', 'Настройки темы, оформления, языка и фона будут сброшены. Данные склада, профиль и журнал останутся без изменений.\n\nПродолжить?': 'Theme, appearance, language and background settings will be reset. Inventory, profile and history will remain unchanged.\n\nContinue?',
    'Настройки сохранены.': 'Settings saved.', 'Настройки сброшены.': 'Settings reset.', 'Не удалось сохранить настройку: {error}': 'Could not save setting: {error}',
    'Не удалось отобразить фон: {error}': 'Could not display background: {error}', 'Поддерживаемые изображения': 'Supported images',
    'Нет пользовательского фона.': 'No custom background selected.', 'Показывать фон мягко': 'Soften the background',
}


def tr(language, key, **values):
    """Translate a static UI phrase; never pass user supplied content as key."""
    phrase = EN.get(key, key) if language == 'en' else key
    try:
        return phrase.format(**values)
    except (KeyError, ValueError):
        return phrase


def format_date(value, language):
    """Format a date while preserving arbitrary invalid or user-entered text."""
    try:
        parsed = date.fromisoformat(str(value))
        return parsed.strftime('%m/%d/%Y' if language == 'en' else '%d.%m.%Y')
    except (TypeError, ValueError):
        return str(value)


def parse_date_input(value, language):
    """Accept locale display format and ISO dates; return the service's ISO form."""
    raw = str(value).strip()
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        pattern = '%m/%d/%Y' if language == 'en' else '%d.%m.%Y'
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            raise ValueError(tr(language, 'Введите дату в формате ДД.ММ.ГГГГ.')) from None


def format_number(value, language):
    """Locale-aware grouping for counts and numeric labels."""
    try:
        rendered = format(value, ',')
        return rendered.replace(',', '\u202f' if language == 'ru' else ',')
    except (TypeError, ValueError):
        return str(value)


def status_label(language, value):
    return tr(language, value)


def status_value(language, label):
    # Normalize either UI language back to the service's stable Russian status values.
    if label in ('Все статусы', 'Готов', 'На заправке', 'Списан', 'Утерян'):
        return label
    return next((ru for ru in ('Все статусы', 'Готов', 'На заправке', 'Списан', 'Утерян')
                 if EN.get(ru) == label), label)


def translate_error(language, error):
    """Translate application validation/storage messages, keeping user values as-is."""
    source = str(error)
    if language != 'en':
        return source
    exact = {
        'Такой даты не существует. Проверьте день, месяц и год.': 'This date does not exist. Check the day, month and year.',
        'Укажите дату в формате ГГГГ-ММ-ДД, например 2026-10-28.': 'Enter a date as YYYY-MM-DD, for example 2026-10-28.',
        'Списанный картридж нельзя редактировать.': 'A written-off cartridge cannot be edited.',
        'Списанный экземпляр нельзя редактировать.': 'A written-off item cannot be edited.',
        'Выбран неизвестный статус.': 'The selected status is not recognized.',
        'Неизвестный столбец сортировки.': 'The selected sort column is not recognized.',
        'Списание не подтверждено. Данные не изменены.': 'Write-off was not confirmed. No data was changed.',
        'Подтвердите списание партии. Данные не изменены.': 'Confirm the write-off batch. No data was changed.',
        'Эта операция не поддерживает пакетное сканирование.': 'This operation does not support batch scanning.',
        'Отсканируйте хотя бы один ID.': 'Scan at least one ID.',
        'В списке есть повторяющиеся ID.': 'The list contains duplicate IDs.',
        'Неизвестная операция.': 'Unknown operation.',
        'Выберите шрифт из списка.': 'Choose a font from the list.',
        'Неизвестная тема.': 'Unknown theme.',
        'Неизвестный язык.': 'Unknown language.',
        'Неизвестный режим фона.': 'Unknown background mode.',
        'Не удалось прочитать или сохранить данные. Проверьте доступ к файлу и свободное место.': 'Could not read or save data. Check file access and available space.',
        'Поддержка фоновых изображений недоступна в этой сборке. Обратитесь к администратору приложения.': 'Background image support is not available in this build. Contact your application administrator.',
        'Не удалось прочитать выбранный файл.': 'Could not read the selected file.',
        'Выберите непустой файл изображения.': 'Select a non-empty image file.',
        'Размер изображения превышает 10 МБ.': 'The image exceeds 10 MB.',
        'Поддерживаются только JPEG, PNG и WebP.': 'Only JPEG, PNG and WebP images are supported.',
        'Разрешение изображения не должно превышать 6000 × 6000.': 'Image dimensions must not exceed 6000 × 6000.',
        'Изображение слишком большое (максимум 24 мегапикселя).': 'The image is too large (maximum 24 megapixels).',
        'Файл изображения повреждён.': 'The image file is damaged.',
        'Файл повреждён или не является поддерживаемым изображением.': 'The file is damaged or is not a supported image.',
        'Файл изменился во время сохранения. Выберите его ещё раз.': 'The file changed while it was being saved. Select it again.',
        'Не удалось открыть сохранённое фоновое изображение.': 'Could not open the saved background image.',
        'Файл фона не найден в хранилище приложения.': 'The background file was not found in the app storage.',
    }
    if source in exact:
        return exact[source]
    patterns = (
        (r'^Картридж с ID «(.*)» не найден\.$', 'Cartridge with ID “{}” was not found.'),
        (r'^Картридж с ID «(.*)» уже существует\. Введите другой ID\.$', 'Cartridge with ID “{}” already exists. Enter another ID.'),
        (r'^Дата операции не может быть раньше последней операции \((.*)\)\.$', 'The operation date cannot be earlier than the last operation ({}).'),
        (r'^Для ID «(.*)» дата не может быть раньше последней операции \((.*)\)\.$', 'For ID “{}”, the date cannot be earlier than the last operation ({}).'),
        (r'^Поле «(.*)» должно быть текстом\.$', 'Field “{}” must be text.'),
        (r'^Заполните поле «(.*)»\.$', 'Fill in “{}”.'),
        (r'^Поле «(.*)» содержит недопустимые управляющие символы\.$', 'Field “{}” contains invalid control characters.'),
        (r'^Поле «(.*)» слишком длинное \(максимум (.*) символов\)\.$', 'Field “{}” is too long (maximum {} characters).'),
        (r'^Неизвестная настройка: (.*)$', 'Unknown preference: {}'),
        (r'^Значение подложки должно быть от −80 до 80\.$', 'Overlay value must be between −80 and 80.'),
        (r'^Цвет должен быть в формате #RRGGBB\.$', 'Color must use the #RRGGBB format.'),
        (r'^Операция «(.*)» недоступна для статуса «(.*)»\.$', 'Operation “{}” is not available for status “{}”.'),
        (r'^Операция «(.*)» недоступна для ID «(.*)» со статусом «(.*)»\.$', 'Operation “{}” is not available for ID “{}” with status “{}”.'),
        (r'^ID «(.*)» уже есть в этой партии\.$', 'ID “{}” is already in this batch.'),
    )
    for pattern, template in patterns:
        match = re.match(pattern, source)
        if match:
            values = list(match.groups())
            translations = {'Отправление': 'Dispatch', 'отправление': 'dispatch', 'Прибытие': 'Return', 'прибытие': 'return',
                            'Списание': 'Write-off', 'списание': 'write-off', 'Готов': 'Ready', 'На заправке': 'Refilling',
                            'Списан': 'Written off', 'Утерян': 'Lost', 'ID': 'ID', 'Наименование картриджа': 'Cartridge name',
                            'Подходящие принтеры': 'Compatible printers', 'Поиск': 'Search'}
            values = [translations.get(value, value) for value in values]
            return template.format(*values)
    return source
