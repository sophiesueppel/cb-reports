@echo off
REM Daily cb-reports run: sweep all bank sites -> rate/classify -> refresh rate
REM decisions -> regenerate reports -> commit & push HTML. Invoked by the Windows
REM scheduled task "cb-reports daily". Logs append to logs\daily.log.
cd /d "C:\Users\SophieSueppel\Desktop\coding\Central Bank Testimony ratings"
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
echo. >> logs\daily.log
echo ====================================================== >> logs\daily.log
echo Run started %DATE% %TIME% >> logs\daily.log
".venv\Scripts\python.exe" main.py >> logs\daily.log 2>&1
echo Run finished %DATE% %TIME% (exit %ERRORLEVEL%) >> logs\daily.log
