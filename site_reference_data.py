#### Fetches recent-year totals straight from an indicator's live page on the KIDS COUNT Data
#### Center (https://datacenter.aecf.org), so KidsCountIndicatorTest.py can compare a file's
#### numbers against what's already published before it gets uploaded.
####
#### HOW THIS WORKS: the indicator page's HTML has hidden form inputs listing every year/
#### category/data-format option and the internal numeric id the site uses for each one (e.g.
#### year "2023" is id "2545"). The page's own table of data is then loaded separately by the
#### browser via a JSON API (GET /api/reports/detailedtable) using those ids, which returns a
#### small HTML table fragment. This scrapes both steps: load the page to learn the ids, then
#### call the same API the site's own JavaScript calls to get the actual numbers. There's no
#### official public API for this - if AECF changes their site's HTML, this will need updating.

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from locations_dict import locations_dict

# pretending to be a browser avoids a bot-detection block that Python's default User-Agent hits
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

REQUEST_TIMEOUT_SECONDS = 20

TEXAS_LOCATION_ID = str(locations_dict['Texas'])


class ReferenceDataUnavailable(Exception):
    """Raised when the live site's data can't be fetched or parsed - callers should treat this
    as 'skip the check', not as a hard failure, since it's an external site outside our control."""


def _get(url, extra_headers=None):
    headers = dict(REQUEST_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, TimeoutError) as e:
        raise ReferenceDataUnavailable(f"Could not reach {url}: {e}") from e


#### scrape the page's hidden form inputs to learn the indicator's internal ids:
#### which numeric id means which year, which breakdown category, and which data format
def _get_indicator_page_config(page_url):
    html = _get(page_url)

    indicator_match = re.search(r'name="ind"\s+value="(\d+)"', html)
    if not indicator_match:
        raise ReferenceDataUnavailable(f"Couldn't find the indicator id on {page_url} - the site's page layout may have changed.")

    # most indicators label each option with a single year (e.g. "2023"), but some report
    # multi-year ACS ranges instead (e.g. "2018 - 2022") - the attributes can also be split
    # across lines, so this tolerates whitespace between them rather than requiring one line
    year_label_by_timeframe_id = {
        match.group(1): match.group(2).strip()
        for match in re.finditer(
            r'class="tf-checkbox"\s+type="checkbox"\s+name="tf"\s+value="(\d+)"\s+id="\d+"\s+data-title="([^"]+)"',
            html,
        )
    }
    if not year_label_by_timeframe_id:
        raise ReferenceDataUnavailable(f"Couldn't find any year options on {page_url} - the site's page layout may have changed.")

    # only present for indicators with a breakdown column (RaceEthnicity, Sex, etc.) - a plain
    # indicator with no breakdown will have no matches here, which is fine
    category_ids = [match.group(1) for match in re.finditer(r'data-name="ch" name="dist" id="ch-chk-(\d+)"', html)]

    format_id_by_label = {
        match.group(2): match.group(1)
        for match in re.finditer(r'name="fmt" class="form_toggle_input radchk" value="(\d+)" data-title="([^"]+)"', html)
    }

    return {
        'indicator_id': indicator_match.group(1),
        'year_label_by_timeframe_id': year_label_by_timeframe_id,
        'category_ids': category_ids,
        'format_id_by_label': format_id_by_label,
    }


#### sort key for a year label ("2023" or "2018 - 2022") - the label's latest 4-digit year,
#### so range-based labels sort by how recent their most recent year is
def _year_label_sort_key(label):
    years_in_label = re.findall(r'\d{4}', label)
    return int(years_in_label[-1]) if years_in_label else -1


#### call the same JSON API the site's own table view uses, and return its raw HTML table fragment
def _fetch_data_table_html(page_url, indicator_id, location_ids, location_type, timeframe_ids, format_id, category_ids):
    params = {
        'ind': indicator_id,
        'loc': ','.join(location_ids),
        'loct': location_type,
        'tf': ','.join(timeframe_ids),
        'fmt': format_id,
        # the site always sends a comparison location even when not displaying one - omitting
        # cmploc/inccmploc entirely makes the API return an error
        'cmploc': TEXAS_LOCATION_ID,
        'inccmploc': 'false',
    }
    if category_ids:
        params['ch'] = ','.join(category_ids)

    url = 'https://datacenter.aecf.org/api/reports/detailedtable?' + urllib.parse.urlencode(params)
    body = _get(url, extra_headers={'Accept': 'application/json, text/plain, */*', 'Referer': page_url})

    try:
        return json.loads(body)['html']
    except (json.JSONDecodeError, KeyError) as e:
        raise ReferenceDataUnavailable(f"Unexpected response from {url}: {e}") from e


#### add up each location's 'Number' value per year (or year-range, e.g. "2018 - 2022") across
#### every row (i.e. across every breakdown category, if there is one) - the site doesn't
#### publish a combined total, so this sum is what represents each location's overall total
def _sum_totals_by_location_and_year(table_html, year_label_by_timeframe_id, number_format_id, location_name_by_id):
    totals_by_location = {}

    row_pattern = re.compile(
        r'<tr class="[^"]*" data-locId="(\d+)"(?:\s+data-chId="\d+")?\s+data-fmtId="(\d+)">(.*?)</tr>',
        re.DOTALL,
    )
    cell_pattern = re.compile(r'class="data_value[^"]*\btf-(\d+)\b[^"]*"><div[^>]*>([^<]*)</div>')

    for location_id, format_id, row_html in row_pattern.findall(table_html):
        if format_id != number_format_id:
            continue

        location_name = location_name_by_id.get(location_id)
        if location_name is None:
            continue

        for timeframe_id, raw_value in cell_pattern.findall(row_html):
            year_label = year_label_by_timeframe_id.get(timeframe_id)
            if year_label is None:
                continue

            # skip non-numeric placeholders like 'LNE'/'NA' - the total is then a slight
            # undercount when those appear, which is fine for a rough sanity check
            try:
                value = float(raw_value.strip().replace(',', ''))
            except ValueError:
                continue

            year_totals = totals_by_location.setdefault(location_name, {})
            year_totals[year_label] = year_totals.get(year_label, 0) + value

    return totals_by_location


#### fetch the most recent `num_years` periods of data from the indicator's live page, for Texas
#### (statewide) plus whichever counties are named in `county_names`. A "period" is normally a
#### single year ("2023") but for some indicators is a multi-year ACS range ("2018 - 2022").
#### returns {location_name: {year_label: total}}, e.g. {'Texas': {'2019': 50183, ...}, 'Bexar': {...}}
#### raises ReferenceDataUnavailable if the site can't be reached or its layout has changed -
#### callers should catch this and just skip the check, since it's an external site we don't control
def fetch_recent_totals(page_url, county_names, num_years=5):
    config = _get_indicator_page_config(page_url)

    number_format_id = config['format_id_by_label'].get('Number')
    if number_format_id is None:
        raise ReferenceDataUnavailable(
            "This indicator doesn't report a 'Number' format on the site - only 'Number' values "
            "are additive across breakdown categories, so totals can't be checked this way."
        )

    recent_periods = sorted(
        config['year_label_by_timeframe_id'].items(),
        key=lambda item: _year_label_sort_key(item[1]),
        reverse=True,
    )[:num_years]
    recent_timeframe_ids = [timeframe_id for timeframe_id, year_label in recent_periods]

    texas_html = _fetch_data_table_html(
        page_url, config['indicator_id'], [TEXAS_LOCATION_ID], '2',
        recent_timeframe_ids, number_format_id, config['category_ids'],
    )
    totals = _sum_totals_by_location_and_year(
        texas_html, config['year_label_by_timeframe_id'], number_format_id, {TEXAS_LOCATION_ID: 'Texas'},
    )

    if county_names:
        county_id_by_name = {name: str(locations_dict[name]) for name in county_names}
        county_html = _fetch_data_table_html(
            page_url, config['indicator_id'], list(county_id_by_name.values()), '5',
            recent_timeframe_ids, number_format_id, config['category_ids'],
        )
        totals.update(_sum_totals_by_location_and_year(
            county_html, config['year_label_by_timeframe_id'], number_format_id,
            {loc_id: name for name, loc_id in county_id_by_name.items()},
        ))

    return totals
