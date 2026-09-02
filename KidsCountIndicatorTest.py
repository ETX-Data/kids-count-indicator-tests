import os
import sys
import pandas as pd

from locations_dict import locations_dict
from valid_data_formats import valid_data_formats


def validate_excel_data(file_path):
    errors = []

    try:
        df = pd.read_excel(file_path)

        required_column = ['Location', 'LocationId', 'DataFormat', 'Data']

        for col in required_column:
            if(col not in df.columns):
                errors.append(f"Missing column header {col}")

       # Iterate over the DataFrame row by row
        for index, row in df.iterrows():
            # Check if location is known
            if row['Location'] not in locations_dict:
                errors.append(f"Unknown location '{row['Location']}' in row {index + 2}.")
            else:
                # Check if LocationId matches with the dictionary
                expected_location_id = locations_dict[row['Location']]
                if row['LocationId'] != expected_location_id:
                    errors.append(f"Mismatched LocationId for '{row['Location']}' (Expected: {expected_location_id}, Found: {row['LocationId']}) in row {index + 2}")

            # Check for valid values in 'Data' column
            valid_types = (float, int)
            valid_values = ['NA', 'LNE']

            # Check for percentage data format
            if row['DataFormat'] == 'Percent':
                try:
                    if not row['Data'] in valid_values:
                        if not (0.00 <= float(row['Data']) <= 1.00):
                            errors.append(f"Value in 'Data' column for percentage format is not between 0.00 and 1.00 in row {index + 1}")
                except ValueError:
                    errors.append(f"Non-numeric value or allowed  '{row['Data']}' in 'Data' column for percentage format in row {index + 1}")

            

            if row['DataFormat'] not in valid_data_formats:
                errors.append(f"Invalid data format '{row['DataFormat']}' in row {index + 2}")

            if not (isinstance(row['Data'], valid_types) or row['Data'] in valid_values):
                errors.append(f"Invalid value '{row['Data']}' in 'Data' column in row {index + 2}")

    except Exception as e:
        errors.append(f"Error processing Excel file in \"{file_path}\": {e}")

    return errors

def is_valid_excel_file(file_path) -> bool:
    if not os.path.exists(file_path):
        print(f"The file path {file_path} does not exist.")
        return False

    _, file_extension = os.path.splitext(file_path)
    if file_extension.lower() != '.xlsx':
        print(f"The file {file_path} is not an Excel file (.xlsx).")
        return False

    try:
        pd.read_excel(file_path)
        return True
    except Exception as e:
        print(f"Error reading Excel file in \"{file_path}\": {e}")
        return False

def get_data_files_in_folder(folder_path) -> list:
    if not os.path.isdir(folder_path):
        print(f"The folder {folder_path} does not exist.")
        print("Press the enter key to exit")
        input()
        exit()

    excel_files = [
        os.path.join(folder_path, f)
        for f in sorted(os.listdir(folder_path))
        if f.lower().endswith('.xlsx') and not f.startswith('~$')
    ]

    if not excel_files:
        print(f"No .xlsx files found in {folder_path}.")
        print("Press the enter key to exit")
        input()
        exit()

    return excel_files

script_dir = os.path.dirname(os.path.abspath(__file__))
data_folder = os.path.join(script_dir, 'data')

data_files = get_data_files_in_folder(data_folder)

any_errors = False
for kidsCountIndicatorExcelFile in data_files:
    print(f"Checking \"{kidsCountIndicatorExcelFile}\"...")

    if not is_valid_excel_file(kidsCountIndicatorExcelFile):
        any_errors = True
        print("")
        continue

    validation_errors = validate_excel_data(kidsCountIndicatorExcelFile)
    if validation_errors:
        any_errors = True
        for error in validation_errors:
            print(error)
        print("")
        print(f"Please resolve the errors above in \"{kidsCountIndicatorExcelFile}\".")
    else:
        print(f"No errors found in \"{kidsCountIndicatorExcelFile}\", congratulations!")
    print("")

if not any_errors:
    print("All files passed validation.")

print("Press the enter key to exit")
input()