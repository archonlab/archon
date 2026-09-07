@echo off
setlocal EnableExtensions

rem ARCHON Studio Windows launcher.
rem Keep platform-specific logic here; the canonical desktop lifecycle lives in
rem Tools\archon_studio_desktop.py for every supported operating system.

cd /d "%~dp0" || goto :cd_error
set "ARCHON_ROOT=%CD%"

where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%ARCHON_ROOT%\Tools\archon_studio_desktop.py" --root "%ARCHON_ROOT%" %*
    set "ARCHON_EXIT=%ERRORLEVEL%"
    goto :done
)

where python3 >nul 2>&1
if not errorlevel 1 (
    python3 "%ARCHON_ROOT%\Tools\archon_studio_desktop.py" --root "%ARCHON_ROOT%" %*
    set "ARCHON_EXIT=%ERRORLEVEL%"
    goto :done
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)" >nul 2>&1
    if not errorlevel 1 (
        python "%ARCHON_ROOT%\Tools\archon_studio_desktop.py" --root "%ARCHON_ROOT%" %*
        set "ARCHON_EXIT=%ERRORLEVEL%"
        goto :done
    )
)

echo.
echo ARCHON Studio could not find Python 3.
echo Install Python 3 and enable the Python Launcher ^(py^) or add Python to PATH.
set "ARCHON_EXIT=127"
goto :error_pause

:cd_error
echo.
echo ARCHON Studio could not open its installation directory.
set "ARCHON_EXIT=2"
goto :error_pause

:done
if "%ARCHON_EXIT%"=="0" exit /b 0

echo.
echo ARCHON Studio exited with code %ARCHON_EXIT%.

:error_pause
rem Keep diagnostics visible when launched by double-click.
pause
exit /b %ARCHON_EXIT%
