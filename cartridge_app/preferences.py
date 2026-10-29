"""Validated, versioned user preferences stored separately from inventory."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Optional


PREFERENCE_VERSION = 1
DEFAULT_ACCENT = '#456fe0'
RECOMMENDED_TEXT_LIGHT = '#162238'
RECOMMENDED_TEXT_DARK = '#f4f6fb'
FONT_FAMILIES = ('Segoe UI', 'Arial', 'Calibri', 'Verdana', 'Tahoma')
_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


def system_theme() -> str:
    """Return the Windows/macOS/Linux system light or dark preference."""
    if sys.platform == 'win32':
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
            value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
            return 'light' if value else 'dark'
        except (ImportError, OSError):
            pass
    if sys.platform == 'darwin':
        import subprocess
        try:
            result = subprocess.run(['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                                    capture_output=True, text=True, timeout=1, check=False)
            if result.returncode == 0 and result.stdout.strip().lower() == 'dark':
                return 'dark'
            return 'light'
        except (OSError, subprocess.SubprocessError):
            pass
    # GTK desktops commonly expose this preference through GTK_THEME.
    if 'dark' in os.environ.get('GTK_THEME', '').lower():
        return 'dark'
    return 'light'


def system_language() -> str:
    """Use the operating-system locale, defaulting to English except ru-* locales."""
    import locale
    candidate = os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG')
    if not candidate:
        try:
            candidate = locale.getlocale()[0]
        except (ValueError, TypeError):
            candidate = ''
    return 'ru' if str(candidate or '').lower().startswith('ru') else 'en'


@dataclass(frozen=True)
class Settings:
    # Follow the operating system until the user explicitly chooses a theme.
    theme: str = 'system'
    language: str = 'ru'
    font_family: str = 'Segoe UI'
    font_size: int = 10
    accent_color: str = DEFAULT_ACCENT
    text_color_light: str = RECOMMENDED_TEXT_LIGHT
    text_color_dark: str = RECOMMENDED_TEXT_DARK
    background_mode: str = 'default'
    background_filename: Optional[str] = None
    background_overlay: int = 38


def default_settings() -> Settings:
    return Settings(theme='system', language=system_language())


def effective_theme(theme: str) -> str:
    """Resolve the saved preference to the palette to render right now."""
    return system_theme() if theme == 'system' else theme


def _validated(value: Any, defaults: Settings) -> Settings:
    if not isinstance(value, dict):
        return defaults
    known = {field.name for field in fields(Settings)}
    data = asdict(defaults)
    for key in known:
        if key in value:
            data[key] = value[key]
    if data['theme'] not in ('system', 'light', 'dark'):
        data['theme'] = defaults.theme
    if data['language'] not in ('ru', 'en'):
        data['language'] = defaults.language
    if data['font_family'] not in FONT_FAMILIES:
        data['font_family'] = defaults.font_family
    if type(data['font_size']) is not int or not 9 <= data['font_size'] <= 24:
        data['font_size'] = defaults.font_size
    for key, default in (('accent_color', DEFAULT_ACCENT),
                         ('text_color_light', RECOMMENDED_TEXT_LIGHT),
                         ('text_color_dark', RECOMMENDED_TEXT_DARK)):
        if not isinstance(data[key], str) or not _COLOR.fullmatch(data[key]):
            data[key] = default
        else:
            data[key] = data[key].lower()
    if data['background_mode'] not in ('default', 'custom'):
        data['background_mode'] = 'default'
    filename = data['background_filename']
    if filename is not None and (not isinstance(filename, str) or
                                 Path(filename).name != filename or
                                 Path(filename).suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp')):
        data['background_filename'] = None
    if data['background_mode'] == 'custom' and not data['background_filename']:
        data['background_mode'] = 'default'
    if type(data['background_overlay']) is not int or not -80 <= data['background_overlay'] <= 80:
        data['background_overlay'] = defaults.background_overlay
    return Settings(**data)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.preferences-', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


class PreferencesStore:
    """One JSON preferences file. Inventory database is never touched here."""

    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.path = self.root_dir / 'preferences.json'
        self._defaults = default_settings()
        self.settings = self._defaults

    def load(self) -> Settings:
        try:
            with self.path.open('r', encoding='utf-8') as stream:
                raw = json.load(stream)
            if not isinstance(raw, dict) or raw.get('version') != PREFERENCE_VERSION:
                self.settings = self._defaults
            else:
                self.settings = _validated(raw.get('settings', {}), self._defaults)
        except (OSError, ValueError, TypeError):
            # A broken preferences file must not block opening the inventory.
            self.settings = self._defaults
        return self.settings

    def update(self, **kwargs) -> Settings:
        allowed = {field.name for field in fields(Settings)}
        unknown = set(kwargs) - allowed
        if unknown:
            raise ValueError('Неизвестная настройка: ' + ', '.join(sorted(unknown)))
        data = asdict(self.settings)
        data.update(kwargs)
        # For explicit user edits reject invalid input instead of silently clamping it.
        for name, value in kwargs.items():
            if name == 'font_size' and (type(value) is not int or not 9 <= value <= 24):
                raise ValueError('Размер текста должен быть от 9 до 24.')
            if name == 'background_overlay' and (type(value) is not int or not -80 <= value <= 80):
                raise ValueError('Значение подложки должно быть от −80 до 80.')
            if name in ('accent_color', 'text_color_light', 'text_color_dark') and (
                    not isinstance(value, str) or not _COLOR.fullmatch(value)):
                raise ValueError('Цвет должен быть в формате #RRGGBB.')
            if name == 'theme' and value not in ('system', 'light', 'dark'):
                raise ValueError('Неизвестная тема.')
            if name == 'language' and value not in ('ru', 'en'):
                raise ValueError('Неизвестный язык.')
            if name == 'font_family' and value not in FONT_FAMILIES:
                raise ValueError('Выберите шрифт из списка.')
            if name == 'background_mode' and value not in ('default', 'custom'):
                raise ValueError('Неизвестный режим фона.')
        candidate = _validated(data, self._defaults)
        _atomic_json(self.path, {'version': PREFERENCE_VERSION, 'settings': asdict(candidate)})
        self.settings = candidate
        return candidate

    def reset(self) -> Settings:
        candidate = self._defaults
        _atomic_json(self.path, {'version': PREFERENCE_VERSION, 'settings': asdict(candidate)})
        self.settings = candidate
        return candidate


def color_contrast(foreground: str, background: str) -> float:
    """WCAG relative-luminance contrast ratio, rounded to 2 decimals."""
    if not _COLOR.fullmatch(foreground) or not _COLOR.fullmatch(background):
        raise ValueError('Цвет должен быть в формате #RRGGBB.')

    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    first, second = sorted((luminance(foreground), luminance(background)), reverse=True)
    return round((first + 0.05) / (second + 0.05), 2)


def contrast_warning(foreground: str, background: str) -> bool:
    """True when normal-sized text misses WCAG AA's 4.5:1 target."""
    return color_contrast(foreground, background) < 4.5


def recommended_text_color(theme: str) -> str:
    return RECOMMENDED_TEXT_DARK if theme == 'dark' else RECOMMENDED_TEXT_LIGHT
