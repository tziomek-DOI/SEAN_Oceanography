@echo off
rem This file is #7_CNV_Create_2023.bat

type #7_CNV_Create_2023.doc

rem Get year and cal file name-----------------------------------------
set /p sb-year=Enter 4-digit year: 
set /p sb-cal=Enter calibration CON file name: 

rem set environment ----------------------------------------------------
set path=%path%;C:\\Program Files\\sea-bird\\sbedataprocessing-win32
REM set sb-base-dir=\\nps\akrdfs\GLBA\science\Data\Oceanography\Data\%sb-year%\
REM set sb-base-dir=C:\dev\projects\SEAN_Oceanography\%sb-year%\
set sb-base-dir=C:\Users\cmurdoch\OneDri~1\Oceanography\File_Processing\%sb-year%\

rem invoke SBEBatch to make CNV from HEX and then plot the CNVs --------
sbebatch #7_CNV_Create_2023.txt %sb-base-dir% %sb-cal%
