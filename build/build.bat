@echo off
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
  echo [ERROR] venv not found. Run: python -m venv .venv ^&^& .venv\Scripts\python -m pip install playwright pillow numpy img2pdf pyinstaller
  exit /b 1
)
rem -- use the custom icon only when the file exists (it is blocked on the logo
rem    asset); otherwise build with the default icon so releases never block
rem    NOTE: --icon resolves relative to the SPEC dir (build\), so no build\ prefix here
set ICON=
if exist "build\patti_shot.ico" set ICON=--icon patti_shot.ico
echo Building PATTI_SHOT.exe ...
"%PY%" -m PyInstaller --noconfirm --onefile --name PATTI_SHOT %ICON% --paths src --collect-all playwright --hidden-import patti_shot --distpath build\dist --workpath build\work --specpath build build\entry.py
if errorlevel 1 (
  echo [ERROR] build failed
  exit /b 1
)
echo.
echo Done: build\dist\PATTI_SHOT.exe
endlocal
