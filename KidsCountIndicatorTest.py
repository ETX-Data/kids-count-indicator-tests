# Checks every .xlsx file in the data/ folder for common formatting mistakes
# (bad locations, bad data values/formats, missing columns, etc.) before it
# gets uploaded to the Kids Count Data Center site.
#
# NOTE: passing this script is not a substitute for actually previewing and
# eyeballing the data post-upload - always double check it looks correct before publishing.

# NOTE: always download the site's full current indicator data before uploading
# anything. An upload completely overwrites that indicator's existing data on the
# site (there's no way to edit/patch it afterward), so if the uploaded file turns
# out to have errors, the only fix is re-uploading a corrected file - and without
# a backup of the full data, whatever historical data wasn't in it is gone.

import os
import re
import sys
from datetime import date
import pandas as pd

from locations_dict import locations_dict
from valid_data_formats import valid_data_formats
from reference_data_dict import reference_data_dict
from site_reference_data import fetch_recent_series, ReferenceDataUnavailable

REQUIRED_COLUMNS = ['Location', 'LocationId', 'DataFormat', 'Data', 'TimeFrame']

MIN_VALID_YEAR = 2010 # 2010 is arbitrary - move it earlier if we ever decide to upload more historical data
MAX_VALID_YEAR = date.today().year

# Bexar and Travis are checked (along with Texas) because they're populous enough that their
# year to year numbers stay fairly stable - small counties can swing widely from natural
# randomness alone, which would trigger false positives here.
# can edit to add additional counties / change which counties you're looking at
REFERENCE_CHECK_LOCATIONS = {'Texas', 'Bexar', 'Travis'}
REFERENCE_CHECK_COUNTIES = ['Bexar', 'Travis'] # the non-Texas subset, passed to fetch_recent_series

# how far a value can drift from the site's recent average before it gets flagged - 0.25 is
# arbitrary, loosen/tighten it if it's too noisy or missing real mistakes. Applies the same way
# to 'Number' and 'Percent' values (e.g. a rate moving from ~13% to 29% is a ~123% relative
# swing, well past this threshold) - though note a relative threshold is twitchy on very small
# percentages, where a 1-point move can look like a large relative swing
REFERENCE_DEVIATION_THRESHOLD = 0.25


#### 'TimeFrame' is most commonly a single year (e.g. 2026), but some indicators report a range
#### instead - either a school year (e.g. '2017 - 2018') or a multi-year ACS estimate (e.g.
#### '2018 - 2022'), so any short, forward-moving range within the valid year bounds is accepted.
MAX_VALID_TIMEFRAME_RANGE_SPAN = 5 # covers school-year ranges (span 1) through 5-year ACS estimates (span 4)

def is_valid_timeframe(value):
    if isinstance(value, bool):
        return False

    if isinstance(value, (int, float)):
        return float(value).is_integer() and MIN_VALID_YEAR <= value <= MAX_VALID_YEAR

    if isinstance(value, str):
        text = value.strip()

        if re.fullmatch(r'\d{4}', text):
            return MIN_VALID_YEAR <= int(text) <= MAX_VALID_YEAR

        year_range_match = re.fullmatch(r'(\d{4})\s*-\s*(\d{4})', text)
        if year_range_match:
            start_year, end_year = int(year_range_match.group(1)), int(year_range_match.group(2))
            return (
                1 <= end_year - start_year <= MAX_VALID_TIMEFRAME_RANGE_SPAN
                and MIN_VALID_YEAR <= start_year
                and end_year <= MAX_VALID_YEAR
            )

    return False


#### 'LocationType' isn't a breakdown like RaceEthnicity/Age group - it's derived from
#### Location, and since there's exactly 1 state-level location (Texas) among all the locations
#### in locations_dict, its two categories are legitimately uneven: 'County' should occur once
#### per county for every 1 occurrence of 'State', not the same number of times as 'State'.
STATE_LOCATION_NAMES = {'Texas'}

def validate_location_type_column(raw_values):
    errors = []
    num_counties = len(locations_dict) - len(STATE_LOCATION_NAMES)

    counts_by_category = pd.Series(raw_values).value_counts()

    unexpected_categories = set(counts_by_category.index) - {'County', 'State'}
    if unexpected_categories:
        errors.append(f"Unexpected value(s) in 'LocationType' column: {sorted(unexpected_categories)} (expected only 'County' or 'State')")
        return errors

    county_count = int(counts_by_category.get('County', 0))
    state_count = int(counts_by_category.get('State', 0))

    if state_count == 0 or county_count != num_counties * state_count:
        errors.append(
            f"'LocationType' column has {county_count} 'County' row(s) and {state_count} 'State' row(s) - "
            f"expected 'County' to occur exactly {num_counties} times for every 1 occurrence of 'State' "
            f"(e.g. {num_counties}/1, {num_counties * 2}/2, ...)."
        )

    return errors


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

        if col == 'LocationType':
            errors.extend(validate_location_type_column(raw_values))
            continue

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


#### pull the indicator key out of a cleaned file name: the "<number>_<Name>" prefix (always the
#### first two underscore-separated segments after "CLEANED_"), plus any other segment that isn't
#### a bare 4-digit year - the data year can appear before or after the breakdown segments, or be
#### left out entirely, but every other segment (RaceEthnicity, AsianDisaggregated, etc.) is kept.
#### This matters because files that share a "<number>_<Name>" prefix can still be fundamentally
#### different data (e.g. no breakdown vs. RaceEthnicity vs. RaceEthnicity_AsianDisaggregated for
#### the same indicator number) that needs to be checked against a different page on the site -
#### collapsing them to the same key would compare a file's categories against the wrong page's
#### categories (e.g. an "Other" bucket that means something different on each page). e.g.
#### "CLEANED_3.7_PretermBirths_2023_RaceEthnicity.xlsx" -> "3.7_PretermBirths_RaceEthnicity"
#### "CLEANED_1.2_ChildPopulation_RaceEthnicity_2024_AsianDisaggregated.xlsx" -> "1.2_ChildPopulation_RaceEthnicity_AsianDisaggregated"
#### "CLEANED_1.2_ChildPopulation_2024.xlsx" -> "1.2_ChildPopulation"
#### this key is what's looked up in reference_data_dict.py - returns None if the file name
#### doesn't even have a "<number>_<Name>" prefix (the reference-data check is just skipped then)
def get_indicator_key(file_path):
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    # strip a Windows re-download suffix like " (1)" before splitting into segments
    file_name = re.sub(r'\s+\(\d+\)$', '', file_name)

    segments = file_name.split('_')
    if segments and segments[0].upper() == 'CLEANED':
        segments = segments[1:]

    if len(segments) < 2 or not re.fullmatch(r'\d+(\.\d+)?', segments[0]):
        return None

    key_segments = [
        segment for i, segment in enumerate(segments)
        if i < 2 or not re.fullmatch(r'\d{4}', segment)
    ]

    return '_'.join(key_segments)


#### the one breakdown column in a file, if any (e.g. 'RaceEthnicity', 'Age group') - everything
#### that isn't a required column or 'LocationType' (which is location metadata, not a breakdown)
#### returns None if there's no such column, so callers treat every row as having no category
def get_breakdown_column(df):
    breakdown_columns = [col for col in df.columns if col not in REQUIRED_COLUMNS and col != 'LocationType']
    return breakdown_columns[0] if len(breakdown_columns) == 1 else None


#### format a Data value for display the same way the file/site would show it
def format_data_value(value, data_format):
    return f"{value:.1%}" if data_format == 'Percent' else f"{value:,.4g}"


#### data check: compare each of this file's Texas/Bexar/Travis data points against the last
#### several periods of the *exact same* location + category + data format pulled live from the
#### indicator's site page (see reference_data_dict.py)
#### This can't catch every mistake, but a value that's way off from recent history is often a
#### units/location/denominator mistake worth double-checking before uploading.
#### does nothing if the indicator isn't in reference_data_dict.py yet, or if the live site can't
#### be reached/parsed (this shouldn't block validation just because a website hiccuped)
def validate_against_reference_data(df, indicator_key):
    warnings = []

    page_url = reference_data_dict.get(indicator_key)
    if page_url is None:
        return warnings

    try:
        series_by_key = fetch_recent_series(page_url, REFERENCE_CHECK_COUNTIES)
    except ReferenceDataUnavailable as e:
        warnings.append(f"Could not run the site trend check for '{indicator_key}' ({e}) - skipping it.")
        return warnings

    breakdown_column = get_breakdown_column(df)

    for index, row in df.iterrows():
        if row['Location'] not in REFERENCE_CHECK_LOCATIONS or not isinstance(row['Data'], (int, float)):
            continue

        category = row[breakdown_column] if breakdown_column else None
        normalized_category = category.strip().casefold() if isinstance(category, str) else None

        reference_periods = series_by_key.get((row['Location'], normalized_category, row['DataFormat']))
        if not reference_periods:
            continue

        reference_average = sum(reference_periods.values()) / len(reference_periods)
        if reference_average == 0:
            continue

        percent_diff = abs(row['Data'] - reference_average) / reference_average
        if percent_diff > REFERENCE_DEVIATION_THRESHOLD:
            direction = "higher" if row['Data'] > reference_average else "lower"
            category_note = f" ({category})" if category else ""
            formatted_periods = {
                period: format_data_value(value, row['DataFormat']) for period, value in reference_periods.items()
            }
            warnings.append(
                f"POSSIBLE DATA ISSUE: '{row['Location']}'{category_note} {row['DataFormat']} value for "
                f"{row['TimeFrame']} (row {index + 2}) is {format_data_value(row['Data'], row['DataFormat'])}, "
                f"which is {percent_diff:.0%} {direction} than the {len(reference_periods)}-period average on "
                f"the site ({format_data_value(reference_average, row['DataFormat'])}). Recent periods on site: "
                f"{formatted_periods}. Double check this isn't a units/location/denominator mistake before uploading."
            )

    return warnings


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

        # can't run column/row-level checks below if a required column is missing
        if errors:
            return errors

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

            # a blank cell shows up as an empty string, but a cell holding an unresolved Excel
            # formula error (e.g. '#DIV/0!') reads as NaN instead (both count as blank here)
            is_blank = (isinstance(row['Data'], str) and row['Data'].strip() == '') or pd.isna(row['Data'])

            # test: 'Data' is not left blank
            if is_blank:
                errors.append(
                    f"Blank/missing value in 'Data' column in row {index + 2} - use 'NA' or 'LNE' instead of "
                    f"leaving it empty. (If this cell isn't actually empty, it may contain an unresolved Excel "
                    f"formula error like '#DIV/0!' - open the file and check.)"
                )
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

            # test: 'TimeFrame' is a plausible year (e.g. 2026) or school year range (e.g. '2017 - 2018')
            if not is_valid_timeframe(row['TimeFrame']):
                errors.append(f"Invalid value '{row['TimeFrame']}' in 'TimeFrame' column in row {index + 2}")

        # test: Texas/Bexar/Travis values aren't way off from the last several periods on the live site
        indicator_key = get_indicator_key(file_path)
        if indicator_key is not None:
            errors.extend(validate_against_reference_data(df, indicator_key))

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

    all_files = [f for f in sorted(os.listdir(folder_path)) if not f.startswith('~$')]

    excel_files = [
        os.path.join(folder_path, f)
        for f in all_files
        if f.lower().endswith('.xlsx')
    ]

    skipped_files = [f for f in all_files if not f.lower().endswith('.xlsx')]
    if skipped_files:
        print(
            f"WARNING: found {len(skipped_files)} file(s) in {folder_path} that are NOT .xlsx and will NOT "
            f"be checked by this script: {skipped_files}"
        )
        print("")

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