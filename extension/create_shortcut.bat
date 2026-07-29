@echo off
rem PATTI SHOT - create a Desktop shortcut to this extension folder.
rem Updating the extension means replacing files in this folder, so a
rem shortcut on the Desktop keeps it one click away.
setlocal
set "HERE=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w = New-Object -ComObject WScript.Shell; $d = $w.SpecialFolders['Desktop']; $s = $w.CreateShortcut((Join-Path $d 'PATTI SHOT Folder.lnk')); $s.TargetPath = '%HERE%'.TrimEnd('\'); $s.Save()"
if %errorlevel%==0 (
  echo OK: Desktop shortcut "PATTI SHOT Folder" created.
) else (
  echo FAILED: could not create the shortcut.
)
pause
