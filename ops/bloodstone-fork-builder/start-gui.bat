@echo off
cd /d "%~dp0"
python fork_builder.py gui
if errorlevel 1 py -3 fork_builder.py gui
pause
