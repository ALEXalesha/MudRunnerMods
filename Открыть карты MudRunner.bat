@echo off
rem Opens MudRunner maps (profile), trucks and garages (map save) - tools\unlock_profile.py.
rem The game must be closed. Shows the changes first, writes only after "да", makes a backup.
rem Undo: start this file again and choose 4 (profile) or 5 (map save).
chcp 65001 >NUL
cd /d "%~dp0"
set PY=python
where py >NUL 2>&1 && set PY=py -3
if exist ".venv\Scripts\python.exe" set PY=".venv\Scripts\python.exe"
%PY% tools\unlock_profile.py %*
echo.
pause
