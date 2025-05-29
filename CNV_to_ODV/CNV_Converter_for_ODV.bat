@echo off
rem CNV_Converter_for_ODV.bat
rem Executes the Powershell script 'cnv_converter_for_ODV.ps1' which generates ODV-friendly CNV files.
rem Must pass in two arguments:
rem 1. name of source directory where the original CNV files are located
rem 2. name of output directory where the ODV-friendly files will be placed.
rem The two directories must NOT be the same, since the filenames will not change.

rem invoke cnv_converter_for_ODV.ps1
rem powershell.exe .\CNV_converter_for_ODV.ps1 c:\\temp\\dev\\DM\\OC\\cnv_source\\ c:\\temp\\dev\\DM\\OC\\cnv_odv\\
set "script=C:\Users\cmurdoch\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\CNV_to_ODV\cnv_converter_for_ODV.ps1"
set "input_dir=C:\Users\cmurdoch\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\CNV_to_ODV\src\"
set "output_dir=C:\Users\cmurdoch\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\CNV_to_ODV\converted\"
rem powershell.exe .\CNV_converter_for_ODV.ps1 "%input_dir%" "%output_dir%"
rem -File is recommended over passing a script name directly, as it properly handles argument parsing.
rem However, it is fragile and couldn't handle the spaces.
rem By switching to -Command and wrapping the entire call in & {} — which PowerShell treats as a block — we were able to:
rem -Properly interpret the script path as a command.
rem -Correctly pass the arguments, preserving spaces and structure.
rem echo Preparing to run the PowerShell script...
echo PowerShell script location: %script%
echo Input directory: %input_dir%
echo Output directory: %output_dir%
rem pause
rem powershell.exe -ExecutionPolicy Bypass -File "%script%" "%input_dir%" "%output_dir%"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
    "& { & '%script%' '%input_dir%' '%output_dir%' }"

rem This one also works, if there are no spaces in the paths:
rem powershell.exe .\CNV_converter_for_ODV.ps1 c:\temp\odv\src\ c:\temp\odv\output\

rem Keep cmd window open to view results
pause
