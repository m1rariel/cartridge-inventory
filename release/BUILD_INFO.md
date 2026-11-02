# Archived Windows executable

`CartridgeAccounting-arm64-pre-auth.exe` is the existing single-file Windows ARM64 build (14 MB, SHA-256 `a1a2d8963049c60c02dba731ae374cbd4a84bde1a13edcdd90d21de3a93d97bd`).

It predates the shared access-key prompt now present in the source, so it does **not** require that key. Do not distribute it as the current protected build. To produce the current executable, run `build-windows.ps1` on Windows with Python 3.12; it writes `dist-onefile/CartridgeAccounting.exe`.

The archived binary was inspected as a Windows ARM64 PE and PyInstaller one-file archive. It was not launched on Windows in the current environment.
