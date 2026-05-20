@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set PYTHONUTF8=1
"%PROJECT_ROOT%\venv\Scripts\python.exe" "%PROJECT_ROOT%\src\hevelius-runner.py" %*
