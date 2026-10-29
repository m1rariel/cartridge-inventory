"""Русский интерфейс автономного учёта картриджей."""
import json
import os
import sqlite3
import sys
import webbrowser
import tkinter as tk
from datetime import date
from tkinter import filedialog, ttk

from .adaptivity import bind_wraplength, configure_window, fit_dialog
from .clipboard import install_clipboard_shortcuts
from .localization import format_date, format_number, parse_date_input, status_label, status_value, tr, translate_error
from .paths import data_directory
from .preferences import PreferencesStore
from .image_store import ImageStore
from .settings_dialog import SettingsDialog
from . import visual as visual_theme
from .visual import COLORS, SPACING, apply_visual_settings, transition_label
from .xlsx import export_inventory


class App:
    STATUSES = ('Все статусы', 'Готов', 'На заправке', 'Списан', 'Утерян')
    COLUMNS = ('id', 'name', 'printers', 'status', 'operation_date')
    HEADINGS = ('ID', 'Наименование картриджа', 'Подходящие принтеры', 'Статус', 'Дата')

    def __init__(self, root, service, preferences=None, image_store=None):
        self.root, self.service = root, service
        install_clipboard_shortcuts(root)
        directory = data_directory()
        self.preferences = preferences or PreferencesStore(directory)
        self.settings = self.preferences.load()
        self.image_store = image_store or ImageStore(directory)
        self.language = self.settings.language
        self.current_screen = 'main'
        self._bg_photo = None
        self._bg_timer = None
        self._batch_work = {}
        self._batch_dates = {}
        root.title(self.t('Учёт картриджей'))
        configure_window(root, initial=(1080, 720), minimum=(640, 480),
                         maximize=(sys.platform == 'win32'))
        apply_visual_settings(root, self.settings)
        root.report_callback_exception = self._callback_error
        self.background = tk.Canvas(root, bd=0, highlightthickness=0, takefocus=False,
                                    background=COLORS['background'])
        self.background.place(x=0, y=0, relwidth=1, relheight=1)
        self.background.bind('<Configure>', self._background_resized, add='+')
        self.body = ttk.Frame(root, padding=SPACING['page'])
        # Tk child widgets are opaque; this reveals the separate image layer in the window gutter.
        self.body.pack(fill='both', expand=True, padx=12, pady=12)
        self.apply_background(report_error=False)
        self.show_main()
        self._lost_check_error_shown = False
        root.after_idle(self._check_overdue_lost)

    def t(self, text, **values):
        return tr(getattr(self, 'language', 'ru'), text, **values)

    def show_error(self, error, parent=None):
        self.show_dialog(self.t('Не удалось выполнить действие'),
                         translate_error(getattr(self, 'language', 'ru'), error),
                         kind='error', parent=parent)

    def show_dialog(self, title, text, kind='info', parent=None):
        """Show an in-app themed modal instead of an OS-colored message box."""
        owner = parent or self.root
        previous_grab = owner.grab_current()
        window = tk.Toplevel(owner)
        window.title(title)
        window.transient(owner)
        _width, height = fit_dialog(window, self.root, size=(560, 280), minimum=(300, 240))
        window.resizable(False, False)
        frame = ttk.Frame(window, style='Content.TFrame', padding=SPACING['xl'])
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        label_style = 'ContentError.TLabel' if kind == 'error' else 'Content.TLabel'
        message = ttk.Label(frame, text=text, style=label_style, wraplength=max(240, min(500, self.root.winfo_screenwidth() - 100)), justify='left')
        message.grid(row=0, column=0, sticky='ew', pady=(0, 18))
        result = {'confirmed': False}

        def close(confirmed=False):
            result['confirmed'] = confirmed
            try:
                window.grab_release()
                window.destroy()
            except tk.TclError:
                pass
            if previous_grab is not None:
                try:
                    if previous_grab.winfo_exists():
                        previous_grab.grab_set()
                except tk.TclError:
                    pass

        actions = ttk.Frame(frame, style='Content.TFrame')
        actions.grid(row=1, column=0, sticky='e')
        if kind == 'confirm':
            cancel = ttk.Button(actions, text=self.t('Отмена'), command=lambda: close(False))
            cancel.pack(side='left', padx=(0, 8))
            cancel.bind('<Return>', lambda _event: (close(False), 'break')[1])
        accept = ttk.Button(actions, text=self.t('Продолжить') if kind == 'confirm' else self.t('ОК'),
                            command=lambda: close(kind == 'confirm'), style='Primary.TButton')
        accept.pack(side='left')
        accept.bind('<Return>', lambda _event: (close(kind == 'confirm'), 'break')[1])
        window.protocol('WM_DELETE_WINDOW', lambda: close(False))
        window.bind('<Escape>', lambda _event: (close(False), 'break')[1])
        window.grab_set()
        accept.focus_set()
        self.root.wait_window(window)
        return result['confirmed']

    def ask_confirmation(self, title, text, parent=None):
        return self.show_dialog(title, text, kind='confirm', parent=parent)

    def open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception as error:
            self.show_error(error)

    def save_preferences(self, **changes):
        old_language = self.language
        try:
            saved = self.preferences.update(**changes)
        except Exception as error:
            self.show_error(self.t('Не удалось сохранить настройку: {error}', error=translate_error(self.language, error)))
            return False
        self.settings = saved
        self.language = saved.language
        if 'background_overlay' in changes:
            self._preview_overlay_value = saved.background_overlay
        apply_visual_settings(self.root, saved)
        self.root.configure(background=COLORS['background'])
        if 'background_filename' in changes or 'background_mode' in changes or 'background_overlay' in changes:
            self.apply_background()
        if old_language != self.language:
            self.root.title(self.t('Учёт картриджей'))
            self._rebuild_current_page()
        return True

    def reset_preferences(self):
        self.settings = self.preferences.reset()
        self.language = self.settings.language
        self._preview_overlay_value = self.settings.background_overlay
        apply_visual_settings(self.root, self.settings)
        self.root.configure(background=COLORS['background'])
        self.apply_background()
        self.root.title(self.t('Учёт картриджей'))
        self._rebuild_current_page()

    def open_settings(self, return_focus=None):
        SettingsDialog(self, return_focus)

    def _check_overdue_lost(self):
        try:
            changed = self.service.mark_overdue_lost()
            self._lost_check_error_shown = False
            if changed:
                if self.current_screen == 'warehouse':
                    self.refresh()
                elif self.current_screen == 'history':
                    self.show_history()
                ids = ', '.join(item['id'] for item in changed)
                self.show_dialog(
                    self.t('Автоматически отмечены как утерянные ({count}): {ids}',
                           count=format_number(len(changed), self.language), ids=ids))
        except Exception as error:
            if not self._lost_check_error_shown:
                self._lost_check_error_shown = True
                self._error(error)
        finally:
            try:
                self._lost_check_timer = self.root.after(60_000, self._check_overdue_lost)
            except tk.TclError:
                pass

    def _rebuild_current_page(self):
        screen = self.current_screen
        if screen == 'warehouse':
            query = self.query.get() if hasattr(self, 'query') else ''
            status = self.status.get() if hasattr(self, 'status') else self.t('Все статусы')
            self.show_warehouse()
            self.query.set(query)
            self.status.set(self.t(status_value(self.language, status)))
            self.refresh()
        elif screen == 'operation' and hasattr(self, 'batch_action'):
            action = self.batch_action
            scanned = self.batch_scan.get()
            self.show_operation_batch(action)
            self.batch_scan.set(scanned)
        elif screen == 'profile':
            self.show_profile()
        elif screen == 'history':
            self.show_history()
        else:
            self.show_main()
        if getattr(self, 'current_screen', '') == 'main':
            self.settings_button = getattr(self, 'settings_button', None)

    def preview_background(self, filename, size):
        from PIL import ImageTk
        image = self.image_store.load_image(filename, size)
        return ImageTk.PhotoImage(image, master=self.root)

    def _background_resized(self, event=None):
        if self._bg_timer is not None:
            try:
                self.root.after_cancel(self._bg_timer)
            except tk.TclError:
                pass
        # Resizing is a routine startup/window event. A missing or temporarily
        # unreadable saved image should not open an error dialog on launch.
        self._bg_timer = self.root.after(180, lambda: self.apply_background(report_error=False))

    def apply_background(self, report_error=True):
        self.background.delete('all')
        self.background.configure(background=COLORS['background'])
        self._bg_photo = None
        try:
            self.root.tk.call('lower', str(self.background))
        except tk.TclError:
            pass
        if self.settings.background_mode != 'custom' or not self.settings.background_filename:
            return
        width = max(320, self.root.winfo_width())
        height = max(240, self.root.winfo_height())
        try:
            from PIL import Image, ImageTk
            source = self.image_store.load_image(self.settings.background_filename, (width, height))
            image = source.copy()
            image.thumbnail((width, height), Image.Resampling.LANCZOS)
            self._bg_photo = ImageTk.PhotoImage(image, master=self.root)
            self.background.create_image(width // 2, height // 2, image=self._bg_photo, anchor='center', tags=('background-image',))
            overlay = getattr(self, '_preview_overlay_value', self.settings.background_overlay)
            if overlay:
                amount = abs(overlay)
                density = ('gray12' if amount < 20 else 'gray25' if amount < 40
                           else 'gray50' if amount < 60 else 'gray75')
                self.background.create_rectangle(0, 0, width, height,
                    fill='#000000' if overlay > 0 else '#ffffff',
                    stipple=density, outline='',
                    tags=('background-overlay',))
            # Canvas is decorative only and remains behind the controls.
            self.root.tk.call('lower', str(self.background))
        except Exception as error:
            if report_error:
                self.show_error(self.t('Не удалось отобразить фон: {error}', error=translate_error(self.language, error)))

    def preview_overlay(self, value):
        self._preview_overlay_value = int(round(value))
        self.apply_background(report_error=False)

    def _callback_error(self, kind, error, traceback):
        self._error(error)

    def _error(self, error, parent=None):
        if isinstance(error, ValueError):
            text = translate_error(self.language, error)
        elif isinstance(error, (OSError, sqlite3.Error)):
            text = self.t('Не удалось прочитать или сохранить данные. Проверьте доступ к файлу и свободное место.\n\n{error}', error=translate_error(self.language, error))
        else:
            text = self.t('Не удалось выполнить действие. Данные не подтверждены; проверьте результат перед повтором.\n\n{error}', error=translate_error(self.language, error))
        self.show_dialog(self.t('Не удалось выполнить действие'), text, kind='error', parent=parent)

    def _page(self, title, subtitle=''):
        title, subtitle = self.t(title), self.t(subtitle) if subtitle else ''
        self.root.title(self.t('Учёт картриджей'))
        for child in self.body.winfo_children():
            child.destroy()
        top = ttk.Frame(self.body, style='Glass.TFrame', padding=(12, 9))
        top.pack(fill='x', pady=(0, 14))
        self.back_button = ttk.Button(top, text=self.t('← Главное меню'), command=self.show_main, style='Glass.TButton')
        self.back_button.pack(side='right')
        title_label = ttk.Label(top, text=title, style='GlassTitle.TLabel')
        title_label.pack(side='left')
        transition_label(self.root, title_label, title, 'GlassTitle.TLabel')
        if subtitle:
            self.subtitle_label = ttk.Label(self.body, text=subtitle, style='Muted.TLabel')
            bind_wraplength(self.root, self.subtitle_label, inset=64, minimum=240, maximum=820)
            self.subtitle_label.pack(anchor='w', pady=(0, 12))

    def show_main(self):
        self.current_screen = 'main'
        self._page('Учёт картриджей', 'Локальный склад • Каждый ID — отдельный физический экземпляр')
        header = self.body.winfo_children()[0]
        # Preserve the back button generated by _page and add profile/settings actions.
        self.back_button.destroy()
        controls = ttk.Frame(header, style='Glass.TFrame')
        controls.pack(side='right')
        ttk.Button(controls, text=self.t('Профиль'), command=self.show_profile, style='Glass.TButton').pack(side='left', padx=4)
        settings = ttk.Button(controls, text='⚙  ' + self.t('Настройки'), command=lambda: self.open_settings(settings), style='Glass.TButton',
                              takefocus=True)
        settings.pack(side='left', padx=(4, 0))
        settings.configure(cursor='hand2')
        settings.bind('<Enter>', lambda _e: self._set_tooltip(settings, self.t('Настройки')))
        settings.bind('<Leave>', lambda _e: self._hide_tooltip())
        settings.configure(takefocus=True)
        settings._accessible_name = self.t('Настройки')
        settings._accessible_description = self.t('Открыть настройки')
        self.settings_button = settings
        grid = ttk.Frame(self.body)
        grid.pack(fill='both', expand=True, pady=24)
        entries = [('Склад', self.show_warehouse), ('Отправление', lambda: self.show_operation('send')),
                   ('Прибытие', lambda: self.show_operation('receive')), ('Списание', lambda: self.show_operation('write_off'))]
        for i, (label, command) in enumerate(entries):
            ttk.Button(grid, text=self.t(label), command=command, style='Menu.TButton').grid(row=i // 2, column=i % 2, sticky='nsew', padx=12, pady=12)
        for i in range(2):
            grid.columnconfigure(i, weight=1)
            grid.rowconfigure(i, weight=1)
        ttk.Label(self.body, text=self.t('Работает без интернета. Изменения сохраняются после подтверждения.'), style='Muted.TLabel').pack(anchor='w')
        footer = ttk.Label(self.body, text=f"© {date.today().year} @m1rariel. {self.t('Все права защищены.') if self.language == 'ru' else self.t('All rights reserved.')}", style='Muted.TLabel', cursor='hand2')
        footer.pack(anchor='e', pady=(7, 0))
        footer.bind('<Button-1>', lambda _e: self.open_url('https://t.me/m1rariel'))
        footer.bind('<Return>', lambda _e: self.open_url('https://t.me/m1rariel'))

    def _set_tooltip(self, widget, text):
        self._hide_tooltip()
        x = widget.winfo_rootx() + widget.winfo_width() // 2
        y = widget.winfo_rooty() + widget.winfo_height() + 6
        self._tooltip = tk.Toplevel(self.root)
        self._tooltip.wm_overrideredirect(True)
        self._tooltip.wm_geometry(f'+{x}+{y}')
        ttk.Label(self._tooltip, text=text, style='Glass.TLabel', padding=(8, 4)).pack()

    def _hide_tooltip(self):
        tooltip = getattr(self, '_tooltip', None)
        if tooltip is not None:
            try:
                tooltip.destroy()
            except tk.TclError:
                pass
            self._tooltip = None

    def _table(self, parent, columns, headings, widths):
        frame = ttk.Frame(parent, style='Content.TFrame')
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        vertical = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=85, stretch=True)
        return tree

    def show_warehouse(self):
        self.current_screen = 'warehouse'
        self._page('Склад', 'Поиск по ID и наименованию. Нажмите заголовок столбца для сортировки.')
        bar = ttk.Frame(self.body, style='Glass.TFrame', padding=(10, 8))
        bar.pack(fill='x', pady=(0, 14))
        self.query = tk.StringVar(value=getattr(self, '_saved_query', ''))
        self.status = tk.StringVar(value=getattr(self, '_saved_status', self.t(self.STATUSES[0])))
        ttk.Label(bar, text=self.t('Поиск'), style='Glass.TLabel').pack(side='left', padx=(0, 8))
        ttk.Entry(bar, textvariable=self.query, width=20).pack(side='left', fill='x', expand=True)
        combo = ttk.Combobox(bar, textvariable=self.status,
                             values=[self.t(x) for x in self.STATUSES], state='readonly', width=14)
        combo.pack(side='left', padx=12)
        ttk.Button(bar, text=self.t('+ Добавить'), style='Primary.TButton', command=self.add_dialog).pack(side='right')
        self.sort_by, self.descending = 'id', False
        self.tree = self._table(self.body, self.COLUMNS, [self.t(x) for x in self.HEADINGS], (100, 250, 250, 150, 120))
        for col in self.COLUMNS:
            self.tree.heading(col, command=lambda c=col: self._sort(c))
        self.tree.bind('<Double-1>', lambda event: self.edit_dialog())
        self.empty_label = ttk.Label(self.body, style='Muted.TLabel')
        self.empty_label.pack(anchor='w', pady=10)
        actions = ttk.Frame(self.body, style='Glass.TFrame', padding=(8, 6))
        actions.pack(fill='x')
        ttk.Button(actions, text=self.t('Редактировать'), command=self.edit_dialog, style='Glass.TButton').pack(side='left')
        ttk.Button(actions, text=self.t('Удалить картридж'), command=self.remove_dialog,
                   style='Danger.TButton').pack(side='left', padx=(8, 0))
        ttk.Button(actions, text=self.t('История'), command=self.show_history, style='Glass.TButton').pack(side='left', padx=8)
        ttk.Button(actions, text=self.t('Экспорт списка в XLSX'), command=self.export, style='Glass.TButton').pack(side='right')
        self.query.trace_add('write', lambda *_: self.refresh())
        combo.bind('<<ComboboxSelected>>', lambda event: self.refresh())
        self.refresh()

    def _sort(self, column):
        self.descending = not self.descending if self.sort_by == column else False
        self.sort_by = column
        self.refresh()

    def refresh(self):
        try:
            self._saved_query = self.query.get()
            self._saved_status = self.status.get()
            raw_status = status_value(self.language, self.status.get())
            self.rows = self.service.list(query=self.query.get(), status='' if raw_status == self.STATUSES[0] else raw_status, sort_by=self.sort_by, descending=self.descending)
            for item in self.tree.get_children():
                self.tree.delete(item)
            for row in self.rows:
                values = [row.get(c, '') for c in self.COLUMNS]
                values[self.COLUMNS.index('status')] = status_label(self.language, values[self.COLUMNS.index('status')])
                values[self.COLUMNS.index('operation_date')] = format_date(values[self.COLUMNS.index('operation_date')], self.language)
                self.tree.insert('', 'end', values=values)
            self.empty_label.configure(text=self.t('Экземпляров в списке: {count}', count=format_number(len(self.rows), self.language)) if self.rows else self.t('Список пуст. Добавьте картридж или измените условия поиска.'))
            for col, label in zip(self.COLUMNS, self.HEADINGS):
                self.tree.heading(col, text=self.t(label) + ((' ▼' if self.descending else ' ▲') if col == self.sort_by else ''))
        except Exception as error:
            self._error(error)

    def _selected_id(self):
        selected = self.tree.selection()
        if not selected:
            self.show_dialog(self.t('Выберите экземпляр'), self.t('Сначала выберите строку в таблице.'))
            return None
        # Treeview coerces numeric-looking values on retrieval; keep original record identity.
        index = self.tree.index(selected[0])
        return self.rows[index]['id']

    def _dialog(self, title):
        win = tk.Toplevel(self.root)
        win.title(self.t(title))
        fit_dialog(win, self.root, size=(590, 390), minimum=(320, 300))
        win.grab_set()
        frame = ttk.Frame(win, style='Content.TFrame', padding=SPACING['xl'])
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        return win, frame

    def add_dialog(self):
        self._edit_form(None)

    def edit_dialog(self):
        ident = self._selected_id()
        if ident is None:
            return
        try:
            record = self.service.get(ident)
            if record['status'] == 'Списан':
                raise ValueError('Списанный экземпляр нельзя редактировать.')
            self._edit_form(record)
        except Exception as error:
            self._error(error)

    def remove_dialog(self):
        ident = self._selected_id()
        if ident is None:
            return
        try:
            record = self.service.get(ident)
            prompt = self.t(
                'Убрать «{name}» (ID {id}) со склада? Экземпляр исчезнет из активного склада, но запись в журнале сохранится. ID повторно использовать нельзя.\n\nПродолжить?',
                name=record['name'], id=record['id'])
            if not self.ask_confirmation(self.t('Удаление со склада'), prompt):
                return
            self.service.remove(record['id'])
            self.refresh()
        except Exception as error:
            self._error(error)

    def _edit_form(self, record):
        win, form = self._dialog('Редактирование экземпляра' if record else 'Новый экземпляр')
        values = {}
        for i, (field, label) in enumerate([('id', 'ID *'), ('name', 'Наименование *'), ('printers', 'Подходящие принтеры')]):
            ttk.Label(form, text=self.t(label), style='Content.TLabel').grid(row=i, column=0, sticky='w', padx=(0, 14), pady=10)
            values[field] = tk.StringVar(value=record.get(field, '') if record else '')
            entry = ttk.Entry(form, textvariable=values[field])
            entry.grid(row=i, column=1, sticky='ew', pady=10)
            if record and field == 'id':
                entry.configure(state='readonly')
            elif field == ('name' if record else 'id'):
                entry.focus_set()
        note = ttk.Label(form, text=self.t('* Обязательные поля. ID после создания не меняется.\nНаименование и принтеры меняются только у этого экземпляра.'), style='ContentMuted.TLabel', wraplength=max(240, min(490, self.root.winfo_screenwidth() - 120)))
        note.grid(row=3, column=0, columnspan=2, sticky='w', pady=18)
        def save():
            try:
                args = [values[k].get() for k in ('id', 'name', 'printers')]
                if record:
                    self.service.edit(*args)
                else:
                    self.service.add(*args)
                win.destroy()
                self.refresh()
            except Exception as error:
                self._error(error, win)
        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=2, sticky='e')
        ttk.Button(buttons, text=self.t('Отмена'), command=win.destroy).pack(side='left', padx=8)
        ttk.Button(buttons, text=self.t('Сохранить'), command=save, style='Primary.TButton').pack(side='left')
        win.bind('<Escape>', lambda event: win.destroy())
        win.bind('<Return>', lambda event: save())

    def show_operation(self, action):
        if action not in ('send', 'receive', 'write_off'):
            raise ValueError('Неизвестная операция.')
        self.show_operation_batch(action)

    def show_operation_batch(self, action):
        self.current_screen = 'operation'
        title = {'receive': 'Прибытие', 'send': 'Отправление', 'write_off': 'Списание'}[action]
        details = {
            'receive': 'Сканируйте ID картриджей, возвращённых из заправки.',
            'send': 'Сканируйте ID картриджей, отправляемых на заправку.',
            'write_off': 'Сканируйте ID картриджей, которые нужно списать.',
        }[action]
        submit_text = {
            'receive': 'Принять партию в склад',
            'send': 'Отправить партию на заправку',
            'write_off': 'Списать партию',
        }[action]
        self._page(title, self.t(details) + self.t(' Каждый ID добавляется в список по Enter; после сканирования подтвердите всю партию одной кнопкой.'))
        form = ttk.Frame(self.body, style='Glass.TFrame', padding=(SPACING['md'], SPACING['sm']))
        form.pack(fill='x', pady=(0, 12))
        form.columnconfigure(1, weight=1)
        self.batch_action = action
        staged_ids = list(getattr(self, '_batch_work', {}).get(action, []))
        operation_date = getattr(self, '_batch_dates', {}).get(action, date.today().isoformat())
        self.batch_date = tk.StringVar(value=format_date(operation_date, self.language))
        self.batch_date.trace_add('write', lambda *_: self._cache_batch_date(action))
        self.batch_scan = tk.StringVar()
        ttk.Label(form, text=self.t('Дата операции (ДД.ММ.ГГГГ)'), style='Glass.TLabel').grid(row=0, column=0, sticky='w', padx=(0, 16), pady=8)
        ttk.Entry(form, textvariable=self.batch_date, width=18).grid(row=0, column=1, sticky='w', pady=8)
        ttk.Label(form, text=self.t('Сканируйте ID'), style='Glass.TLabel').grid(row=1, column=0, sticky='w', padx=(0, 16), pady=8)
        scan_entry = ttk.Entry(form, textvariable=self.batch_scan)
        scan_entry.grid(row=1, column=1, sticky='ew', pady=8)
        scan_entry.bind('<Return>', self._scan_incoming)
        # Keep the operation form's geometry stable when feedback changes from
        # a short success message to a wrapped validation error (e.g. a repeat scan).
        feedback_area = ttk.Frame(form, style='Glass.TFrame', height=max(58, self.settings.font_size * 5))
        feedback_area.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(4, 8))
        feedback_area.grid_propagate(False)
        self.batch_feedback = ttk.Label(feedback_area, text=self.t('Ожидание сканирования.'),
                                        style='GlassMuted.TLabel', wraplength=800, anchor='w')
        self.batch_feedback.pack(fill='both', expand=True, anchor='w')
        bind_wraplength(self.root, self.batch_feedback, inset=64, minimum=240, maximum=800)
        self.batch_ids = staged_ids
        self.batch_tree = self._table(
            self.body, ('id', 'name', 'transition'),
            tuple(self.t(x) for x in ('ID', 'Наименование картриджа', 'Изменение статуса')), (150, 400, 220))
        self.batch_count = ttk.Label(self.body, text=self.t('В партии: 0'), style='Muted.TLabel')
        self.batch_count.pack(anchor='w', pady=8)
        for ident in staged_ids:
            try:
                record = self.service.get(ident)
                transition = {
                    'receive': self.t('На заправке → Готов'),
                    'send': self.t('Готов → На заправке'),
                    'write_off': self.t('{old} → Списан', old=status_label(self.language, record['status']))}[action]
                self.batch_tree.insert('', 'end', values=(record['id'], record['name'], transition))
            except Exception:
                # Keep the scanned ID visible even if the current database record is unavailable.
                self.batch_tree.insert('', 'end', values=(ident, self.t('Экземпляр недоступен'), ''))
        self.batch_count.configure(text=self.t('В партии: {count}', count=format_number(len(staged_ids), self.language)))
        self.batch_submit = ttk.Button(
            self.body, text=self.t(submit_text), style='Primary.TButton',
            state='normal' if staged_ids else 'disabled', command=self._commit_operation_batch)
        self.batch_submit.pack(anchor='w', pady=(4, 0))
        scan_entry.focus_set()

    def _scan_incoming(self, event=None):
        ident = self.batch_scan.get().strip()
        self.batch_scan.set('')
        if not ident:
            return 'break'
        try:
            if ident in self.batch_ids:
                raise ValueError(self.t('ID «{id}» уже есть в этой партии.', id=ident))
            record = self.service.preview_transition(ident, self.batch_action, self._operation_date())
            self.batch_ids.append(record['id'])
            if not hasattr(self, '_batch_work'):
                self._batch_work = {}
            if not hasattr(self, '_batch_dates'):
                self._batch_dates = {}
            self._batch_work.setdefault(self.batch_action, []).append(record['id'])
            self._batch_dates[self.batch_action] = self.batch_date.get()
            transition = {
                'receive': self.t('На заправке → Готов'),
                'send': self.t('Готов → На заправке'),
                'write_off': self.t('{old} → Списан', old=status_label(getattr(self, 'language', 'ru'), record['status'])),
            }[self.batch_action]
            self.batch_tree.insert('', 'end', values=(record['id'], record['name'], transition))
            self.batch_count.configure(text=self.t('В партии: {count}', count=format_number(len(self.batch_ids), getattr(self, 'language', 'ru'))))
            self.batch_submit.configure(state='normal')
            transition_label(self.root, self.batch_feedback,
                             self.t('Добавлен: {id} — {name}', id=record['id'], name=record['name']), 'GlassSuccess.TLabel')
        except Exception as error:
            transition_label(self.root, self.batch_feedback, translate_error(getattr(self, 'language', 'ru'), error), 'GlassError.TLabel')
        return 'break'

    def _commit_operation_batch(self):
        if not self.batch_ids:
            return
        try:
            count = len(self.batch_ids)
            if self.batch_action == 'receive':
                self.service.receive_many(list(self.batch_ids), self._operation_date())
            elif self.batch_action == 'send':
                self.service.send_many(list(self.batch_ids), self._operation_date())
            else:
                self.service.write_off_many(list(self.batch_ids), self._operation_date(), confirmed=True)
            for item in self.batch_tree.get_children():
                self.batch_tree.delete(item)
            self.batch_ids.clear()
            if hasattr(self, '_batch_work'):
                self._batch_work[self.batch_action] = []
            self.batch_count.configure(text=self.t('В партии: 0'))
            self.batch_submit.configure(state='disabled')
            result = {
                'receive': self.t('Принято в склад: {count}. Статус экземпляров — «Готов».', count=format_number(count, getattr(self, 'language', 'ru'))),
                'send': self.t('Отправлено на заправку: {count}. Статус экземпляров — «На заправке».', count=format_number(count, getattr(self, 'language', 'ru'))),
                'write_off': self.t('Списано экземпляров: {count}.', count=format_number(count, getattr(self, 'language', 'ru'))),
            }[self.batch_action]
            transition_label(self.root, self.batch_feedback,
                             result + self.t('Можно сканировать следующую партию.'), 'GlassSuccess.TLabel')
        except Exception as error:
            transition_label(self.root, self.batch_feedback, translate_error(getattr(self, 'language', 'ru'), error), 'GlassError.TLabel')

    def show_profile(self):
        self.current_screen = 'profile'
        self._page('Профиль', 'Организация и ФИО сохраняются в каждой новой записи журнала. Старые записи не меняются.')
        try:
            profile = self.service.profile()
        except Exception as error:
            self._error(error)
            return
        form = ttk.Frame(self.body, style='Content.TFrame', padding=(SPACING['md'], SPACING['sm']))
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        fields = []
        for i, (key, title) in enumerate([('organization', 'Организация'), ('full_name', 'ФИО')]):
            value = tk.StringVar(value=profile.get(key, ''))
            fields.append(value)
            ttk.Label(form, text=self.t(title), style='Content.TLabel').grid(row=i, column=0, sticky='w', padx=(0, 12), pady=4)
            ttk.Entry(form, textvariable=value).grid(row=i, column=1, sticky='ew', pady=4)
        def save():
            try:
                self.service.save_profile(*(v.get() for v in fields))
                self.show_dialog(self.t('Профиль'), self.t('Данные профиля сохранены.'))
            except Exception as error:
                self._error(error)
        ttk.Button(form, text=self.t('Сохранить профиль'), style='Primary.TButton', command=save).grid(row=2, column=1, sticky='w', pady=5)
        data_path = ttk.Label(self.body, text=self.t('База данных: ') + str(self.service.storage.path), style='Muted.TLabel')
        data_path.pack(anchor='w', pady=5)
        bind_wraplength(self.root, data_path, inset=64, minimum=240, maximum=820)
        bind_wraplength(self.root, data_path, inset=64, minimum=240, maximum=820)
        buttons = ttk.Frame(self.body, style='Glass.TFrame', padding=(SPACING['sm'], SPACING['xs']))
        buttons.pack(fill='x', pady=4)
        ttk.Button(buttons, text=self.t('Создать резервную копию'), command=self.backup, style='Glass.TButton').pack(side='left')
        ttk.Button(buttons, text=self.t('Восстановить из копии'), command=self.restore, style='Danger.TButton').pack(side='left', padx=10)
        ttk.Button(self.body, text=self.t('Открыть журнал всех операций'), command=self.show_history, style='Glass.TButton').pack(anchor='w', pady=12)

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self.root, title=self.t('Сохранить резервную копию'), defaultextension='.sqlite3', initialfile=self.t('Картриджи-') + date.today().isoformat() + '.sqlite3', filetypes=[(self.t('База SQLite'), '*.sqlite3')])
        if path:
            try:
                self.service.backup(path)
                self.show_dialog(self.t('Резервная копия'), self.t('Копия сохранена:\n') + path)
            except Exception as error:
                self._error(error)

    def restore(self):
        path = filedialog.askopenfilename(parent=self.root, title=self.t('Выберите резервную копию'), filetypes=[(self.t('База SQLite'), '*.sqlite3 *.db'), (self.t('Все файлы'), '*')])
        if not path:
            return
        if not self.ask_confirmation(self.t('Восстановление базы'), self.t('Текущие данные будут заменены содержимым выбранной копии, включая профиль и журнал. Перед заменой будет сохранена страховочная копия.\n\nПродолжить?')):
            return
        try:
            safety = self.service.restore(path)
            self.show_dialog(self.t('Восстановление завершено'), self.t('Данные восстановлены. Предыдущая база сохранена:\n') + str(safety))
            self.show_profile()
        except Exception as error:
            self._error(error)

    def export(self):
        path = filedialog.asksaveasfilename(parent=self.root, title=self.t('Экспорт текущего списка'), defaultextension='.xlsx', initialfile=self.t('Склад-') + date.today().isoformat() + '.xlsx', filetypes=[(self.t('Книга Excel'), '*.xlsx')])
        if path:
            try:
                export_inventory(self.rows, path, profile=self.service.profile())
                self.show_dialog(self.t('Экспорт'), self.t('Экспортировано экземпляров: {count}\n{path}', count=format_number(len(self.rows), self.language), path=path))
            except Exception as error:
                self._error(error)

    def show_history(self):
        self.current_screen = 'history'
        self._page('Журнал операций', 'Журнал всех экземпляров. Выберите запись, чтобы прочитать полные сведения.')
        try:
            rows = self.service.history()
        except Exception as error:
            self._error(error)
            return
        columns = ('cartridge_id', 'action', 'old_status', 'new_status', 'operation_date', 'recorded_at', 'organization', 'full_name')
        headings = tuple(self.t(x) for x in ('ID', 'Действие', 'Было', 'Стало', 'Дата операции', 'Время записи', 'Организация', 'ФИО'))
        tree = self._table(self.body, columns, headings, (100, 130, 130, 130, 140, 230, 160, 170))
        actions = {'add': self.t('Создание'), 'create': self.t('Создание'), 'Добавление': self.t('Создание'),
                   'edit': self.t('Редактирование'), 'Редактирование': self.t('Редактирование'),
                   'send': self.t('Отправление'), 'Отправление': self.t('Отправление'),
                   'receive': self.t('Прибытие'), 'Прибытие': self.t('Прибытие'),
                   'write_off': self.t('Списание'), 'Списание': self.t('Списание'),
                   'remove': self.t('Удаление со склада'), 'Удаление со склада': self.t('Удаление со склада'),
                   'lost': self.t('Автоматическое признание утерянным'),
                   'Автоматическое признание утерянным': self.t('Автоматическое признание утерянным')}
        for row in rows:
            values = []
            for column in columns:
                value = row.get(column) or '—'
                if column == 'action':
                    value = actions.get(value, value)
                elif column in ('old_status', 'new_status'):
                    value = status_label(self.language, value)
                elif column == 'operation_date':
                    value = format_date(value, self.language) if value != '—' else value
                elif column == 'recorded_at' and value != '—':
                    value = self._format_timestamp(value)
                values.append(value)
            tree.insert('', 'end', values=values)
        detail_frame = ttk.Frame(self.body, style='Content.TFrame', padding=(SPACING['sm'], SPACING['xs']))
        detail_frame.pack(fill='x', pady=(12, 0))
        details = tk.Text(detail_frame, height=6, wrap='word', font=visual_theme.FONT,
                          bg=COLORS['surface'], fg=COLORS['text'], insertbackground=COLORS['text'],
                          relief='flat', padx=10, pady=8, highlightthickness=1,
                          highlightbackground=COLORS['border'], highlightcolor=COLORS['focus'])
        detail_scroll = ttk.Scrollbar(detail_frame, orient='vertical', command=details.yview)
        details.configure(yscrollcommand=detail_scroll.set)
        details.pack(side='left', fill='x', expand=True)
        detail_scroll.pack(side='right', fill='y')
        details.insert('1.0', self.t('Операций пока нет.') if not rows else self.t('Записей: {count}. Выберите запись в таблице.', count=format_number(len(rows), self.language)))
        details.configure(state='disabled')
        def select(event):
            if not tree.selection():
                return
            row = rows[tree.index(tree.selection()[0])]
            lines = []
            for key, title in zip(columns, headings):
                value = row.get(key) or '—'
                if key == 'action':
                    value = actions.get(value, value)
                elif key in ('old_status', 'new_status'):
                    value = status_label(self.language, value)
                elif key == 'operation_date' and value != '—':
                    value = format_date(value, self.language)
                elif key == 'recorded_at' and value != '—':
                    value = self._format_timestamp(value)
                lines.append(f'{title}: {value}')
            if row.get('details'):
                try:
                    labels = {'name': self.t('Наименование'), 'printers': self.t('Подходящие принтеры'),
                              'old': self.t('Было'), 'new': self.t('Стало'), 'before': self.t('Было'), 'after': self.t('Стало'),
                              'id': 'ID', 'status': self.t('Статус'), 'operation_date': self.t('Дата операции')}
                    def describe(value, level=0):
                        if isinstance(value, dict):
                            parts = []
                            for k, v in value.items():
                                shown = status_label(self.language, v) if k in ('status', 'old_status', 'new_status') else v
                                parts.append('  ' * level + labels.get(k, k) + ': ' +
                                             ('\n' + describe(v, level + 1) if isinstance(v, dict) else str(shown)))
                            return '\n'.join(parts)
                        return str(value)
                    extra = describe(json.loads(row['details']))
                except (ValueError, TypeError):
                    extra = str(row['details'])
                lines.append(self.t('Изменения') + ': ' + extra)
            details.configure(state='normal')
            details.delete('1.0', 'end')
            details.insert('1.0', '\n'.join(lines))
            details.configure(state='disabled')
        tree.bind('<<TreeviewSelect>>', select)

    def _format_timestamp(self, value):
        try:
            from datetime import datetime
            parsed = datetime.fromisoformat(value)
            pattern = '%m/%d/%Y %I:%M %p' if self.language == 'en' else '%d.%m.%Y %H:%M'
            return parsed.strftime(pattern)
        except (TypeError, ValueError):
            return value

    def _cache_batch_date(self, action):
        if not hasattr(self, '_batch_dates'):
            self._batch_dates = {}
        value = self.batch_date.get()
        try:
            self._batch_dates[action] = parse_date_input(value, getattr(self, 'language', 'ru'))
        except ValueError:
            self._batch_dates[action] = value

    def _operation_date(self):
        return parse_date_input(self.batch_date.get(), getattr(self, 'language', 'ru'))
