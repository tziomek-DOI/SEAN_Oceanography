using System;
using System.IO;
using System.Collections.Generic;
using System.Text;

namespace CNV_converter_for_ODV
{
    public class Converter
    {
        private decimal _latitude;
        private decimal _longitude;
        private string _input_directory;
        private string _output_directory;
        private string[] _cnv_files;

        public Converter(string input_directory, string output_directory) 
        {
            if (!Directory.Exists(input_directory))
            {
                throw new DirectoryNotFoundException($"Directory '{input_directory}' not found.");
            }

            if (!Directory.Exists(output_directory))
            {
                throw new DirectoryNotFoundException($"Directory '{output_directory}' not found.");
            }

            _input_directory = input_directory;
            _output_directory = output_directory;
        }

        public Converter(decimal latitude, decimal longitude)
        {
            _latitude = latitude;
            _longitude = longitude;
        }

        public decimal Latitude
        {
            get
            {
                return _latitude;
            }

            set
            {
                if (value < -90.0M || value > 90.0M)
                {
                    throw new ArgumentOutOfRangeException("Latitude must be between -90.0 and 90.0.");
                }

                _latitude = value;
            }
        }

        public decimal Longitude
        {
            get
            {
                return _longitude;
            }

            set
            {
                if (value < -180.0M || value > 180.0M)
                {
                    throw new ArgumentOutOfRangeException("Longitude must be between -180.0 and 180.0.");
                }

                _longitude = value;
            }
        }

        public string FormatWGS84()
        {
            return $"{this.Latitude}, {this.Longitude}";
        }

        public string FormatLatitudeDegrees(decimal latitude)
        {
            string direction = latitude > 0 ? "N" : "S";
            latitude = Math.Abs(latitude);

            //string dd = decimal.Truncate(latitude).ToString("0#");
            //string mm = (decimal.Subtract(latitude, decimal.Truncate(latitude)) * 60).ToString("0#.0000");

            //return $"{dd}.{mm}{direction}";

            return $"{latitude}{direction}";
        }

        public string FormatLongitudeDegrees(decimal longitude)
        {
            string direction = longitude > 0 ? "E" : "W";
            longitude = Math.Abs(longitude);

            //string dd = decimal.Truncate(longitude).ToString("00#");
            //string mm = (decimal.Subtract(longitude, decimal.Truncate(longitude)) * 60).ToString("0#.0000");

            //return $"{dd}.{mm}{direction}";

            return $"{longitude}{direction}";
        }

        private string ReplaceBadFlag()
        {
            return "-999";
        }

        public int GetCNVFileCount()
        {
            return _cnv_files.Length;
        }

        /// <summary>
        /// 
        /// </summary>
        /// <returns>The number of CNV files that were updated.</returns>
        public int UpdateCNVFiles()
        {
            int numFilesUpdated = 0;

            // Get list of CNV files 
            GetCNVFiles(_input_directory);

            // Iterate the CNV files
            if (_cnv_files.Length == 0)
                throw new FileNotFoundException($"No CNV files found in directory '{_input_directory}'.");

            foreach (var cnv_file in _cnv_files)
            {
                string output_file = _output_directory + @"\" + Path.GetFileName(cnv_file);
                numFilesUpdated += UpdateCNV(cnv_file, output_file);
            }

            return numFilesUpdated;
        }

        private void GetCNVFiles(string directory)
        {
            if (!Directory.Exists(directory))
                throw new DirectoryNotFoundException(directory);

            _cnv_files = Directory.GetFiles(directory);
        }

        /// <summary>
        /// 
        /// </summary>
        /// <param name="input_filename">Source .CNV file.</param>
        /// <param name="output_filename">The edited, "ODV-friendly" .CNV file.</param>
        /// <returns>Number of files updated (0 or 1)</returns>
        private int UpdateCNV(string input_filename, string output_filename)
        {
            int retval = 0;

            try
            {
                // open the file
                // Read the lat (and reformat)
                // Read the long (and reformat)
                // Read the bad_flag (and set to -999)
                // Write the changed values back to file
                // close the file
                using (var input = File.OpenText(input_filename))
                {
                    using (var output = new StreamWriter(output_filename))
                    {
                        string line;
                        while (null != (line = input.ReadLine()))
                        {
                            // optionally modify line.
                            if (line.StartsWith("** Latitude"))
                            {
                                // We want to rename the initial value to "** Latitude_orig"
                                // and add a new line with the edited version.
                                var parts = line.Split(':');
                                string new_label = parts[0].Replace("Latitude", "Latitude_orig");
                                string new_lat = FormatLatitudeDegrees(Convert.ToDecimal(parts[1]));
                                StringBuilder sb = new StringBuilder(new_label + ":" + parts[1]);
                                sb.AppendLine();
                                sb.Append(parts[0] + ":" + new_lat);
                                line = sb.ToString();
                            }
                            else if (line.StartsWith("** Longitude"))
                            {
                                // We want to rename the initial value to "** Latitude_orig"
                                // and add a new line with the edited version.
                                var parts = line.Split(':');
                                string new_label = parts[0].Replace("Longitude", "Longitude_orig");
                                string new_long = FormatLongitudeDegrees(Convert.ToDecimal(parts[1]));
                                StringBuilder sb = new StringBuilder(new_label + ":" + parts[1]);
                                sb.AppendLine();
                                sb.Append(parts[0] + ":" + new_long);
                                line = sb.ToString();
                            }
                            // original format is # bad_flag = -999 (note the spacing around the = sign)
                            // Need to preserve the bad_flag value? Unclear if it is consistently set the same, but assuming so,
                            // may not be necessary to preserve. The default set by SBE is -9.990e-29. It will need to be replaced
                            // everywhere in the file.
                            //else if (line.StartsWith("# bad_flag"))
                            //{
                            //    var parts = line.Split('=');
                            //    StringBuilder sb = new StringBuilder(line);
                            //    sb.AppendLine(parts[0] + " = " + ReplaceBadFlag());
                            //}
                            else if (line.Contains("-9.990e-29"))
                            {
                                line = line.Replace("-9.990e-29", "-999");
                            }
                            output.WriteLine(line);
                        }
                    }
                }

                retval = 1;
            }
            catch (Exception ex)
            {
                // what to do here?
                throw new Exception($"ERROR processing file {input_filename}: {ex.Message}");
            }
            finally
            {
                // Close the file if an exception occurred
            }

            return retval;
        }
    }
}
