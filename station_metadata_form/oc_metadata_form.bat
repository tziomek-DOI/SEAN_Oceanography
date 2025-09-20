@echo off

REM Check if Python is already in PATH
REM ---------------------------------------------------
where python >nul 2>&1
IF %ERRORLEVEL%==0 (
    echo Python found in PATH.
) ELSE (
    REM - Try Microsoft Store location
    SET PYTHON_DIR=%LOCALAPPDATA%\Microsoft\WindowsApps
    IF EXIST "%PYTHON_DIR%\python.exe" (
        SET PATH=%PYTHON_DIR%;%PATH%
        echo Added Microsoft Store Python to PATH
    ) ELSE (
        REM - Try user Python installs
        SET FOUND_PYTHON=
        FOR /D %%D IN ("%LOCALAPPDATA%\Programs\Python\Python*") DO (
            IF EXIST "%%D\python.exe" (
                SET FOUND_PYTHON=%%D
                GOTO :foundpython
            )
        )
        :foundpython
        IF NOT "%FOUND_PYTHON%"=="" (
            SET PATH=%FOUND_PYTHON%;%PATH%
            echo Added user Python at %FOUND_PYTHON% to PATH
        ) ELSE (
            echo Python not found in PATH, Microsoft Store, or user install folders.
            pause
            exit /b 1
        )
    )
)

REM Optional: confirm Python is available
python --version
pip --version

REM Step 4: Run your Python script in the same folder as this batch file
python "%~dp0gps_app.py"

pause
