@echo off
rem This file is #8_CNV_Create_2024.bat

type #8_CNV_Create_2024.doc

rem Get year and cal file name-----------------------------------------
set /p sb-year=Enter 4-digit year: 
set /p sb-cal=Enter calibration CON file name: 

rem set environment ----------------------------------------------------
set path=%path%;C:\\Program Files\\sea-bird\\sbedataprocessing-win32
set sb-base-dir=\\nps\akrdfs\GLBA\science\Data\Oceanography\Data\%sb-year%\

rem invoke SBEBatch to make CNV from HEX and then plot the CNVs --------
sbebatch #8_CNV_Create_2024.txt %sb-base-dir% %sb-cal%