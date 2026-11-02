# Windows ARM64 executable

`CartridgeAccounting-arm64.exe` is the existing single-file Windows ARM64 build (14 MB, SHA-256 `a1a2d8963049c60c02dba731ae374cbd4a84bde1a13edcdd90d21de3a93d97bd`).

The application launches directly without an authorization key. Build a fresh EXE from the current source with `build-windows.ps1` on Windows with Python 3.12; the output path is `dist-onefile/CartridgeAccounting.exe`.

The binary was identified structurally as a Windows ARM64 PE with a PyInstaller one-file archive. It was not launched on Windows in the current environment.
