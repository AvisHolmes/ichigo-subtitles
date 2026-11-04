@echo off
rem Запуск программы-окна без консоли. Лог: cache\ichigo.log
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" app\gui.py
