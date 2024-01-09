@echo off
rem CNV_Converter_for_ODV.bat
rem Executes the Powershell script 'cnv_converter_for_ODV.ps1' which generates ODV-friendly CNV files.
rem Must pass in two arguments:
rem 1. name of source directory where the original CNV files are located
rem 2. name of output directory where the ODV-friendly files will be placed.
rem The two directories must NOT be the same, since the filenames will not change.

rem invoke cnv_converter_for_ODV.ps1
powershell.exe .\CNV_converter_for_ODV.ps1 c:\\temp\\dev\\DM\\OC\\cnv_source\\ c:\\temp\\dev\\DM\\OC\\cnv_odv\\

rem Keep cmd window open to view results
pause
