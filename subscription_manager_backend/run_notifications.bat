@echo off
setlocal
REM Batch file to run subscription renewal notifications
REM This can be scheduled to run daily using Windows Task Scheduler

cd /d "%~dp0"

echo Starting DUES renewal notifications at %date% %time%
set "NOTIFICATION_PYTHON=python"
if exist "%~dp0..\.venv\Scripts\python.exe" set "NOTIFICATION_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "NOTIFICATION_PYTHON=%~dp0.venv\Scripts\python.exe"
"%NOTIFICATION_PYTHON%" "%~dp0scheduler.py" %*
set "NOTIFICATION_EXIT=%errorlevel%"

if %NOTIFICATION_EXIT% neq 0 (
    echo ERROR: Notification scheduler failed with exit code %NOTIFICATION_EXIT%
) else (
    echo SUCCESS: Notifications completed successfully
)

echo Finished at %date% %time%
exit /b %NOTIFICATION_EXIT%
