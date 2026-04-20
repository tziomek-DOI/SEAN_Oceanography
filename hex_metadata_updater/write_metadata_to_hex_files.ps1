<# 
.SYNOPSIS

Updates the CTD downloaded .hex files with metadata from each station, via the CSV file from the 'oc_station_metadata_form' app.

.DESCRIPTION

- Reads the survey and station metadata CSV file.
- Finds the matching .hex file, updates the .hex file metadata, and writes the updated content to a new file, preserving the original.

.VERSION
1.1

.LASTMODIFIED
20-APR-2026

.EXAMPLE

# Assumes the script is in the current/working directory.

PS c:\> .\write_metadata_to_hex_files.ps1 <hex_dir> <metadata_csv_file>

PS c:\> .\write_metadata_to_hex_files.ps1 c:\oc\hex_files\ c:\oc\csv_files\oc_station_metadata.csv

.INPUTS

.PARAMETER 
    The directory containing the source .HEX files.

.PARAMETER 
    The full path and filename of the CSV file containing the survey and station metadata.

.OUTPUTS
    Return a code = 0 if program ran successfully. Any value other than 0 means an error occurred.

.NOTES
    Any errors that occur should display an associated message in the terminal window.

#>

class HexFileMetadata {
    [string] $_hex_file_dir
    [string] $_metadata_csv
    [object[]] $_merged_data
    [string] $_yyMM
    [bool] $_is_production
    [int] $_matched_recs_count
    [int] $_unmatched_recs_count

    # Constructor:
    HexFileMetadata([string]$hex_file_dir, [string]$metadata_csv) {

        $this._merged_data = @()
        $this._hex_file_dir = ""
        $this._metadata_csv = ""
        $this._yyMM = ""
        $this._is_production = $false
        $this._matched_recs_count = 0
        $this._unmatched_recs_count = 0

        if (Test-Path $hex_file_dir) {
            $this._hex_file_dir = Convert-Path $hex_file_dir
        } else {
            throw "Invalid .hex files directory: '$($hex_file_dir)'."
        }

        if (Test-Path $metadata_csv) {
            $this._metadata_csv = Convert-Path $metadata_csv
        } else {
            throw "Metadata CSV file Not Found: '$($metadata_csv)'."
        }
        
    } # end CTOR HexFileMetadata

    [string] NormalizeString([string]$value) {
        if ($null -eq $value) { return $null }
        return $value.Trim()
    }

    [PSCustomObject] NormalizeRow([PSCustomObject]$row) {

        foreach ($prop in $row.PSObject.Properties) {
            if ($prop.Value -is [string]) {
                $prop.Value = $this.NormalizeString($prop.Value)
            }
        }

        $row.ctd = [int]$row.ctd
        $row.dump = [int]$row.dump
        $row.cast = [int]$row.cast
        $row.station = "{0:D2}" -f [int]$row.station

        $row.decimalLatitude = [double]$row.decimalLatitude
        $row.decimalLongitude = [double]$row.decimalLongitude

        return $row
    }

    [void] ValidateRow([pscustomobject]$row, [int]$index) {

        if (-not $row.eventDate) {
            throw "Row $($index): Missing eventDate"
        }

        try {
            [datetime]::Parse($row.eventDate) | Out-Null
        } catch {
            throw "Row $index (Station $($row.station), Cast $($row.cast)): Invalid eventDate '$($row.eventDate)'"
        }

        if ($row.decimalLatitude -lt -90 -or $row.decimalLatitude -gt 90) {
            throw "Row $index (Station $($row.station), Cast $($row.cast)): Invalid latitude '$($row.decimalLatitude)'"
        }

        if ($row.decimalLongitude -lt -180 -or $row.decimalLongitude -gt 180) {
            throw "Row $index (Station $($row.station), Cast $($row.cast)): Invalid longitude '$($row.decimalLongitude)'"
        }

        if (-not $row.station) {
            throw "Row $index (Timestamp $($row.eventDate)): Missing station"
        }
    }

    <# function LoadCsvData
     # Loads the data collected and exported into the metadata CSV file.
     # The loaded data is saved in an array class variable, and used later.
     #>
    [void] LoadCsvData() {

        $csvData = Import-Csv -Path $this._metadata_csv

        $processedData = @()

        for ($i = 0; $i -lt $csvData.Count; $i++) {

            $row = $this.NormalizeRow($csvData[$i])
            $this.ValidateRow($row, $i)

            # Use datetimeoffset to prevent possible implicit conversion to local time:
            #$dt = [datetime]::Parse($row.eventDate)
            $dto = [datetimeoffset]::Parse($row.eventDate)
            $dt = $dto.UtcDateTime

            $processedData += [PSCustomObject]@{
                Cruise              = $row.cruise
                Vessel              = $row.vessel
                Observer            = $row.observers
                'CTD#'              = $row.ctd
                'Dump#'             = $row.dump
                'Cast#'             = $row.cast
                Station             = $row.station
                Latitude            = $row.decimalLatitude
                Longitude           = $row.decimalLongitude
                'Date GMT'          = $dt.ToString("MM/dd/yyyy")
                'Time GMT'          = $dt.ToString("HH:mm")
                'Fathometer Depth'  = $row.fathometer_depth
                'Target Depth'      = $row.target_depth
                Comments            = $row.fieldNotes
            }
        }

        $duplicates = $processedData |
            Group-Object Station, 'Cast#' |
            Where-Object { $_.Count -gt 1 }

        if ($duplicates) {
            throw "Duplicate station/cast combinations detected. Fix your CSV before proceeding."
        }

        $this._merged_data = $processedData
    }

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

                #$expectedFilename = "$($this._yyMM)_$($ctd)_$($dump)_$($cast)_$($station).hex"
                $dateUTC = [datetime]::ParseExact($row.'Date GMT', 'MM/dd/yyyy', $null)
                $timeUTC = [datetime]::ParseExact($row.'Time GMT', 'HH:mm', $null)
                $expectedFilename = "$($dateUTC.ToString('yyMM'))_$($ctd)_$($dump)_$($cast)_$($station).hex"
                $expectedPath = Join-Path $HexFolder $expectedFilename
                Log-Message "info" "Expected filename (station $($station): $($expectedPath)"

                if (Test-Path $expectedPath) {
                    Log-Message "info" "✅ Found: $expectedFilename"
                    $this._matched_recs_count++

                    # Construct a hashtable with all the necessary data:

                    # Note: For now we will grab the first observer in the array.
                    #$observers = $row.Observers -split "," | ForEach-Object { $_.Trim() }
                    $observers = $row.Observer -split ","
                    #$dateGMT = [datetime]::Parse($row.'Date GMT')
                    #$timeGMT = [datetime]::Parse($row.'Time GMT') 
                    #$dateUTC = [datetime]::Parse($row.'Date GMT')
                    #$timeUTC = [datetime]::Parse($row.'Time GMT') 
                    Log-Message "info" "################ $dateUTC ######################"
                    Log-Message "info" "################ $timeUTC ######################"
                    # Need to convert the local date/time variables into UTC:
                    #$dateUTC = $null
                    #$timeUTC = $null

                    <# Timestamp already in UTC, this is no longer needed:
                    if (-not ([HexFileMetadata]::ConvertLocalDateTimeToUTC($dateGMT, $timeGMT, [ref]$dateUTC, [ref]$timeUTC))) {
                        Log-Message "error" "Failed to convert '$($dateGMT)' and/or '$($timeGMT)' to UTC time."
                    } else {
                        Log-Message "info" "UTC date = $dateUTC, time = $timeUTC"
                    }
                    #>

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
                        "Date GMT" = $dateUTC.ToString("MM/dd/yyyy") # Need to reformat, currently '5/30/2025 20:00'
                        "Time GMT" = $timeUTC.ToString("HH:mm") # Need to reformat, currently '8:24'
                        #"Date GMT" = $dateUTC
                        #"Time GMT" = $timeUTC
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
                    $this._unmatched_recs_count++
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
    [string] GetYearMonthFromFilename($hexFileName) {

        # Get the first .hex file in the folder. If none are found, the variable will be empty. No error is generated.
        #$firstHexFile = Get-ChildItem -Path $this._hex_file_dir -Filter '*.hex' | Sort-Object Name | Select-Object -First 1

        #if (-not $firstHexFile) {
        if (-not $hexFileName) {
            throw "No .hex files found in '$($this._hex_file_dir)'."
        }

        # Extract the first 4 characters
        #$yyMM = $firstHexFile.BaseName.Substring(0, 4)
        $yyMM = $hexFileName.BaseName.Substring(0, 4)

        # Optional: Validate the extracted yyMM format
        if ($yyMM -notmatch '^\d{4}$') {
            #throw "The filename '$($firstHexFile.Name)' does not start with a valid yyMM format."
            throw "The filename '$($hexFileName.Name)' does not start with a valid yyMM format."
        }

        # Output the result
        #Log-Message "info" "Extracted yyMM: $yyMM from file: $($firstHexFile.Name)"
        #$this._yyMM = $yyMM

        # Return the result:
        return $yyMM

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

$metadata = $null

try {
    if ($args.Count -ne 2) {
        #Log-Message "error" "ERROR! Must pass in the .HEX files directory, and the full path and filename of the metadata CSV file."
        $result = -3
        throw "ERROR! Must pass in the .HEX files directory, and the full path and filename of the metadata CSV file."
    }

    Log-Message "info" "args:"
    Log-Message "info" ".HEX files directory: $($args[0])"
    Log-Message "info" "Metadata CSV: $($args[1])"

    $metadata = [HexFileMetadata]::new($args[0], $args[1])
    #$metadata.GetYearMonthFromFilename()
    $metadata.LoadCsvData()
    $metadata.MatchHexFiles()
    Log-Message "info" "Hex files count: $($metadata._merged_data.Count)"
    Log-Message "info" "Matched files: $($metadata._matched_recs_count)"
    Log-Message "info" "Unmatched Files: $($metadata._unmatched_recs_count)"
    $result = 0
} catch {
    Log-Message "error" $_.Exception.Message
    $result = -1
} finally {
    Log-Message "info" "Program completed with code $result (0 indicates success)."
    Log-Message "info" "==========================================================`n"
}

