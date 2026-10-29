"""Shared Liquid Glass-inspired tokens and ttk styles.

Tk's child widgets do not support per-widget backdrop filtering or alpha
compositing. Glass surfaces therefore use opaque, high-contrast fallbacks;
the palette keeps translucency and blur values as design intent for a future
native platform renderer rather than pretending Tk applies those effects.
"""
import ctypes
import os
import sys
import tkinter.font as tkfont
from tkinter import ttk
from .preferences import effective_theme


COLORS = {
    'background': '#edf2fb',
    'background_highlight': '#f6f8fd',
    'surface': '#ffffff',
    'surface_soft': '#f5f8fd',
    'glass_fallback': '#f8faff',
    'glass_border': '#ffffff',
    'border': '#d7e0ee',
    'border_strong': '#b8c8df',
    'text': '#162238',
    'muted': '#63738b',
    'accent': '#456fe0',
    'accent_hover': '#355fce',
    'accent_pressed': '#2b50b4',
    'accent_soft': '#dfe9ff',
    'danger': '#a73f4b',
    'danger_hover': '#923541',
    'success': '#176b4a',
    'focus': '#235fdf',
    'disabled_bg': '#e7ecf4',
    'disabled_text': '#8490a2',
}

SPACING = {
    'xs': 4,
    'sm': 8,
    'md': 12,
    'lg': 18,
    'xl': 24,
    'page': 16,
}

RADII = {
    'control': 10,
    'panel': 18,
    'floating': 22,
}

GLASS = {
    'regular_opacity': 0.84,
    'clear_opacity': 0.92,
    'backdrop_blur_px': 18,
    'highlight': '#ffffff',
    'shadow': '#c7d3e6',
    'tk_alpha_supported': False,
    'tk_backdrop_blur_supported': False,
    'tk_rounded_child_widgets_supported': False,
    'tk_soft_widget_shadows_supported': False,
    'fallback_style': 'Opaque light surfaces with a thin bright border and clear focus contrast.',
}

MOTION = {
    'short_ms': 120,
    'page_ms': 180,
    'reduced_motion_fallback': True,
    'label_color_transitions_supported': True,
}

FONT_FAMILY = 'Segoe UI' if sys.platform == 'win32' else 'TkDefaultFont'
FONT = (FONT_FAMILY, 10)
FONT_STRONG = (FONT_FAMILY, 10, 'bold')
FONT_TITLE = (FONT_FAMILY, 23, 'bold')
FONT_MENU = (FONT_FAMILY, 15, 'bold')

_LIGHT_COLORS = dict(COLORS)
_DARK_COLORS = {
    'background': '#111722', 'background_highlight': '#192232',
    'surface': '#202a39', 'surface_soft': '#283447',
    'glass_fallback': '#1b2636', 'glass_border': '#34445b',
    'border': '#3b4b60', 'border_strong': '#526783',
    'text': '#e8eef8', 'muted': '#aab8ca',
    'accent': '#7899ff', 'accent_hover': '#91aaff', 'accent_pressed': '#587ae7',
    'accent_soft': '#34486d', 'danger': '#f07883', 'danger_hover': '#df6370',
    'success': '#71d0a5', 'focus': '#9cb5ff',
    'disabled_bg': '#2b3543', 'disabled_text': '#8390a1',
}
_BASE_FONT_SIZE = 10
COLORS['accent_foreground'] = '#ffffff'
COLORS['danger_foreground'] = '#ffffff'
COLORS['selection_foreground'] = COLORS['text']


def apply_visual_settings(root, settings):
    """Apply saved theme and design preferences before or during the UI session."""
    global FONT_FAMILY, FONT, FONT_STRONG, FONT_TITLE, FONT_MENU
    theme = effective_theme(getattr(settings, 'theme', 'system'))
    COLORS.clear()
    COLORS.update(_DARK_COLORS if theme == 'dark' else _LIGHT_COLORS)
    accent = getattr(settings, 'accent_color', None)
    text = (getattr(settings, 'text_color_dark' if theme == 'dark' else 'text_color_light', None))
    if _is_hex_color(accent):
        COLORS['accent'] = accent
        COLORS['accent_hover'] = _shade(accent, 1.12 if theme == 'dark' else 0.88)
        COLORS['accent_pressed'] = _shade(accent, 0.86)
        COLORS['accent_soft'] = _blend(accent, COLORS['surface'], .72)
        COLORS['focus'] = accent
    COLORS['accent_foreground'] = _best_foreground(COLORS['accent'])
    COLORS['danger_foreground'] = _best_foreground(COLORS['danger'])
    if _is_hex_color(text) and all(_contrast(text, COLORS[surface]) >= 4.5
                                   for surface in ('background', 'surface', 'surface_soft', 'glass_fallback')):
        COLORS['text'] = text
    COLORS['selection_foreground'] = _best_foreground(COLORS['accent_soft'])
    family = getattr(settings, 'font_family', None) or ('Segoe UI' if sys.platform == 'win32' else 'TkDefaultFont')
    size = max(9, min(24, int(getattr(settings, 'font_size', _BASE_FONT_SIZE))))
    FONT_FAMILY = family
    FONT = (family, size)
    FONT_STRONG = (family, size, 'bold')
    FONT_TITLE = (family, max(size + 8, int(size * 1.7)), 'bold')
    FONT_MENU = (family, max(size + 3, int(size * 1.25)), 'bold')
    try:
        default = tkfont.nametofont('TkDefaultFont', root=root)
        default.configure(family=family, size=size)
    except (tk.TclError, RuntimeError):
        pass
    return apply_visual_style(root)


def _is_hex_color(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != '#':
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


def _rgb(color):
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def _blend(color, other, ratio):
    return '#%02x%02x%02x' % tuple(round(a * (1 - ratio) + b * ratio) for a, b in zip(_rgb(color), _rgb(other)))


def _shade(color, factor):
    return '#%02x%02x%02x' % tuple(max(0, min(255, round(channel * factor))) for channel in _rgb(color))


def _contrast(foreground, background):
    def luminance(color):
        values = [channel / 255 for channel in _rgb(color)]
        values = [item / 12.92 if item <= .04045 else ((item + .055) / 1.055) ** 2.4 for item in values]
        return .2126 * values[0] + .7152 * values[1] + .0722 * values[2]
    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + .05) / (low + .05)


def _best_foreground(background):
    return max(('#ffffff', '#111722'), key=lambda candidate: _contrast(candidate, background))


def apply_visual_style(root):
    """Apply the app-wide palette, control states, and readable fallbacks."""
    root.configure(background=COLORS['background'])
    style = ttk.Style(root)
    if 'clam' in style.theme_names():
        style.theme_use('clam')

    style.configure('.', font=FONT, foreground=COLORS['text'])
    style.configure('TFrame', background=COLORS['background'])
    style.configure('Content.TFrame', background=COLORS['surface'])
    style.configure('Glass.TFrame', background=COLORS['glass_fallback'],
                    relief='solid', borderwidth=1, bordercolor=COLORS['glass_border'])
    style.configure('TLabel', background=COLORS['background'], foreground=COLORS['text'])
    style.configure('Title.TLabel', font=FONT_TITLE, foreground=COLORS['text'])
    style.configure('GlassTitle.TLabel', font=FONT_TITLE, foreground=COLORS['text'],
                    background=COLORS['glass_fallback'])
    style.configure('Glass.TLabel', background=COLORS['glass_fallback'], foreground=COLORS['text'])
    style.configure('GlassMuted.TLabel', background=COLORS['glass_fallback'], foreground=COLORS['muted'])
    style.configure('GlassError.TLabel', background=COLORS['glass_fallback'], foreground=COLORS['danger'])
    style.configure('GlassSuccess.TLabel', background=COLORS['glass_fallback'], foreground=COLORS['success'])
    style.configure('Content.TLabel', background=COLORS['surface'], foreground=COLORS['text'])
    style.configure('ContentMuted.TLabel', background=COLORS['surface'], foreground=COLORS['muted'])
    style.configure('ContentError.TLabel', background=COLORS['surface'], foreground=COLORS['danger'])
    style.configure('Muted.TLabel', foreground=COLORS['muted'])
    style.configure('Error.TLabel', foreground=COLORS['danger'])
    style.configure('Success.TLabel', foreground=COLORS['success'])
    style.configure('Loading.TLabel', foreground=COLORS['accent'], font=FONT_STRONG)

    # Opaque glass fallback with explicit hover, pressed, focus and disabled states.
    style.configure('TButton', padding=(12, 8), background=COLORS['glass_fallback'],
                    foreground=COLORS['text'], bordercolor=COLORS['border'],
                    lightcolor=COLORS['glass_border'], darkcolor=COLORS['border'],
                    relief='flat', focusthickness=2, focuscolor=COLORS['focus'])
    style.map('TButton',
              background=[('disabled', COLORS['disabled_bg']),
                          ('pressed', COLORS['accent_soft']),
                          ('active', COLORS['surface'])],
              foreground=[('disabled', COLORS['disabled_text']), ('!disabled', COLORS['text'])],
              bordercolor=[('focus', COLORS['focus']), ('active', COLORS['border_strong'])])

    style.configure('Primary.TButton', background=COLORS['accent'],
                    foreground=COLORS['accent_foreground'], bordercolor=COLORS['accent'],
                    lightcolor=COLORS['accent'], darkcolor=COLORS['accent_pressed'])
    style.map('Primary.TButton',
              background=[('disabled', COLORS['disabled_bg']),
                          ('pressed', COLORS['accent_pressed']),
                          ('active', COLORS['accent_hover'])],
              foreground=[('disabled', COLORS['disabled_text']), ('!disabled', COLORS['accent_foreground'])],
              bordercolor=[('focus', COLORS['focus'])])

    style.configure('Danger.TButton', background=COLORS['danger'], foreground=COLORS['danger_foreground'],
                    bordercolor=COLORS['danger'], lightcolor=COLORS['danger'],
                    darkcolor=COLORS['danger_hover'])
    style.map('Danger.TButton',
              background=[('disabled', COLORS['disabled_bg']),
                          ('pressed', COLORS['danger_hover']),
                          ('active', COLORS['danger_hover'])],
              foreground=[('disabled', COLORS['disabled_text']), ('!disabled', COLORS['danger_foreground'])],
              bordercolor=[('focus', COLORS['focus'])])

    style.configure('Glass.TButton', padding=(12, 8), background=COLORS['glass_fallback'],
                    foreground=COLORS['text'], bordercolor=COLORS['glass_border'],
                    lightcolor=COLORS['glass_border'], darkcolor=COLORS['border'], relief='flat',
                    focusthickness=2, focuscolor=COLORS['focus'])
    style.map('Glass.TButton',
              background=[('disabled', COLORS['disabled_bg']),
                          ('pressed', COLORS['accent_soft']), ('active', COLORS['surface'])],
              foreground=[('disabled', COLORS['disabled_text']), ('!disabled', COLORS['text'])],
              bordercolor=[('focus', COLORS['focus']), ('active', COLORS['border_strong'])])

    style.configure('Menu.TButton', font=FONT_MENU, padding=(22, 22),
                    background=COLORS['glass_fallback'], foreground=COLORS['text'],
                    bordercolor=COLORS['glass_border'], lightcolor=COLORS['glass_border'],
                    darkcolor=COLORS['border'], relief='flat', focusthickness=2,
                    focuscolor=COLORS['focus'])
    style.map('Menu.TButton',
              background=[('disabled', COLORS['disabled_bg']),
                          ('pressed', COLORS['accent_soft']), ('active', COLORS['surface'])],
              foreground=[('disabled', COLORS['disabled_text']), ('!disabled', COLORS['text'])],
              bordercolor=[('focus', COLORS['focus']), ('active', COLORS['border_strong'])])

    style.configure('TEntry', padding=(10, 7), fieldbackground=COLORS['surface'],
                    foreground=COLORS['text'], bordercolor=COLORS['border'],
                    lightcolor=COLORS['surface'], darkcolor=COLORS['border'])
    style.map('TEntry', fieldbackground=[('disabled', COLORS['surface_soft'])],
              foreground=[('disabled', COLORS['disabled_text'])],
              bordercolor=[('focus', COLORS['focus'])])
    style.configure('TCombobox', padding=(8, 6), fieldbackground=COLORS['surface'],
                    foreground=COLORS['text'], bordercolor=COLORS['border'],
                    lightcolor=COLORS['surface'], darkcolor=COLORS['border'])
    style.map('TCombobox', fieldbackground=[('readonly', COLORS['surface']),
                                            ('disabled', COLORS['surface_soft'])],
              foreground=[('disabled', COLORS['disabled_text'])],
              bordercolor=[('focus', COLORS['focus'])])

    style.configure('Treeview', rowheight=31, background=COLORS['surface'],
                    fieldbackground=COLORS['surface'], foreground=COLORS['text'],
                    bordercolor=COLORS['border'], relief='flat')
    style.map('Treeview', background=[('selected', COLORS['accent_soft'])],
              foreground=[('selected', COLORS['selection_foreground'])])
    style.configure('Treeview.Heading', font=FONT_STRONG, padding=8,
                    background=COLORS['surface_soft'], foreground=COLORS['muted'], relief='flat')
    style.map('Treeview.Heading', background=[('active', COLORS['glass_fallback'])],
              foreground=[('active', COLORS['text'])])
    style.configure('TScrollbar', background=COLORS['surface_soft'], troughcolor=COLORS['background'],
                    bordercolor=COLORS['background'], arrowcolor=COLORS['muted'])

    style.configure('TCheckbutton', background=COLORS['background'], foreground=COLORS['text'],
                    focuscolor=COLORS['focus'])
    style.map('TCheckbutton', foreground=[('disabled', COLORS['disabled_text'])])
    style.configure('TRadiobutton', background=COLORS['background'], foreground=COLORS['text'],
                    focuscolor=COLORS['focus'])
    style.map('TRadiobutton', foreground=[('disabled', COLORS['disabled_text'])])
    style.configure('TNotebook', background=COLORS['background'], borderwidth=0)
    style.configure('TNotebook.Tab', padding=(14, 8), background=COLORS['surface_soft'],
                    foreground=COLORS['muted'])
    style.map('TNotebook.Tab', background=[('selected', COLORS['glass_fallback']),
                                           ('active', COLORS['surface'])],
              foreground=[('selected', COLORS['text']), ('active', COLORS['text'])])
    return style


def prefers_reduced_motion():
    """Respect Windows' client-animation preference; fail safe to no motion."""
    override = os.environ.get('CARTRIDGE_REDUCED_MOTION')
    if override is not None:
        return override.strip().lower() in ('1', 'true', 'yes', 'on')
    if sys.platform != 'win32':
        return MOTION['reduced_motion_fallback']
    try:
        enabled = ctypes.c_int()
        # SPI_GETCLIENTAREAANIMATION; Windows controls this in Accessibility settings.
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return not bool(enabled.value)
    except (AttributeError, OSError):
        pass
    return MOTION['reduced_motion_fallback']


def transition_label(root, label, text, style_name='Title.TLabel'):
    """Fade a short label state change without moving layout or blurring content."""
    label.configure(text=text)
    pending = getattr(label, '_visual_transition_id', None)
    if pending is not None:
        try:
            root.after_cancel(pending)
        except Exception:
            pass
        label._visual_transition_id = None
    if prefers_reduced_motion():
        label.configure(style=style_name)
        return
    style = ttk.Style(root)
    target = style.lookup(style_name, 'foreground') or COLORS['text']
    origin = COLORS['muted']
    transient = f"Motion{id(label)}.{style_name}"
    style.configure(transient, foreground=origin)
    label.configure(style=transient)
    steps = 4
    delay = max(1, MOTION['short_ms'] // steps)

    def blend(value):
        return '#%02x%02x%02x' % tuple(
            round(int(origin[index:index + 2], 16) * (1 - value)
                  + int(target[index:index + 2], 16) * value)
            for index in (1, 3, 5))

    def tick(step):
        try:
            if not label.winfo_exists():
                return
            style.configure(transient, foreground=blend(step / steps))
            if step < steps:
                label._visual_transition_id = root.after(delay, tick, step + 1)
            else:
                label.configure(style=style_name)
                label._visual_transition_id = None
        except Exception:
            return

    label._visual_transition_id = root.after(delay, tick, 1)
