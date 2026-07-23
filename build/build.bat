@echo off
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
  echo [ERROR] venv not found. Run: python -m venv .venv ^&^& .venv\Scripts\python -m pip install playwright pillow numpy img2pdf pyinstaller
  exit /b 1
)
echo Building PATTI_SHOT.exe ...
"%PY%" -m PyInstaller --noconfirm --onefile --name PATTI_SHOT --paths src --collect-all playwright --hidden-import patti_shot --distpath build\dist --workpath build\work --specpath build build\entry.py
if errorlevel 1 (
  echo [ERROR] build failed
  exit /b 1
)
echo.
echo Done: build\dist\PATTI_SHOT.exe
endlocal
