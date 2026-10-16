@echo off
rem Builds your own OpenTrail set: several mods in ONE copy of every truck (tools\combine.py).
rem Undo: start this file again and choose 0.
chcp 65001 >NUL
cd /d "%~dp0"
set PY=python
where py >NUL 2>&1 && set PY=py -3
if exist ".venv\Scripts\python.exe" set PY=".venv\Scripts\python.exe"
%PY% tools\combine.py %*
echo.
pause
