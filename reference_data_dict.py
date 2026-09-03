#### Maps each indicator to its page on the live KIDS COUNT Data Center site
#### (https://datacenter.aecf.org). Used by site_reference_data.py as a data check before
#### uploading new data: it fetches the last 5 periods straight from the site - for every
#### location/category/data-format combination the file has, Number and Percent both - and
#### flags any value that's way off from its own history (a common sign of a units/location/
#### denominator mistake) so it's worth double checking before uploading.
####
#### HOW TO FILL THIS OUT for a new indicator:
#### 1. Get the indicator's key: it's the "<number>_<Name>" part of the cleaned file name, e.g.
####    "CLEANED_3.7_PretermBirths_2023_RaceEthnicity.xlsx" -> key is "3.7_PretermBirths".
#### 2. Go to the indicator's page on datacenter.aecf.org for Texas (statewide) - any view/years
####    selected is fine, the URL just needs to point at the right indicator page.
#### 3. Add an entry below: indicator key -> that page's URL.

reference_data_dict = {
    "1.2_ChildPopulation": "https://datacenter.aecf.org/data/tables/11124-child-pop-by-race-and-ethnicity-asian-disaggregated?loc=45&loct=2",
    "1.3_ChildPopulation": "https://datacenter.aecf.org/data/tables/6422-child-population-by-age-group?loc=45&loct=2",

    "1.4_ChildInFamilies": "https://datacenter.aecf.org/data/tables/3059-children-in-single-parent-families?loc=45&loct=2",

    "3.6_PretermBirths": "https://datacenter.aecf.org/data/tables/6016-preterm-births?loc=45&loct=2",
    "3.7_PretermBirths": "https://datacenter.aecf.org/data/tables/8981-preterm-births-by-race-ethnicity?loc=45&loct=2",
}
