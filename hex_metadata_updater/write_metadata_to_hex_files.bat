@echo off
rem write_metadata_to_hex_files.bat
rem This batch file launches a PowerShell script, which reads the AGOL CSV files from OC Survey123,
rem and updates the .hex files with the metadata for each station.

rem Must pass in three arguments:
rem 1. Name of directory where the original HEX files are located.
rem 2. Path and filename of the 'survey' metadata CSV file from Survey123/AGOL.
rem 3. Path and filename of the 'station' metadata CSV file from Survey123/AGOL.

rem The script will create a subdirectory inside the original HEX files directory.
rem This directory will be named 'hex_files_with_metadata'.
rem The updated .hex files will be placed in this subdirectory, so that the originals will remain intact.
rem A log file named 'write_metadata_to_hex_files.log' is written to the same directory as the script location.

rem The paths below assume the script will be run from a user's OneDrive.
rem For ease, a variable called %username% is set here. Change this value to the user who runs the script from their workstation.
set /p username="Enter username (for OneDrive path): " 

rem invoke write_metadata_to_hex_files.ps1
set "script=C:\Users\%username%\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\hex_metadata_updater\write_metadata_to_hex_files.ps1"
set "hex_files_dir=C:\Users\%username%\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\hex_metadata_updater\data\hex_files\"
set "survey_csv=C:\Users\%username%\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\hex_metadata_updater\data\glba_oc_survey_metadata.csv"
set "station_csv=C:\Users\%username%\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\hex_metadata_updater\data\glba_oc_survey_station_data.csv"

rem echo Preparing to run the PowerShell script...
echo Preparing to run the script for user '%username%'. Settings:
echo PowerShell script location: %script%
echo Original .HEX filed directory: %hex_files_dir%
echo Input directory: %survey_csv%
echo Output directory: %station_csv%

rem pause
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
    "& { & '%script%' '%hex_files_dir%' '%survey_csv%' '%station_csv%' }"

rem This keeps the cmd window open to view results
pause
