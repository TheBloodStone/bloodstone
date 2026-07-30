@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONHOME=%ROOT%python"
set "PATH=%PYTHONHOME%;%PATH%"
set "PYTHONPATH=%ROOT%app"
REM Stay in install root so bundled daemons\ are discoverable
cd /d "%ROOT%"
"%PYTHONHOME%\python.exe" "%ROOT%app\main.py" %*
echo.
echo Exit code %ERRORLEVEL%
pause
endlocal
