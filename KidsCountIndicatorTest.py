import os
import re
import sys
from datetime import date
import pandas as pd

from locations_dict import locations_dict
from valid_data_formats import valid_data_formats

REQUIRED_COLUMNS = ['Location', 'LocationId', 'DataFormat', 'Data', 'TimeFrame']

MIN_VALID_YEAR = 2010 # 2010 is arbitrary - move it earlier if we ever decide to upload more historical data
MAX_VALID_YEAR = date.today().year


#### 'TimeFrame' is most commonly a single year (e.g. 2026), but some education
#### indicators report a school year range instead (e.g. '2017 - 2018').
def is_valid_timeframe(value):
    if isinstance(value, bool):
        return False

    if isinstance(value, (int, float)):
        return float(value).is_integer() and MIN_VALID_YEAR <= value <= MAX_VALID_YEAR

    if isinstance(value, str):
        text = value.strip()

        if re.fullmatch(r'\d{4}', text):
            return MIN_VALID_YEAR <= int(text) <= MAX_VALID_YEAR

        school_year_match = re.fullmatch(r'(\d{4})\s*-\s*(\d{4})', text)
        if school_year_match:
            start_year, end_year = int(school_year_match.group(1)), int(school_year_match.group(2))
            return end_year == start_year + 1 and MIN_VALID_YEAR <= start_year <= MAX_VALID_YEAR

    return False


#### some indicators include an extra breakdown column (e.g. RaceEthnicity, Sex, AgeGroup) that other indicators don't have
#### these columns aren't required, but when present, each category should be spelled/formatted consistently
#### and should appear the same number of times as every other category (a multiple of the number of locations,
#### since every location should get one row per category per time period)
def validate_optional_categorical_columns(df):
    errors = []
    num_locations = len(locations_dict)

    optional_columns = [col for col in df.columns if col not in REQUIRED_COLUMNS]

    for col in optional_columns:
        raw_values = [str(v) for v in df[col]]

        # skip columns that are entirely blank - they just don't apply to this indicator
        if all(v.strip() == '' for v in raw_values):
            continue

        # test: no case/whitespace variants of what should be the same category
        # (e.g. 'Asian' and 'asian ' both present)
        variants_by_normalized_value = {}
        for value in raw_values:
            normalized_value = value.strip().casefold()
            variants_by_normalized_value.setdefault(normalized_value, set()).add(value)

        for normalized_value, variants in variants_by_normalized_value.items():
            if len(variants) > 1:
                errors.append(
                    f"Inconsistent formatting in '{col}' column: {sorted(variants)} appear to be the same "
                    f"category but are spelled/formatted differently."
                )

        # test: every category occurs the same number of times, and that count is a
        # multiple of the number of locations ({num_locations}, {num_locations*2}, ...)
        counts_by_category = pd.Series(raw_values).value_counts()
        distinct_counts = set(counts_by_category.values)

        if len(distinct_counts) > 1:
            counts_summary = ", ".join(f"'{category}': {count}" for category, count in counts_by_category.items())
            errors.append(
                f"Inconsistent number of occurrences per category in '{col}' column "
                f"(every category should occur the same number of times): {counts_summary}"
            )
        else:
            common_count = next(iter(distinct_counts))
            if common_count % num_locations != 0:
                errors.append(
                    f"Each category in '{col}' column occurs {common_count} time(s), which is not a multiple "
                    f"of {num_locations} (the number of locations) - expected {num_locations}, "
                    f"{num_locations * 2}, {num_locations * 3}, etc."
                )

    return errors


#### validate the data inside an excel file against the required rules
def validate_excel_data(file_path):
    errors = []

    try:
        # keep "NA" as literal text instead of pandas turning it into a blank cell
        df = pd.read_excel(file_path, keep_default_na=False, na_values=[])

        # test: all required columns are present
        for col in REQUIRED_COLUMNS:
            if(col not in df.columns):
                errors.append(f"Missing column header {col}")

        errors.extend(validate_optional_categorical_columns(df))

       # iterate over DataFrame row by row
        for index, row in df.iterrows():
            # test: location is known
            if row['Location'] not in locations_dict:
                errors.append(f"Unknown location '{row['Location']}' in row {index + 2}.")
            else:
                # test: LocationId matches the expected id for this location
                expected_location_id = locations_dict[row['Location']]
                if row['LocationId'] != expected_location_id:
                    errors.append(f"Mismatched LocationId for '{row['Location']}' (Expected: {expected_location_id}, Found: {row['LocationId']}) in row {index + 2}")

            # check for valid values in 'Data' column
            valid_types = (float, int)
            valid_values = ['NA', 'LNE']

            is_blank = isinstance(row['Data'], str) and row['Data'].strip() == ''

            # test: 'Data' is not left blank
            if is_blank:
                errors.append(f"Blank/missing value in 'Data' column in row {index + 2} - use 'NA' or 'LNE' instead of leaving it empty.")
            else:
                # test: percentage values are between 0.00 and 1.00
                if row['DataFormat'] == 'Percent' and row['Data'] not in valid_values:
                    try:
                        if not (0.00 <= float(row['Data']) <= 1.00):
                            errors.append(f"Value in 'Data' column for percentage format is not between 0.00 and 1.00 in row {index + 2}")
                    except ValueError:
                        errors.append(f"Non-numeric value or allowed  '{row['Data']}' in 'Data' column for percentage format in row {index + 2}")

                # test: 'Data' is a number, or an allowed placeholder ('NA'/'LNE')
                if not (isinstance(row['Data'], valid_types) or row['Data'] in valid_values):
                    errors.append(f"Invalid value '{row['Data']}' in 'Data' column in row {index + 2}")

            # test: 'DataFormat' is one of the allowed formats
            if row['DataFormat'] not in valid_data_formats:
                errors.append(f"Invalid data format '{row['DataFormat']}' in row {index + 2}")

            # test: 'TimeFrame' is a plausible year (e.g. 2026) or school-year range (e.g. '2017 - 2018')
            if not is_valid_timeframe(row['TimeFrame']):
                errors.append(f"Invalid value '{row['TimeFrame']}' in 'TimeFrame' column in row {index + 2}")

    except Exception as e:
        errors.append(f"Error processing Excel file in \"{file_path}\": {e}")

    return errors

#### check that a file exists, is an .xlsx file, and can actually be opened
def is_valid_excel_file(file_path) -> bool:
    # test: file exists
    if not os.path.exists(file_path):
        print(f"The file path {file_path} does not exist.")
        return False

    # test: file has an .xlsx extension
    _, file_extension = os.path.splitext(file_path)
    if file_extension.lower() != '.xlsx':
        print(f"The file {file_path} is not an Excel file (.xlsx).")
        return False

    # test: file can actually be opened as Excel
    try:
        pd.read_excel(file_path, keep_default_na=False, na_values=[])
        return True
    except Exception as e:
        print(f"Error reading Excel file in \"{file_path}\": {e}")
        return False

#### find all .xlsx files in a given folder
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

#### main: run validation on every excel file in the data folder and print results
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