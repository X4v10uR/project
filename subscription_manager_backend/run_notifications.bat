@echo off
REM Batch file to run subscription renewal notifications
REM This can be scheduled to run daily using Windows Task Scheduler

cd /d "%~dp0"

echo Starting Subly renewal notifications at %date% %time%
python scheduler.py

if %errorlevel% neq 0 (
    echo ERROR: Notification scheduler failed with exit code %errorlevel%
    pause
) else (
    echo SUCCESS: Notifications completed successfully
)

echo Finished at %date% %time%