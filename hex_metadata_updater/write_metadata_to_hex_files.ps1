<# 
.SYNOPSIS

Updates the CTD downloaded .hex files with metadata from each station, via the AGOL CSV files from Survey123.

DESCRIPTION

- Reads the survey and station metadata CSV files.
- Matches the survey and station records.
- Finds the matching .hex file, updates the .hex file metadata, and writes the updated content to a new file, preserving the original.

.EXAMPLE

# Assumes the script is in the current/working directory.

PS c:\> .\write_metadata_to_hex_files.ps1 <hex_dir> <survey_csv_file> <station_csv_file>

PS c:\> .\write_metadata_to_hex_files.ps1 c:\oc\hex_files\ c:\oc\csv_files\glba_oc_survey_metadata.csv c:\oc\csv_files\glba_oc_station_metadata.csv

.INPUTS

.PARAMETER 
    The directory containing the source .HEX files.

.PARAMETER 
    The full path and filename of the CSV file containing the survey metadata.

.PARAMETER
    The full path and filename of the CSV file containing the station metadata.

.OUTPUTS
    Return a code = 0 if program ran successfully. Any value other than 0 means an error occurred.

.NOTES
    Any errors that occur should display an associated message in the terminal window.

#>

class HexFileMetadata {
    [string] $_hex_file_dir
    [string] $_survey_metadata
    [string] $_station_metadata
    [object[]] $_merged_data
    [string] $_yyMM
    [bool] $_is_production

    # Constructor:
    HexFileMetadata([string]$hex_file_dir, [string]$survey_metadata_csv, [string]$station_metadata_csv) {

        $this._merged_data = @()
        $this._hex_file_dir = ""
        $this._survey_metadata = ""
        $this._station_metadata = ""
        $this._yyMM = ""
        $this._is_production = $false

        if (Test-Path $hex_file_dir) {
            $this._hex_file_dir = Convert-Path $hex_file_dir
        } else {
            throw "Invalid .hex files directory: '$($hex_file_dir)'."
        }

        if (Test-Path $survey_metadata_csv) {
            $this._survey_metadata = Convert-Path $survey_metadata_csv
        } else {
            throw "Survey metadata file Not Found: '$($survey_metadata_csv)'."
        }

        if (Test-Path $station_metadata_csv) {
            $this._station_metadata = Convert-Path $station_metadata_csv
        } else {
            throw "Station metadata file not found: '$station_metadata_csv'."
        }
        
    } # end CTOR HexFileMetadata

    <# function MergeCsvData
     # Finds the matching records from the survey and station CSV files, and writes a new record containing select fields from the two input records.
     # The merged data is saved in an array class variable, and used later.
     #>
    [void] MergeCsvData() {

        $stationData = Import-Csv -Path $this._station_metadata
        $surveyData = Import-Csv -Path $this._survey_metadata

        $mergedData = foreach ($child in $stationData) {
            $parent = $surveyData | Where-Object { $_.GlobalID -eq $child.ParentGlobalID }
            if ($parent) {
                Log-Message "info" "Found match for parent '$($parent.GlobalID)'..."

                [PSCustomObject]@{
                    Cruise              = $parent.Cruise
                    Vessel              = $parent.Vessel
                    'Other Vessel'      = $parent.'Other Vessel'
                    Observer            = $parent.Observers
                    'CTD#'              = $parent.'CTD Number'
                    'Dump#'             = $parent.data_dump_number
                    'Cast#'             = $child."Cast Number"
                    Station             = $child.Station
                    Latitude            = $child.Latitude
                    Longitude           = $child.Longitude
                    StationObjectID     = $child.ObjectID
                    GlobalID            = $parent.GlobalID # can remove this, just checking
                    ChildGlobalID       = $child.ParentGlobalID # can remove this, just checking
                    'Date GMT'          = $child.Date
                    'Time GMT'          = $child.Time
                    'Fathometer Depth'  = $child.'Fathometer Depth'
                    'Target Depth'      = $child.'Target Depth'
                    Comments            = $child.Comments
                }
            }
        }

        $this._merged_data = $mergedData

        # Export the merged data to a new CSV file for dev/debug purposes.
        # TODO: Remove this in production.
        if (-not $this._is_production) {
            $dataDir = Split-Path $this._station_metadata
            $mergedData | Export-Csv -Path "$dataDir\glba_oc_merged_survey_data.csv" -NoTypeInformation
        }
    } # end MergeCsvData

    <# function MatchHexFiles
     # Uses the metadata from the merged data to locate the associated .hex files.
     # When a match is found, it will call another function to update the file metadata.
     #>
    [void] MatchHexFiles() {

        $HexFolder = $this._hex_file_dir
        $records = @()
        $records = $this._merged_data
        $tempRow = $null

        if (-not $records -or $records.Count -eq 0) {
            Log-Message "error" "No records found in the merged data."
            return
        }

        Log-Message "info" "Processing $($records.Count) records..."

        foreach ($row in $records) {
            $tempRow = $row # used for logging error info
            try {
                # Parse date and extract YYMM
                # Note that this only works if the .hex files were downloaded during the same month as the survey was conducted.
                # For now, this matching is disabled. Instead, the YYMM of the .hex files will be obtained by parsing the first
                # .hex file in the directory. The assumption is all files were downloaded during the same month/year.
                #Write-Host "Parsing date '$($row.'Date GMT')'..."
                #$date = [datetime]::ParseExact($row.'Date GMT', 'M/d/yyyy HH:mm', $null) # Keep in case this is useful later, otherwise remove/comment.
                #$yymm = $date.ToString("yyMM")
                
                # This only needs to be done once, if we assume all files have the same yyMM.
                #$yymm = GetYearMonthFromFilename
                #$yyMM = $this._yyMM

                # Pad fields
                $ctd    = $row.'CTD#'
                $dump   = "{0:D4}" -f [int]$row.'Dump#'
                $cast   = "{0:D3}" -f [int]$row.'Cast#'
                $station = "{0:D2}" -f [int]$row.'Station'

                $expectedFilename = "$($this._yyMM)_$($ctd)_$($dump)_$($cast)_$($station).hex"
                $expectedPath = Join-Path $HexFolder $expectedFilename
                Log-Message "info" "Expected filename (station $($station): $($expectedPath)"

                if (Test-Path $expectedPath) {
                    Log-Message "info" "✅ Found: $expectedFilename"

                    # Construct a hashtable with all the necessary data:

                    # Note: For now we will grab the first observer in the array.
                    #$observers = $row.Observers -split "," | ForEach-Object { $_.Trim() }
                    $observers = $row.Observer -split ","
                    $dateGMT = [datetime]::Parse($row.'Date GMT')
                    $timeGMT = [datetime]::Parse($row.'Time GMT') 

                    # Need to convert the local date/time variables into UTC:
                    $dateUTC = $null
                    $timeUTC = $null

                    if (-not ([HexFileMetadata]::ConvertLocalDateTimeToUTC($dateGMT, $timeGMT, [ref]$dateUTC, [ref]$timeUTC))) {
                        Log-Message "error" "Failed to convert '$($dateGMT)' and/or '$($timeGMT)' to UTC time."
                    } else {
                        Log-Message "info" "UTC date = $dateUTC, time = $timeUTC"
                    }

                    $updatedFields = @{
                        "Vessel" = $row.Vessel
                        "CTD#" = $ctd
                        "Dump#" = $dump
                        "Observer" = $observers[0]
                        "Cast#" = $cast
                        "Station" = $station
                        "Latitude" = $row.Latitude
                        "Longitude" = $row.Longitude
                        #"Date GMT" = $dateGMT.ToString("MM/dd/yyyy") # Need to reformat, currently '5/30/2025 20:00'
                        #"Time GMT" = $timeGMT.ToString("HH:mm") # Need to reformat, currently '8:24'
                        #"Date GMT" = $dateUTC.ToString("MM/dd/yyyy") # Need to reformat, currently '5/30/2025 20:00'
                        #"Time GMT" = $timeUTC.ToString("HH:mm") # Need to reformat, currently '8:24'
                        "Date GMT" = $dateUTC
                        "Time GMT" = $timeUTC
                        "Fathometer depth" = $row.'Fathometer Depth'
                        "Cast target depth" = $row.'Target Depth'
                        "Comments" = $row.Comments
                    }


                    if (-not $this.WriteHexFileMetadata($expectedPath, $updatedFields)) {
                        Log-Message "error" "The call to WriteHexFileMetadata failed on file '$($expectedFilename)'."
                        break
                    }
                } else {
                    Log-Message "warning" "❌ No match for StationObjectID: $($row.StationObjectID)"
                }
            } catch {
                Log-Message "error" "Error processing row: $($_.Exception.Message)"
                Log-Message "error" "Current row: $tempRow"
            }

        } # end foreach
    } # end Match-HexFiles

    <# function GetYearMonthFromFilename
     # Reads the first four characters of the first .hex file found, and stores this for use when matching the .hex filenames.
     #>
    [void] GetYearMonthFromFilename() {

        # Get the first .hex file in the folder. If none are found, the variable will be empty. No error is generated.
        $firstHexFile = Get-ChildItem -Path $this._hex_file_dir -Filter '*.hex' | Sort-Object Name | Select-Object -First 1

        if (-not $firstHexFile) {
            throw "No .hex files found in '$($this._hex_file_dir)'."
        }

        # Extract the first 4 characters
        $yyMM = $firstHexFile.BaseName.Substring(0, 4)

        # Optional: Validate the extracted yyMM format
        if ($yyMM -notmatch '^\d{4}$') {
            throw "The filename '$($firstHexFile.Name)' does not start with a valid yyMM format."
        }

        # Output the result
        Log-Message "info" "Extracted yyMM: $yyMM from file: $($firstHexFile.Name)"
        $this._yyMM = $yyMM

    } # end GetYearMonthFromFilename

    <# function WriteHexFileMetadata
     # Writes the metadata info into the matched .hex file.
     # Returns $true for success, $false for errors.
     #>
    [bool] WriteHexFileMetadata([string] $hexFile, [hashtable] $updatedFields) {
        [bool] $retval = $false
        $psVer = $global:PSVersionTable.PSVersion.Major

        Log-Message "info" "In WriteHexFileMetadata, processing file '$($hexFile)'..."

        try {
            try {
                $hexFilePath = [System.IO.Path]::GetDirectoryName($hexFile)
                Log-Message "info" "Hex files directory = $($hexFilePath)"
                $hexFilePathNew = Join-Path -Path $hexFilePath -ChildPath "hex_files_with_metadata"

            } catch {
                Log-Message "warning" "Failed to set the new subdirectory 'hex_files_with_metadata'."
                throw $_.Exception.Message
            }

            try {
                if (Test-Path -Path $hexFilePathNew -PathType Container) {
                    Log-Message "info", "Directory '$($hexFilePathNew)' found..."
                } else {
                    $createdDir = New-Item -Path $hexFilePathNew -ItemType Directory -ErrorAction Stop

                    if ($null -ne $createdDir -and $createdDir.Exists) {
                        Log-Message "info" "Successfully created: $($createdDir.FullName)"
                    } else {
                        Log-Message "warning" "New-Item did not throw an error, but the folder does not exist."
                    }
                }
            }
            catch {
                Log-Message "error" "Error in WriteHexFileMetadata:`n$($_.Exception.Message)"
                throw "Failed to create directory: $($_.Exception.Message)"
            }

            $lines = Get-Content $hexFile
            Log-Message "info" "Retrieved $($lines.Count) lines from file $($hexFile)..."

            # Define the lines to update (these are the fields we care about)
            
            $fieldsToUpdate = @(
                "Vessel",
                "CTD#",
                "Dump#",
                "Observer",
                "Cast#",
                "Station",
                "Latitude",
                "Longitude",
                "Date GMT",
                "Time GMT",
                "Fathometer depth",
                "Cast target depth"
            )
            
            # Create updated content
            Log-Message "info" "Updating the metadata fields in file '$($hexFile)'..."

            $updatedLines = $lines | ForEach-Object {
                $line = $_
                foreach ($field in $fieldsToUpdate) {
                    if ($line -match "^\*\* $([regex]::Escape($($field)))\s*:") {
                        #Log-Message "info" "updatedFields[$($field)] = $($updatedFields[$field])"
                        $newValue = $updatedFields[$field]
                        # We need to insert Comments after 'Cast target depth'
                        if ($field -eq "Cast target depth") {
                            return "** $($field):$($newValue)", "** Comments:$($updatedFields['Comments'])"
                        } else {
                            return "** $($field):$($newValue)"
                        }
                    }
                }
                return $line
            }
            
            # The updated .hex file should be saved to a new subdirectory, so that we retain the original.
            $updatedFile = Join-Path -Path $hexFilePathNew -ChildPath ([System.IO.Path]::GetFileName($hexFile))
            Log-Message "info" "Writing updated .hex content to file '$($updatedFile)'..."

            # Don't use -Encoding UTF8, as it actually encodes as UTF-8-BOM (byte order mark)
            # This will work in multiple PS versions:
            if ($psVer -ge 7) {
                $updatedLines | Set-Content -Path $updatedFile -Encoding utf8noBOM
            } else {
                $utf8noBom = New-Object System.Text.UTF8Encoding($false)
                [System.IO.File]::WriteAllLines($updatedFile, $updatedLines, $utf8noBom)
            }

            Log-Message "info" "File $($updatedFile) successfully updated."
            $retval = $true

        } catch {
            Log-Message "error" "In WriteHexFileMetadata, external catch block: $($_.Exception.Message)"
        }

        return $retval
    }


    # ConvertLocalDateTimeToUTC
    # Does what it says, and also converts back to local time as an extra check.
    #function ConvertLocalDateTimeToUTC([string] $dateLocal, [string] $timeLocal) {
    static [bool] ConvertLocalDateTimeToUTC(
        [string] $dateLocal, 
        [string] $timeLocal,
        [ref] $dateUTC,
        [ref] $timeUTC
    ) {

        [bool]$retval = $false # return variable to indicate success/failure
        [string]$localDTcombined = ""

        try {
            # Time zone object for Alaska (handles DST automatically)
            $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Alaskan Standard Time")

            # Combine into one DateTime string and parse
            $localDTcombined = "$((Get-Date $dateLocal).ToString("MM/dd/yyyy")) $((Get-Date $timeLocal).ToString("HH:mm"))"
            Log-Message "info" "Combined local time: $($localDTCombined)."
            $localDateTime = [datetime]::ParseExact($localDTcombined, "MM/dd/yyyy HH:mm", $null)
            <#
            $localDateTime = [datetime]::ParseExact(
                "$dateLocalDateOnly $timeLocal",
                "MM/dd/yyyy HH:mm",
                $null
            )
            #>

            # Treat as Alaska local time
            $localDateTime = [System.TimeZoneInfo]::ConvertTime($localDateTime, $tz)

            # Convert to UTC
            $utcDateTime = [System.TimeZoneInfo]::ConvertTimeToUtc($localDateTime, $tz)

            # Split into date + time variables, and store them in the reference parameters:
            $dateUTC.Value = $utcDateTime.ToString("MM/dd/yyyy")
            $timeUTC.Value = $utcDateTime.ToString("HH:mm")

            Write-Host "Local Alaska time: $dateLocal $timeLocal"
            Write-Host "Converted UTC time: $dateUTC $timeUTC"

            # --- Round-trip check: UTC → Alaska ---
            $backToLocal = [System.TimeZoneInfo]::ConvertTimeFromUtc($utcDateTime, $tz)

            $retval = $true

        } catch {
            #Log-Message "error" "Error in WriteHexFileMetadata:`n$($_.Exception.Message)"
            Log-Message "error" "Error in ConvertLocalDateTimeToUTC:`n$($_.Exception.Message)"
            $msg = "Failed to convert the date '$($dateLocal)'/ time '$($timeLocal)', combined into '$($localDTcombined)' correctly (or at all)."
            Log-Message "error" $msg
            throw $msg
        }
        Write-Host "Round-trip back to Alaska local: $($backToLocal.ToString('MM/dd/yyyy HH:mm'))"
        return $retval
    }

} # end class

# Define a return value for feedback to the calling batch file:
$result = -999
$logFile = ".\write_metadata_to_hex_files.log"

# Functions to customize logging messages:
function Log-Message([string]$msgType, [string]$msg) {
    #Write-Host "In Log-Message, msgType = $msgType, msg = $msg"
    $logMsg = ""
    if ($msgType -eq "info") {
        $logMsg = "[INFO]: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $($msg)"
        Write-Host $logMsg
    } elseif ($msgType -eq "warning") {
        $logMsg = "[WARN]: $($msg)"
        Write-Warning $logMsg
    } else {
        $logMsg = "[ERROR]: $($msg)"
        Write-Error $msg
    }

    Log-To-File($logMsg)
}

function Log-To-File($msg) {
   Add-Content -Path $logFile -Value $msg -Encoding UTF8
} 

Log-Message "info" "Starting the 'write_metadata_to_hex_files.ps1' script..."

if ($args.Count -ne 3) {
    Log-Message "error" "ERROR! Must pass in the .HEX files directory, and the full path and filenames for the survey and station metadata CSV files."
    $result = -3
} else {
    try {
        Log-Message "info" "args:"
        Log-Message "info" ".HEX files directory: $($args[0])"
        Log-Message "info" "Survey metadata CSV: $($args[1])"
        Log-Message "info" "Station metadata CSV: $($args[2])"

        $metadata = [HexFileMetadata]::new($args[0], $args[1], $args[2])
        $metadata.GetYearMonthFromFilename()
        $metadata.MergeCsvData()
        $metadata.MatchHexFiles()
        $result = 0
    } catch {
        Log-Message "error" $_.Exception.Message
        $result = -1
    } finally {
        Log-Message "info" "Program completed with code $result (0 indicates success)."
        Log-Message "info" "==========================================================`n"
    }
        
}

