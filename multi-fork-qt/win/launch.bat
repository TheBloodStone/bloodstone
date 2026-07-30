@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONHOME=%ROOT%python"
set "PATH=%PYTHONHOME%;%PATH%"
set "PYTHONPATH=%ROOT%app"
REM Stay in install root so bundled daemons\STONE|AZURE|LRGK are discoverable
cd /d "%ROOT%"
start "" "%PYTHONHOME%\pythonw.exe" "%ROOT%app\main.py" %*
endlocal
