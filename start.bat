@echo off
REM Double-click this on Windows to open the Daily Grace app.
REM The window that appears must stay open while you use it.

cd /d "%~dp0"

python app.py
if errorlevel 1 (
  echo.
  echo Could not start. Is Python installed? https://www.python.org/downloads/
  pause
)
