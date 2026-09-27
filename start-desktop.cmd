@echo off
cd /d "%~dp0"
python editor.py
if errorlevel 1 pause
