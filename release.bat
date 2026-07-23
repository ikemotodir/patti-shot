@echo off
setlocal
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
set REPO=ikemotodir/patti-shot
set "GH=gh"
where gh >nul 2>&1
if errorlevel 1 set "GH=C:\Program Files\GitHub CLI\gh.exe"

if not exist "%PY%" (
  echo [ERROR] .venv not found. See README.md
  exit /b 1
)

rem -- read version from the package (delete stale file first so a failed
rem    write can never leave an old version behind)
del /f /q build\ver.txt >nul 2>&1
"%PY%" -c "import sys; sys.path.insert(0,'src'); import patti_shot; print(patti_shot.__version__)" > build\ver.txt
if errorlevel 1 (
  echo [ERROR] could not read version
  exit /b 1
)
set /p VER=<build\ver.txt
if "%VER%"=="" (
  echo [ERROR] could not read version
  exit /b 1
)
echo === PATTI SHOT v%VER% release ===

rem -- refuse to overwrite an existing release
"%GH%" release view v%VER% --repo %REPO% >nul 2>&1
if not errorlevel 1 (
  echo [ERROR] release v%VER% already exists on GitHub.
  echo         Bump __version__ in src\patti_shot\__init__.py first.
  exit /b 1
)

rem -- build the exe
call build\build.bat
if errorlevel 1 exit /b 1

rem -- release notes (Japanese) via UTF-8 file so this bat stays ASCII
"%PY%" -c "import sys; sys.path.insert(0,'src'); from patti_shot.relnotes import write_notes; write_notes('build/notes.md')"
if errorlevel 1 exit /b 1

rem -- create the GitHub release with the exe attached
"%GH%" release create v%VER% build\dist\PATTI_SHOT.exe --repo %REPO% --title "PATTI SHOT v%VER%" --notes-file build\notes.md
if errorlevel 1 (
  echo [ERROR] gh release create failed
  exit /b 1
)
echo.
echo === DONE: https://github.com/%REPO%/releases/tag/v%VER% ===
endlocal
