# Installation Instructions:
To get this cloned down and to use it locally, just follow these instructions

1. Clone the repo down locally. Open up a terminal, change directory to wherever you would like the repo folder downloaded to, then use the following command:

```
git clone https://github.com/Tom-Shaffer/KidsCountIndicatorTest.git
```

2. Then you need to go into the folder and run pip install to get all the necessary packages

```
cd KidsCountIndicatorTest/
pip install -r requirements.txt
```

# How to use it:

Method 1: Pass the file path right away
```
python3 KidsCountIndicatorTest.py Path/To/The/Excel
```

Method 2: Pass in file path later
```
python3 KidsCountIndicatorTest.py 
```

# Expected results

This program should tell you if there are any errors detected, an example output might be:

* Example of a "perfect" upload:
```
No errors found in the Excel file, congratulations!
```

* Example of a finding errors:

```
python3 KidsCountIndicatorTest.py "/Users/tomshaffer/Downloads/1.1_TotalPopulation_RaceEthnicity_21_22 1.xlsx"
Invalid value '--' in 'Data' column in row 6
Mismatched LocationId for 'Texas' (Expected: 45, Found: 555) in row 15
Invalid data format 'Porcent' in row 17
Unknown location 'Banderson' in row 24.
Invalid data format 'Kaitlan' in row 26
Non-decimal percentage value 1.37 in 'Data' column for percentage format in row 73.
Unknown location 'De Witt' in row 508.
Unknown location 'Dewitt' in row 512.
Unknown location 'mcculloch' in row 1246.
Unknown location 'Mcculloch' in row 1247.
Unknown location 'Mcmullen' in row 1258.
Unknown location 'marion' in row 1274.
```