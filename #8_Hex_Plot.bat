@echo off

rem This file is #7_Hex_Plot_2023.bat
rem Replacement of #5_Hex_Plot_2014+.bat, for use with CTD #7.

type #8_hex_plot_header.txt

rem Get year and cal file name-----------------------------------------
set /p sb-year=Enter 4-digit year: 
set /p sb-cal=Enter calibration CON file name: 

rem set environment ----------------------------------------------------
set path=%path%;C:\Program Files\sea-bird\sbedataprocessing-win32
set sb-base-dir=C:\dev\projects\SEAN_Oceanography\%sb-year%\

rem invoke SBEBatch to make CNV from HEX and then plot the CNVs --------
sbebatch #8_Hex_Plot.txt %sb-base-dir% %sb-cal%
