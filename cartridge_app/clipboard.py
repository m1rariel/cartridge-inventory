"""Layout-independent clipboard shortcuts for editable Tk controls."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk


_RUSSIAN_LAYOUT = {
    'cyrillic_es': 'copy',       # physical C key
    'cyrillic_em': 'paste',      # physical V key
    'cyrillic_che': 'cut',       # physical X key
    'cyrillic_ef': 'select_all', # physical A key
}
_WINDOWS_VKEY = {67: 'copy', 86: 'paste', 88: 'cut', 65: 'select_all'}


def shortcut_action(keysym, keycode=None, platform=None):
    """Resolve Ctrl+C/V/X/A across keyboard layouts without changing key input."""
    platform = sys.platform if platform is None else platform
    if platform == 'win32' and keycode in _WINDOWS_VKEY:
        return _WINDOWS_VKEY[keycode]
    return _RUSSIAN_LAYOUT.get(str(keysym).lower())


def install_clipboard_shortcuts(root):
    """Install a bindtag before Tk's class bindings on text-entry widgets."""
    tag = 'CartridgeClipboardShortcuts'

    def on_focus(event):
        widget = event.widget
        if not isinstance(widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox)):
            return
        tags = widget.bindtags()
        if tag not in tags:
            widget.bindtags((tags[0], tag, *tags[1:]))

    def on_control_key(event):
        action = shortcut_action(event.keysym, getattr(event, 'keycode', None))
        if action is None:
            return None
        widget = event.widget
        text_widget = isinstance(widget, tk.Text)
        try:
            if action == 'copy':
                has_selection = bool(widget.tag_ranges('sel')) if text_widget else bool(widget.selection_present())
                if has_selection:
                    root.clipboard_clear()
                    root.clipboard_append(widget.get('sel.first', 'sel.last') if text_widget
                                          else widget.selection_get())
                return 'break'

            state = str(widget.cget('state'))
            if state in ('disabled', 'readonly'):
                return 'break'

            if action == 'select_all':
                if text_widget:
                    widget.tag_add('sel', '1.0', 'end-1c')
                else:
                    widget.selection_range(0, 'end')
                    widget.icursor('end')
                return 'break'

            if action == 'cut':
                has_selection = bool(widget.tag_ranges('sel')) if text_widget else bool(widget.selection_present())
                if has_selection:
                    root.clipboard_clear()
                    root.clipboard_append(widget.get('sel.first', 'sel.last') if text_widget
                                          else widget.selection_get())
                    widget.delete('sel.first', 'sel.last')
                return 'break'

            if action == 'paste':
                try:
                    value = root.clipboard_get()
                except tk.TclError:
                    return 'break'
                if text_widget:
                    if widget.tag_ranges('sel'):
                        widget.delete('sel.first', 'sel.last')
                    widget.insert('insert', value)
                else:
                    if widget.selection_present():
                        widget.delete('sel.first', 'sel.last')
                    widget.insert('insert', value)
                return 'break'
        except tk.TclError:
            # A selection or clipboard can disappear between keypress and handling.
            return 'break'
        return None

    root.bind_class(tag, '<Control-KeyPress>', on_control_key)
    root.bind_all('<FocusIn>', on_focus, add='+')
