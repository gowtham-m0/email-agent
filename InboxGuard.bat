@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo   InboxGuard Initializer
echo ==============================================
echo.

:: 1. Check for uv and install it automatically if missing
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 'uv' (Python package manager) is not installed. Installing automatically...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    
    :: Temporarily add common uv install paths to the current session's PATH
    set "PATH=%USERPROFILE%\.cargo\bin;%USERPROFILE%\.local\bin;%PATH%"
    
    where uv >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install 'uv'. Please install it manually.
        pause
        exit /b 1
    )
    echo [INFO] 'uv' installed successfully!
    echo.
)

:: 2. Let uv handle Python and dependencies automatically
echo [INFO] Checking Python and syncing dependencies...
uv sync
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies. Check your internet connection.
    pause
    exit /b 1
)

:: 3. Launch the application
echo.
echo [INFO] Starting InboxGuard...
uv run python main.py

pause
