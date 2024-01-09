The file CNV_Converter_for_ODV.bat is the only file that needs to be customized, if the user wants to decide where to place the source and converted .CNV files.

The actual program is now a Powershell script named CNV_Converter_for_ODV.ps1, and it is fired off when the CNV_Converter_for_ODV.bat file is run. The .bat file must pass two directory paths to the .exe:
path 1: Name of source directory where the original CNV files are located
path 2: name of output directory where the converted, ODV-friendly files will be placed.
*Note: The two directories must NOT be the same, since the filenames will not change during conversion.

The paths defined in the default .bat file are examples. One could recreate this directory structure, place the source CNV files inside, and run the app, or, one could change these paths. It's important to use two backslashes in the paths!

Assuming the user was to keep the default structure, the following is one way to manage the structure to keep each month's source and converted CNVs organized:

- If this is the first cruise of the year (winter cruise), if not already done, use Windows Explorer to create a subdirectory inside "cnv_source" for the new cruise year, then another subdirectory for the month of the cruise, such as:
..\CNV_to_ODV\cnv_source\
..\CNV_to_ODV\cnv_source\YYYY\ (where YYYY is the new/current cruise year)
..\CNV_to_ODV\cnv_source\YYYY\month\ (where month is the current month being analyzed)

- For subsequent months of the same year, simply create a new "month" directory each month, then change the path in the .bat file to match.

# Running the program
The user can create a shortcut to the .bat file on their desktop or other desired location. Then simply double-click the shortcut. The Windows command window will appear, and the program will attempt to run using the directories specified inside the .bat file, as mentioned previously. Once the program completes, the command window will remain open so the user may review the results.

