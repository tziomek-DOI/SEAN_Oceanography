@echo off

rem This file is #8_Hex_Plot_Field.bat

type #8_Hex_Plot_FIELD_header.txt

rem Get year and cal file name-----------------------------------------
set /p sb-year=Enter 4-digit year: 
set /p sb-cal=Enter calibration CON file name: 

rem set environment ----------------------------------------------------
rem set path=%path%;C:\\Program Files (x86)\\sea-bird\\sbedataprocessing-win32
rem set sb-base-dir=C:\dev\projects\SEAN_Oceanography\%sb-year%\
set sb-base-dir=C:\Users\cmurdoch\OneDri~1\Oceanography\File_Processing\%sb-year%\

rem invoke SBEBatch to make CNV from HEX and then plot the CNVs --------
sbebatch #8_hex_plot_FIELD.txt %sb-base-dir% %sb-cal%
