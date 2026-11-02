import tkinter as tk
from tkinter import messagebox
from cartridge_app.paths import data_directory
from cartridge_app.storage import Storage
from cartridge_app.service import Service
from cartridge_app.ui import App
from cartridge_app.localization import tr, translate_error
from cartridge_app.preferences import system_language


def main():
    root = tk.Tk()
    root.withdraw()
    storage = None
    try:
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
