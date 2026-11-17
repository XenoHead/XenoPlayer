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