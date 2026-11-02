import tkinter as tk
from tkinter import messagebox, simpledialog
from cartridge_app.paths import data_directory
from cartridge_app.storage import Storage
from cartridge_app.service import Service
from cartridge_app.ui import App
from cartridge_app.localization import tr, translate_error
from cartridge_app.preferences import system_language
from cartridge_app.auth import verify_access_key
from cartridge_app.clipboard import install_clipboard_shortcuts


def authorize(root):
    """Ask for the shared offline key before opening the inventory database."""
    language = system_language()
    install_clipboard_shortcuts(root)
    candidate = simpledialog.askstring(
        tr(language, 'Доступ к приложению'),
        tr(language, 'Введите ключ доступа, чтобы открыть приложение:'),
        show='*', parent=root)
    if candidate is None:
        return False
    if verify_access_key(candidate):
        return True
    messagebox.showerror(
        tr(language, 'Доступ запрещён'),
        tr(language, 'Неверный ключ доступа. Приложение будет закрыто.'),
        parent=root)
    return False


def main():
    root = tk.Tk()
    root.withdraw()
    storage = None
    try:
        if not authorize(root):
            return
        storage = Storage(data_directory() / 'inventory.sqlite3')
        App(root, Service(storage))
        root.deiconify()
        root.mainloop()
    except Exception as exc:
        language = system_language()
        messagebox.showerror(tr(language, 'Не удалось запустить приложение'),
                             tr(language, 'Проверьте доступ к каталогу данных. Существующие данные не удалены.\n\n') +
                             translate_error(language, exc), parent=root)
    finally:
        if storage is not None:
            storage.close()
        try:
            root.destroy()
        except tk.TclError:
            pass


if __name__ == '__main__':
    main()
