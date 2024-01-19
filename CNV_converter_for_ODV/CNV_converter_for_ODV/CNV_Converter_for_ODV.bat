@echo off
rem CNV_Converter_for_ODV.bat
rem Executes the app which generates ODV-friendly CNV files.
rem Must pass in two arguments:
rem 1. name of source directory where the original CNV files are located
rem 2. name of output directory where the ODV-friendly files will be placed.
rem The two directories must not be the same, since the filenames will not change.

rem invoke CNV_converter_for_ODV.exe
CNV_converter_for_ODV.exe c:\\temp\\dev\\DM\\OC\\cnv_source\\ c:\\temp\\dev\\DM\\OC\\cnv_odv\\
