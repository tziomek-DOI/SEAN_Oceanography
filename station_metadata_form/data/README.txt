station_metadata_form/data:

If the 'default/new' data file (oc_station_metadata_form_records.json) was accidentally written to, there are two ways to fix this,
in the event a 'new' file is desired:

1a. Delete the contents of oc_station_metadata_form_records.json using a text editor (be sure the app is closed before doing this).
1b. Enter the following characters into the file, and save it: []
	(Yes, the file should contain only [])
2. There is a backup of oc_station_metadata_form_records.json in the directory, named oc_station_metadata_form_records.json.empty.
	a. Copy oc_station_metadata_form_records.json.empty into the same data directory.
	b. Rename the copied file to something useful, but definitely remove the '.empty' from the end. Do not use the same default name of oc_station_metadata_form_records.json or you could end up messing with this again.
	ex. oc_station_metadata_form_records_May2026.json would be a useful name.
