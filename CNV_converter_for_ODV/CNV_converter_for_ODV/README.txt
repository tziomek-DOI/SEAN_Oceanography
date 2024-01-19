This program is used to modify Sea-Bird CNV files, previously generated from HEX files, to make them "ODV-compatible".

ODV is the Ocean Data View software application. For the purposes of SEAN related to this application, ODV is used as a QA tool to analyze the CNV files generated from the oceanographic CTD's HEX files.

In it's current state, the resulting CNV files have coordinates which are incompatable with ODV. Also, the "bad_flag" in the CNV files is set to an extremely small number in scientific notation, and ODV does not like this either.
SEAN has chosen to replace the "bad_flag" value with the number "-999", which is more inline with traditional oceanographic error checking.

A batch file named CNV_converter_for_ODV.bat is provided, and is launched by the user after modifying (if needed) the arguments. The file contains comments for this.

To build this project with ALL dependencies, so that the user does not need to install any .NET-related dependency packages, open the Package Manager Console, and enter the following command:
dotnet publish -r win-x64

This will make a build folder within the bin directory that includes everything the end user should need. Note that in it's current state, the package, when zipped, is over 29MB in size!

TODO: Need to make a lighter-weight package, as this is much too large for the limited amount of work the app actually does. A script could handle this easily.
