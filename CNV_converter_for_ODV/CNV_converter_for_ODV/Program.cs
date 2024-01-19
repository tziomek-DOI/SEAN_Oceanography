using System;

namespace CNV_converter_for_ODV
{
    class Program
    {
        static int Main(string[] args)
        {
            int retval = -999;

            if (args.Length != 2)
            {
                Console.WriteLine("You must pass the cnv source directory and the cnv output (edited files) directory to the program.");
                Console.WriteLine("Usage:");
                Console.WriteLine("CNV_converter_for_ODV.exe <source_dir> <output_dir>");
                return 1;
            }
            // first arg should be the directory containing the .CNV files
            string cnv_dir = args[0];
            if (!cnv_dir.EndsWith(@"\"))
                cnv_dir += @"\";

            // second arg should be the directory where to place the edited .CNV files
            string output_dir = args[1];
            if (!output_dir.EndsWith(@"\"))
                output_dir += @"\";

            try
            {
                Converter converter = new Converter(cnv_dir, output_dir);
                converter.UpdateCNVFiles();
                int numSourceCNVFiles = converter.GetCNVFileCount();
                Console.WriteLine($"{numSourceCNVFiles} file(s) found in the source directory.");

                int numOutputFiles = converter.UpdateCNVFiles();
                Console.WriteLine($"{numOutputFiles} file(s) created in the output directory");

                if (numSourceCNVFiles == numOutputFiles)
                    retval = 0;
                else
                {
                    Console.WriteLine("The number of source and output files does not match. Something went wrong!");
                    retval = 2;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"ERROR: {ex.Message}");
                retval = 3;
            }
            finally
            {
                Console.WriteLine("Press any key to exit...");
                Console.ReadKey();
            }

            //string latitude = "59.08604";
            //string longitude = "-136.37216";
            //string latitude_odv = converter.FormatLatitudeDegrees(Convert.ToDecimal(latitude));
            //string longitude_odv = converter.FormatLongitudeDegrees(Convert.ToDecimal(longitude));


            //Console.WriteLine($"Converted '{latitude}' toDegreeDecimalMinutes: '{latitude_odv}'");
            //Console.WriteLine($"Converted '{longitude}' toDegreeDecimalMinutes: '{longitude_odv}'");

            //Console.WriteLine("Press any key to exit...");
            //Console.ReadKey();

            return retval;
        }
    }
}
