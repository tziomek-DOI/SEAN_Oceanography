# Read the glba_oc survey metadata.csv file and store the data
$metadata = Import-Csv -Path "C:\Users\tziomek\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\hex_metadata_updater\data\glba_oc_survey_metadata.csv"
Write-Host $metadata

# Read the glba_occ survey station data.csv file and store the data 
$stationData = Import-Csv -Path "C:\Users\tziomek\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\hex_metadata_updater\data\glba_oc_survey_station_data.csv"
Write-Host $stationData

# Create an empty array to store the merged data
$mergedData = @()

function Merge-CsvData {
    param (
        [string]$Csv1Path,
        [string]$Csv2Path,
        [string]$OutputPath = "csv3.csv"
    )

    #$csv1 = Import-Csv -Path $Csv1Path
    #$csv2 = Import-Csv -Path $Csv2Path

    $combined = foreach ($child in $stationData) {
        $parent = $metadata | Where-Object { $_.GlobalID -eq $child.ParentGlobalID }
        if ($parent) {
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

#            "Vessel" = $metadataRecord.Vessel
#            "CTD#" = $metadataRecord."CTD Number"
#            "Dump#" = $metadataRecord.data_dump_number
#            "Observer" = $metadataRecord.Observers
#            "Cast#" = $station."Cast Number"
#            "Station" = $station.Station
#            "Latitude" = $station.Latitude
#            "Longitude" = $station.Longitude
#            "Date GMT" = $station.Date
#            "Time GMT" = $station.Time
#            "Fathometer depth" = $station."Fathometer Depth"
#            "Cast target depth" = $station."Target Depth"
#            "Comments" = $station.Comments
            }
        }
    }

    $combined | Export-Csv -Path $OutputPath -NoTypeInformation
}


# Define a function to find matching records in metadata based on ParentGlobal ID
function Find-MatchingMetadata {
    param ([string]$ParentGlobalID)
    $metadata | Where-Object { $_.ParentGlobalID -eq $ParentGlobalID }
}

# Iterate through each record in the station data
foreach ($station in $stationData) {
    # Find matching records in metadata using the ParentGlobal ID
    $matchingMetadata = Find-MatchingMetadata -ParentGlobalID $station.ParentGlobalID

    # Iterate through each matching metadata record
    foreach ($metadataRecord in $matchingMetadata) {
        # Create a custom object with the combined fields
            $combinedRecord = [PSCustomObject]@{
            "Vessel" = $metadataRecord.Vessel
            "CTD#" = $metadataRecord."CTD Number"
            "Dump#" = $metadataRecord.data_dump_number
            "Observer" = $metadataRecord.Observers
            "Cast#" = $station."Cast Number"
            "Station" = $station.Station
            "Latitude" = $station.Latitude
            "Longitude" = $station.Longitude
            "Date GMT" = $station.Date
            "Time GMT" = $station.Time
            "Fathometer depth" = $station."Fathometer Depth"
            "Cast target depth" = $station."Target Depth"
            "Comments" = $station.Comments
        }

        # Add the combined record to the merged data array
        Write-Host $combinedRecord
        $mergedData += $combinedRecord
    }
}

# Export the merged data to a new CSV file
$mergedData | Export-Csv -Path "C:\Users\tziomek\OneDrive - DOI\dev\projects\SEAN_Oceanography\scripts\hex_metadata_updater\data\glba_oc_merged_survey_data.csv" -NoTypeInformation

# Notify the user that the script has completed
Write-Output "Merged data has been exported to 'glba_oc_merged_survey_data'"
