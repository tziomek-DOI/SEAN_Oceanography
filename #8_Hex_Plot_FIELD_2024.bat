@echo off

rem This file is #8_Hex_Plot_Field_2024.bat

type #8_Hex_Plot_Field_2024.doc

rem Get year and cal file name-----------------------------------------
set /p sb-year=Enter 4-digit year: 
set /p sb-cal=Enter calibration CON file name: 

rem set environment ----------------------------------------------------
rem set path=%path%;C:\\Program Files (x86)\\sea-bird\\sbedataprocessing-win32
set sb-base-dir=C:\Oceanography\%sb-year%\

rem invoke SBEBatch to make CNV from HEX and then plot the CNVs --------
sbebatch #8_Hex_Plot_Field_2024.txt %sb-base-dir% %sb-cal%