@echo off
REM Double-click this file to start the tool.
REM
REM It finds Python, downloads the draw history the first time, and opens the
REM app in your browser. Closing this window stops it.

setlocal
cd /d "%~dp0"

REM The reports contain pound signs and dashes. Force UTF-8 so they print on
REM every console codepage rather than raising an encoding error.
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"

echo ======================================================
echo   Lottery Pattern Search
echo ======================================================
echo.

REM --- Find a usable Python -------------------------------------------------
REM "py" is the launcher that ships with python.org installs and is the most
REM reliable. Plain "python" on Windows may be a Microsoft Store stub that
REM does nothing, so each candidate is tested by actually running it.
set "PY="

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"

if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python3"
)

if not defined PY (
    echo Python 3 is not installed, or is too old ^(3.9 or newer is needed^).
    echo.
    echo Install it from:
    echo.
    echo     https://www.python.org/downloads/
    echo.
    echo IMPORTANT: on the first screen of the installer, tick
    echo "Add python.exe to PATH" before clicking Install.
    echo.
    echo Then double-click this file again.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%V in ('%PY% -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%V"
echo Python %PYVER% found.

REM --- Draw history ---------------------------------------------------------
if not exist "data\lotto_draws.csv" (
    echo.
    echo First run - downloading the published draw history.
    echo This takes a few seconds and only happens once.
    echo.
    %PY% -m lotterypatterns fetch
    echo.
    if not exist "data\lotto_draws.csv" (
        echo The download did not work, so the app will start with the sample
        echo data instead. Everything still runs; the numbers are just based on
        echo example draws rather than real ones.
        echo.
    )
) else (
    echo Draw history found.
)

REM --- Go -------------------------------------------------------------------
echo.
echo Starting. Your browser should open in a moment.
echo Leave this window open while you use it. Close it to stop.
echo.

%PY% -m lotterypatterns gui

echo.
echo Stopped.
pause
