"""Accessible settings panel implemented with standard Tk widgets."""
import tkinter as tk
from tkinter import colorchooser, filedialog, ttk
from datetime import date

from .localization import tr, translate_error
from .preferences import FONT_FAMILIES, color_contrast, effective_theme, recommended_text_color
from .visual import COLORS


class SettingsDialog:
    def __init__(self, app, return_focus=None):
        self.app = app
        self.return_focus = return_focus
        self.pending_background = None
        self.photo_ref = None
        self.window = tk.Toplevel(app.root)
        self.window.title(self.t('Настройки'))
        self.window.transient(app.root)
        self.window.minsize(*self._minimum())
        self.window.geometry(self._geometry())
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', lambda _e: self.close())
        self.window.bind('<Control-w>', lambda _e: self.close())
        self._make_scrollable()
        self.rebuild()
        self.window.grab_set()
        self.window.after_idle(self._focus_first)

    def t(self, text, **values):
        return tr(self.app.language, text, **values)

    def _geometry(self):
        width, height = 680, 760
        screen_w, screen_h = self.app.root.winfo_screenwidth(), self.app.root.winfo_screenheight()
        width = max(280, min(width, screen_w - 32))
        height = max(300, min(height, screen_h - 48))
        return f'{width}x{height}'

    def _minimum(self):
        return (max(280, min(340, self.app.root.winfo_screenwidth() - 32)),
                max(300, min(420, self.app.root.winfo_screenheight() - 48)))

    def _make_scrollable(self):
        self.shell = ttk.Frame(self.window, style='Content.TFrame')
        self.shell.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(self.shell, highlightthickness=0, bd=0, takefocus=False,
                                background=COLORS['surface'])
        self.scroll = ttk.Scrollbar(self.shell, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scroll.pack(side='right', fill='y')
        self.content = ttk.Frame(self.canvas, style='Content.TFrame', padding=20)
        self._content_window = self.canvas.create_window((0, 0), window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(self._content_window, width=event.width))
        self.canvas.bind('<MouseWheel>', self._wheel, add='+')
        self.canvas.bind('<Button-4>', self._wheel, add='+')
        self.canvas.bind('<Button-5>', self._wheel, add='+')

    def _wheel(self, event):
        try:
            if self.window.focus_displayof() is None:
                return None
        except tk.TclError:
            return None
        if getattr(event, 'num', None) == 4:
            delta = -1
        elif getattr(event, 'num', None) == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta * 3, 'units')
        return 'break'

    def _focus_first(self):
        try:
            self.theme_button.focus_set()
        except (AttributeError, tk.TclError):
            pass

    def _section(self, title):
        ttk.Label(self.content, text=self.t(title), style='Title.TLabel').pack(anchor='w', pady=(14, 8))

    def _row(self, label, widget_factory):
        row = ttk.Frame(self.content, style='Content.TFrame')
        row.pack(fill='x', pady=5)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=self.t(label), style='Content.TLabel', wraplength=250).grid(row=0, column=0, sticky='w', padx=(0, 12))
        widget_factory(row).grid(row=0, column=1, sticky='ew')
        return row

    def rebuild(self):
        if not self.window.winfo_exists():
            return
        for child in self.content.winfo_children():
            child.destroy()
        self.window.title(self.t('Настройки'))
        settings = self.app.settings
        self._section('Оформление')
        if effective_theme(settings.theme) == 'dark':
            icon, text = '☀', 'Включить светлую тему'
        else:
            icon, text = '☾', 'Включить тёмную тему'
        self.theme_button = ttk.Button(self.content, text=f'{icon}  {self.t(text)}',
                                       command=lambda: self._save(theme='light' if effective_theme(settings.theme) == 'dark' else 'dark'),
                                       style='Glass.TButton')
        self.theme_button.pack(fill='x', pady=(0, 8))

        family = tk.StringVar(value=settings.font_family)
        self._row('Шрифт', lambda parent: ttk.Combobox(parent, textvariable=family,
                                       values=FONT_FAMILIES, state='readonly'))
        family.trace_add('write', lambda *_: self._save(font_family=family.get()))

        size_line = ttk.Frame(self.content, style='Content.TFrame')
        size_line.pack(fill='x', pady=5)
        ttk.Label(size_line, text=self.t('Размер текста'), style='Content.TLabel').pack(side='left')
        size_value = tk.IntVar(value=settings.font_size)
        size = ttk.Spinbox(size_line, from_=9, to=24, increment=1, width=5, textvariable=size_value,
                           command=lambda: self._save(font_size=int(size_value.get())))
        size.pack(side='right')
        size.bind('<FocusOut>', lambda _e: self._save_size(size_value))
        size.bind('<Return>', lambda _e: self._save_size(size_value))
        ttk.Button(size_line, text=self.t('Сбросить размер'), command=lambda: self._save(font_size=10)).pack(side='right', padx=8)

        self._color_row('Основной цвет', 'accent_color', settings.accent_color)
        self._color_row('Цвет текста для светлой темы', 'text_color_light', settings.text_color_light)
        self._color_row('Цвет текста для тёмной темы', 'text_color_dark', settings.text_color_dark)

        self._section('Фон приложения')
        self.preview = ttk.Label(self.content, text=self.t('Нет пользовательского фона.'),
                                 style='ContentMuted.TLabel', anchor='center')
        self.preview.pack(fill='x', pady=(0, 8))
        if self.pending_background:
            try:
                self.photo_ref = self.app.preview_background(self.pending_background['filename'], (520, 220))
                self.preview.configure(image=self.photo_ref, text='')
            except Exception as error:
                self.preview.configure(text=translate_error(self.app.language, error))
        else:
            self._show_saved_preview()
        chooser = ttk.Frame(self.content, style='Content.TFrame')
        chooser.pack(fill='x')
        button_text = 'Заменить изображение' if settings.background_mode == 'custom' else 'Выбрать изображение'
        ttk.Button(chooser, text=self.t(button_text), command=self.choose_background,
                   style='Glass.TButton').pack(side='left', fill='x', expand=True)
        ttk.Button(chooser, text=self.t('Стандартный фон'), command=self.reset_background,
                   style='Glass.TButton').pack(side='left', padx=(8, 0))
        ttk.Label(self.content, text=self.t('JPEG, PNG или WebP, до 10 МБ, до 24 Мп. Изображение остаётся на этом компьютере.'),
                  style='ContentMuted.TLabel', wraplength=540, justify='left').pack(anchor='w', pady=8)
        overlay = tk.IntVar(value=settings.background_overlay)
        self._row('Затемнение / осветление', lambda parent: ttk.Scale(parent, from_=-80, to=80,
                   variable=overlay, command=lambda value: self._preview_overlay(value)))
        ttk.Label(self.content, textvariable=overlay, style='ContentMuted.TLabel').pack(anchor='e')
        if self.pending_background:
            self._pending_controls()
        elif settings.background_mode == 'custom':
            ttk.Button(self.content, text=self.t('Удалить пользовательский фон'), command=self.reset_background,
                       style='Danger.TButton').pack(anchor='w', pady=6)

        self._section('Язык')
        language = tk.StringVar(value=settings.language)
        language_row = ttk.Frame(self.content, style='Content.TFrame')
        language_row.pack(fill='x')
        for code, label in (('ru', 'Русский'), ('en', 'Английский')):
            ttk.Radiobutton(language_row, text=self.t(label), value=code, variable=language,
                            command=lambda value=code: self._save(language=value)).pack(side='left', padx=(0, 16))

        self._section('О приложении')
        year = date.today().year
        copyright_text = (f'© {year} @m1rariel. ' +
                          ('Все права защищены.' if self.app.language == 'ru' else 'All rights reserved.'))
        credit = ttk.Label(self.content, text=copyright_text, style='ContentMuted.TLabel', cursor='hand2')
        credit.pack(anchor='w')
        credit.bind('<Button-1>', lambda _e: self.app.open_url('https://t.me/m1rariel'))
        ttk.Button(self.content, text=self.t('Сбросить настройки'), command=self.reset_settings,
                   style='Danger.TButton').pack(anchor='w', pady=(16, 8))
        ttk.Button(self.content, text=self.t('Закрыть'), command=self.close).pack(anchor='e')
        self._bind_wheel_children(self.content)

    def _bind_wheel_children(self, parent):
        for child in parent.winfo_children():
            child.bind('<MouseWheel>', self._wheel, add='+')
            child.bind('<Button-4>', self._wheel, add='+')
            child.bind('<Button-5>', self._wheel, add='+')
            if child.winfo_children():
                self._bind_wheel_children(child)

    def _color_row(self, title, setting, color):
        row = ttk.Frame(self.content, style='Content.TFrame')
        row.pack(fill='x', pady=4)
        row.columnconfigure(0, weight=1)
        ttk.Label(row, text=self.t(title), style='Content.TLabel', wraplength=250).grid(row=0, column=0, sticky='w')
        sample = tk.Label(row, text=color, background=color, foreground=self._contrast_text(color),
                          padx=8, pady=4, relief='solid', bd=1, takefocus=False)
        sample.grid(row=0, column=1, padx=5)
        ttk.Button(row, text=self.t('Выбрать цвет'), command=lambda: self._choose_color(setting, color)).grid(row=0, column=2)
        theme = 'light' if setting.endswith('light') else 'dark'
        surfaces = ('#edf2fb', '#ffffff', '#f8faff') if theme == 'light' else ('#111722', '#202a39', '#1b2636')
        warning = min(color_contrast(color, surface) for surface in surfaces) < 4.5 if setting != 'accent_color' else False
        if warning:
            ttk.Label(row, text=self.t('Цвет текста имеет недостаточный контраст и может быть плохо читаем.'),
                      style='Error.TLabel', wraplength=420).grid(row=1, column=0, columnspan=3, sticky='w', pady=3)
            ttk.Button(row, text=self.t('Восстановить рекомендуемый цвет'),
                       command=lambda: self._save(**{setting: recommended_text_color(theme)})).grid(row=2, column=0, columnspan=3, sticky='w')

    @staticmethod
    def _contrast_text(color):
        try:
            rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
            return '#111111' if sum(rgb) > 382 else '#ffffff'
        except (ValueError, TypeError):
            return '#111111'

    def _choose_color(self, setting, initial):
        _rgb, color = colorchooser.askcolor(color=initial, parent=self.window, title=self.t('Выбрать цвет'))
        if color:
            self._save(**{setting: color.lower()})

    def _save_size(self, variable):
        try:
            self._save(font_size=int(variable.get()))
        except (ValueError, tk.TclError) as error:
            self.app.show_error(self.t('Размер текста должен быть от 9 до 24.'), self.window)

    def _save(self, **changes):
        if self.app.save_preferences(**changes):
            if 'language' in changes and hasattr(self.app, 'settings_button'):
                self.return_focus = self.app.settings_button
            self.rebuild()

    def choose_background(self):
        path = filedialog.askopenfilename(parent=self.window, title=self.t('Выбрать изображение'),
            filetypes=[(self.t('Поддерживаемые изображения'), '*.jpg *.jpeg *.png *.webp')])
        if not path:
            return
        try:
            metadata = self.app.image_store.validate_and_save(path)
            if self.pending_background:
                self.app.image_store.remove(self.pending_background['filename'])
            self.pending_background = metadata
            self.rebuild()
        except Exception as error:
            self.app.show_error(str(error), self.window)

    def rebuild_pending_buttons(self):
        self.rebuild()

    def _pending_controls(self):
        row = ttk.Frame(self.content, style='Content.TFrame')
        row.pack(fill='x', pady=5)
        ttk.Button(row, text=self.t('Установить этот фон'), style='Primary.TButton',
                   command=self.apply_pending_background).pack(side='left')
        ttk.Button(row, text=self.t('Отмена'), command=self.cancel_pending_background).pack(side='left', padx=8)

    def apply_pending_background(self):
        old = self.app.settings.background_filename
        name = self.pending_background['filename']
        committed = False
        try:
            if not self.app.save_preferences(background_mode='custom', background_filename=name):
                self.app.image_store.remove(name)
                self.pending_background = None
                self.rebuild()
                return
            committed = True
            self.pending_background = None
            self.app.apply_background()
            if old and old != name:
                try:
                    self.app.image_store.remove(old)
                except Exception:
                    pass
            self.rebuild()
        except Exception as error:
            if not committed:
                try:
                    self.app.image_store.remove(name)
                except Exception:
                    pass
                self.pending_background = None
            self.app.show_error(self.t('Не удалось сохранить фон: {error}', error=error), self.window)

    def cancel_pending_background(self):
        if self.pending_background:
            try:
                self.app.image_store.remove(self.pending_background['filename'])
            except Exception:
                pass
        self.pending_background = None
        self.photo_ref = None
        self.app.apply_background()
        self.rebuild()

    def reset_background(self):
        if self.pending_background:
            try:
                self.app.image_store.remove(self.pending_background['filename'])
            except Exception:
                pass
            self.pending_background = None
            self.photo_ref = None
        old = self.app.settings.background_filename
        if self.app.save_preferences(background_mode='default', background_filename=None):
            self.app.apply_background()
            if old:
                try:
                    self.app.image_store.remove(old)
                except Exception:
                    pass
            self.rebuild()

    def reset_settings(self):
        if not self.app.ask_confirmation(self.t('Сброс настроек'), self.t('Настройки темы, оформления, языка и фона будут сброшены. Данные склада, профиль и журнал останутся без изменений.\n\nПродолжить?'), parent=self.window):
            return
        try:
            self.app.reset_preferences()
        except Exception as error:
            self.app.show_error(self.t('Не удалось сохранить настройку: {error}', error=error), self.window)
            return
        if getattr(self.app, 'current_screen', '') == 'main' and hasattr(self.app, 'settings_button'):
            self.return_focus = self.app.settings_button
        self.pending_background = None
        try:
            self.app.image_store.reset()
        except Exception as error:
            self.app.show_error(self.t('Не удалось сохранить настройку: {error}', error=error), self.window)
        self.rebuild()

    def _show_saved_preview(self):
        if self.app.settings.background_mode != 'custom' or not self.app.settings.background_filename:
            return
        try:
            self.photo_ref = self.app.preview_background(self.app.settings.background_filename, (520, 220))
            self.preview.configure(image=self.photo_ref, text='')
        except Exception as error:
            self.preview.configure(text=translate_error(self.app.language, error))

    def _preview_overlay(self, _value):
        # Preview a separate overlay layer and persist a stable value after dragging.
        try:
            self.app.preview_overlay(float(_value))
            pending = getattr(self, '_overlay_timer', None)
            if pending:
                self.window.after_cancel(pending)
            self._overlay_timer = self.window.after(500, self._commit_overlay_preview)
        except tk.TclError:
            pass

    def _commit_overlay_preview(self):
        if self.window.winfo_exists():
            self._save(background_overlay=int(round(self.app._preview_overlay_value)))

    def close(self):
        pending_overlay = getattr(self, '_overlay_timer', None)
        if pending_overlay:
            try:
                self.window.after_cancel(pending_overlay)
            except tk.TclError:
                pass
            value = getattr(self.app, '_preview_overlay_value', self.app.settings.background_overlay)
            if value != self.app.settings.background_overlay:
                self.app.save_preferences(background_overlay=value)
        if hasattr(self.app, '_preview_overlay_value'):
            self.app._preview_overlay_value = self.app.settings.background_overlay
            self.app.apply_background(report_error=False)
        if self.pending_background:
            try:
                self.app.image_store.remove(self.pending_background['filename'])
            except Exception:
                pass
            self.pending_background = None
        try:
            self.window.grab_release()
            self.window.destroy()
        except tk.TclError:
            pass
        if self.return_focus is not None:
            try:
                self.return_focus.focus_set()
            except tk.TclError:
                pass
