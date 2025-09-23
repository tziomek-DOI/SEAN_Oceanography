@echo off
:: enabledelayedexpansion allows for variables to expand within the code blocks
setlocal enabledelayedexpansion

:: Set up script and log file
set "SCRIPT=%~dp0gps_app_v0.4.py"
set "LOGFILE=%~dp0gps_app_log.txt"

echo === Script started at %DATE% %TIME% === >> "%LOGFILE%"

echo Checking for Python...
echo Checking for Python... >> "%LOGFILE%"

:: Check if python is in PATH

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "tokens=*" %%V in ('python --version 2^>nul') do (
        set "PYVERSION=%%V"
        echo Python version "!PYVERSION!" found in PATH.
        echo Python version "!PYVERSION!" found in PATH. >> "%LOGFILE%"
    )
    goto CheckPip
)

:: Check WindowsApps
if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" (
	for /f "tokens=*" %%V in ('python --version 2^>nul') do (
		set "PYVERSION=%%V"
		echo Python version "!PYVERSION!" found in WindowsApps.
		echo Python version "!PYVERSION!" found in WindowsApps. >> "%LOGFILE%"
		set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"
	)
    goto CheckPip
)

:: Check generic Python folder in Program Files
for /d %%D in ("%ProgramFiles%\Python*") do (
    if exist "%%D\python.exe" (
        echo Python found in %%D
        echo Python found in %%D >> "%LOGFILE%"
        set "PATH=%%D;%PATH%"
        goto CheckPip
    )
)

for /d %%D in ("%ProgramFiles(x86)%\Python*") do (
    if exist "%%D\python.exe" (
        echo Python found in %%D
        echo Python found in %%D >> "%LOGFILE%"
        set "PATH=%%D;%PATH%"
        goto CheckPip
    )
)

echo Python not found in PATH or common locations.
echo Python not found in PATH or common locations. >> "%LOGFILE%"
goto End

:CheckPip
echo Checking for pip...
echo Checking for pip... >> "%LOGFILE%"

where pip >nul 2>&1
if %ERRORLEVEL%==0 (
	for /f "tokens=*" %%V in ('pip --version 2^>nul') do set "PIPVERSION=%%V"
    echo pip version "!PIPVERSION!" found.
    echo pip version "!PIPVERSION!" found. >> "%LOGFILE%"
    goto RunScript
)

if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\pip.exe" (
	for /f "tokens=*" %%V in ('pip --version 2^>nul') do set "PIPVERSION=%%V"
    echo pip version "!PIPVERSION!" found in WindowsApps.
    echo pip version "!PIPVERSION!" found in WindowsApps. >> "%LOGFILE%"
    set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"
    goto RunScript
)

echo pip not found.
echo pip not found. >> "%LOGFILE%"
goto End

:RunScript
echo Running gps_app.py...
echo Running gps_app.py... >> "%LOGFILE%"

:: Use a temporary file to capture output
set "TMPLOG=%TEMP%\gps_app_output.tmp"

:: Run the script synchronously and capture output
python "%SCRIPT%" > "%TEMP%\gps_app_output.tmp" 2>&1
set "EXITCODE=%ERRORLEVEL%"

type "%TMPLOG%" >> "%LOGFILE%"

:: Handle success/failure
if %EXITCODE% NEQ 0 (
    echo Error occurred while running %SCRIPT%.
    echo Error occurred while running %SCRIPT%. >> "%LOGFILE%"
    type "%TEMP%\gps_app_output.tmp"
    echo Exit code: %EXITCODE% >> "%LOGFILE%"
    pause
) else (
    echo Script completed successfully.
    echo Script completed successfully. >> "%LOGFILE%"
)

:End
echo.
echo === Script ended at %DATE% %TIME% === >> "%LOGFILE%"
echo. >> "%LOGFILE%" 
endlocal
