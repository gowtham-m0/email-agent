@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo   InboxGuard Initializer
echo ==============================================
echo.

where uv >nul 2>&1
if not errorlevel 1 goto uv_ready

echo [INFO] uv is not installed. Installing automatically...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
set "PATH=%USERPROFILE%\.cargo\bin;%USERPROFILE%\.local\bin;%PATH%"

where uv >nul 2>&1
if not errorlevel 1 goto uv_ready

echo [ERROR] Failed to install uv. Please install it manually.
goto done_error

:uv_ready
echo [INFO] Checking Python and syncing dependencies...
call uv sync
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies. Check your internet connection.
    goto done_error
)

echo.
echo [INFO] Starting InboxGuard...
call uv run python main.py
set "APP_EXIT=%ERRORLEVEL%"
echo.
if not "%APP_EXIT%"=="0" (
    echo [ERROR] InboxGuard exited with code %APP_EXIT%.
    goto done_error
)

goto done

:done_error
echo.
echo [INFO] The window will stay open so you can read the error.

:done
echo [INFO] Press any key to close this window.
pause >nul
endlocal