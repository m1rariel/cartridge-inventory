$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Сборка Windows выполняется на Windows.' }
py -3.12 -m venv .venv-build
if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать окружение Python 3.12.' }
& .\.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить средства сборки.' }
& .\.venv-build\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Тесты не прошли.' }
& .\.venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onefile --collect-all PIL --name CartridgeAccounting --distpath dist-onefile --workpath build-onefile run.py
if ($LASTEXITCODE -ne 0) { throw 'Сборка не выполнена.' }
Copy-Item README.md dist-onefile\ИНСТРУКЦИЯ.md
New-Item -ItemType Directory -Force dist | Out-Null
Compress-Archive -Path dist-onefile\CartridgeAccounting.exe, dist-onefile\ИНСТРУКЦИЯ.md -DestinationPath dist\CartridgeAccounting-Windows.zip -Force
Write-Host 'Готово: dist-onefile\CartridgeAccounting.exe и dist\CartridgeAccounting-Windows.zip. Проверьте на целевой Windows без Python и без сети.'
