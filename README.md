# Installation Instructions:
To get this cloned down and to use it locally, just follow these instructions

1. Clone the repo down locally. Open up a terminal, change directory to wherever you would like the repo folder downloaded to, then use the following command:

```
git clone https://github.com/kaitlan-wong/kids-count-indicator-tests
```

2. Then you need to go into the folder and run pip install to get all the necessary packages

```
cd KidsCountIndicatorTest/
pip install -r requirements.txt
```

# How to use it:

Put the `.xlsx` file(s) you want to check into the `data/` folder, then run the script:

```
python3 KidsCountIndicatorTest.py
```

It will validate every `.xlsx` file it finds in `data/` and print the results for each one.

# What it checks

For every file:
- Required columns are present: `Location`, `LocationId`, `DataFormat`, `Data`, `TimeFrame`
- `Location` is a known Texas county (or "Texas")
- `LocationId` matches the expected id for that `Location`
- `Data` is not left blank (use `NA` or `LNE` instead) - this also catches a cell holding an unresolved Excel formula error like `#DIV/0!`, which reads as blank
- `Data` is a number, or an allowed placeholder (`NA`/`LNE`)
- If `DataFormat` is `Percent`, `Data` is between 0.00 and 1.00
- `DataFormat` is one of the allowed formats (`Rate Per 100,000`, `Number`, `Percent`)
- `TimeFrame` is a plausible year, or a short year range - either a school year (e.g. `2017 - 2018`) or a multi-year ACS estimate (e.g. `2018 - 2022`)
- If an optional breakdown column is present (e.g. `RaceEthnicity`), its categories are spelled/formatted consistently and each one occurs the same number of times
- If a `LocationType` column is present, it's spelled/formatted consistently and `County` occurs exactly once per county for every 1 occurrence of `State` (not the same count as `State` - there's only 1 state-level location, Texas, so this is naturally uneven)
- If the indicator has a URL in `reference_data_dict.py`, every Texas/Bexar/Travis data point (`Number` and `Percent` both, and each breakdown category separately) is compared live against the last 5 periods of that *exact same* series pulled straight from the indicator's site page, and flagged if it's way off (a common sign of a units/location/denominator mistake - including a `Percent` that's wrong even when the `Number` next to it is right). See the comments in `reference_data_dict.py` for how to add an indicator to it - it only takes a URL, no numbers to type in.

# Expected results

* Example of a "perfect" upload:
```
No errors found in "data/1.1_TotalPopulation_RaceEthnicity_21_22.xlsx", congratulations!
```

* Example of finding errors:

```
Checking "data/1.1_TotalPopulation_RaceEthnicity_21_22.xlsx"...
Invalid value '--' in 'Data' column in row 6
Mismatched LocationId for 'Texas' (Expected: 45, Found: 555) in row 15
Invalid data format 'Porcent' in row 17
Unknown location 'Banderson' in row 24.
Value in 'Data' column for percentage format is not between 0.00 and 1.00 in row 73
Unknown location 'De Witt' in row 508.
Unknown location 'Dewitt' in row 512.
Unknown location 'mcculloch' in row 1246.
Unknown location 'Mcculloch' in row 1247.
Unknown location 'Mcmullen' in row 1258.
Unknown location 'marion' in row 1274.

Please resolve the errors above in "data/1.1_TotalPopulation_RaceEthnicity_21_22.xlsx".
```
