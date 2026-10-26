@echo off
setlocal

:: Check if the virtual environment exists
if not exist ".\.venv\Scripts\activate.bat" (
    echo Virtual environment not found at .\.venv\Scripts\
    pause
    exit /b 1
)

:: Activate and run
call ".\.venv\Scripts\activate.bat"
python "%~dp0XenoPlayer.py" %1

:: Keep the window open if the script crashes
if %errorlevel% neq 0 (
    echo.
    echo Script failed with error code %errorlevel%.
    pause
)