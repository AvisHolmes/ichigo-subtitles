@echo off
chcp 65001 >nul
rem Установка Ichigo: окружение Python и зависимости, ярлык на рабочем столе, первый запуск.
rem Словари выбираются и скачиваются в самой программе (мастер настройки при первом запуске).
rem Нужен Python 3.12 (py launcher). Кэш pip и временные файлы — в папке cache, а не на диске C.
cd /d "%~dp0"
set "PIP_CACHE_DIR=%~dp0cache\pip"
set "TEMP=%~dp0cache\tmp"
set "TMP=%~dp0cache\tmp"
if not exist cache\tmp mkdir cache\tmp
if not exist .venv py -3.12 -m venv .venv || goto :err
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :err
.venv\Scripts\python.exe app\shortcut.py || echo Не удалось создать ярлык / could not create the shortcut
echo.
echo Готово. Ярлык «Ichigo» — на рабочем столе. Done: the "Ichigo" shortcut is on your desktop.
start "" ".venv\Scripts\pythonw.exe" app\gui.py
exit /b 0
:err
echo.
echo Ошибка установки, см. сообщения выше. Setup failed, see the messages above.
pause
exit /b 1
