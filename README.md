# air-quality-data-pipeline

# Air Quality Data Pipeline

A Python data pipeline that cleans and combines air-quality, weather, health, and socioeconomic sample data using Pandas. Developed for DS3500, the project demonstrates source-specific transformations, relational joins, AQI summaries, and automated testing.

The repository contains the cleaning and merging stages plus five sample CSVs. It produces a daily table in memory and exports a city summary to Parquet. The supplied samples produce results for Boston; the merge configuration also includes NYC, Philadelphia, and Washington, D.C.

## Project Scope

This project focuses on preparing data for exploratory analysis. It includes:

- Cleaning functions for EPA AQS, NOAA, OpenAQ, CDC PLACES, and U.S. Census data.
- Daily left joins using city and date.
- Four AQI groups summarized as percentages of retained observations.
- County FIPS joins to attach health and socioeconomic fields.
- A 33-test Pytest suite covering sample schemas, transformations, joins, and selected validation checks.

The supplied code does not fetch live data, train models, generate visualizations, or establish relationships between pollution and health outcomes. The original documentation references `project_proposal_code.py`, but that file is not included.

## Repository Structure

```text
air-quality-data-pipeline/
├── README.md
├── data/
│   ├── sample_epa.csv
│   ├── sample_noaa.csv
│   ├── sample_openaq.csv
│   ├── sample_cdc.csv
│   └── sample_census.csv
└── src/
    ├── clean.py
    ├── merge.py
    └── test_pipeline.py
```

Running the merge script creates `data/final_dataset.parquet`.

The scripts and tests are kept together in `src/` to preserve the existing imports and file references. Run the scripts from that directory because their data paths are relative to the working directory.

## Included Data

Counts below describe the supplied files and the output of their cleaning functions.

| Source | Raw rows | Cleaned rows | Contents and coverage |
|---|---:|---:|---|
| EPA AQS | 100 | 13 | Boston PM2.5 and AQI observations, January 12–March 16, 2023; repeated records include different pollutant standards. |
| NOAA | 100 | 6 | Boston weather records; retained daily values span January 1–6, 2023. |
| OpenAQ | 39 | 27 | Monitoring-location metadata for Boston, NYC, Philadelphia, and DC; retained `datetimeFirst` dates span 2016–2026. |
| CDC PLACES | 100 | 1 | Suffolk County records with tract identifiers and 2022/2023 values; the cleaner retains one asthma record. |
| U.S. Census | 4 | 4 | Income and poverty-population fields for Suffolk County, New York County, Philadelphia County, and the District of Columbia. |

The original documentation identifies the Census data as 2022 ACS five-year estimates. The CSV itself has no year field, and the fetching script is unavailable, so that vintage cannot be independently verified from the supplied code and data.

## Cleaning Logic

### EPA

`clean_epa` selects `date_local`, `city`, `aqi`, and `arithmetic_mean`. It renames the date field to `date` and `arithmetic_mean` to `pm25`, parses dates, drops rows missing AQI or PM2.5, and keeps the first row for each city-date pair.

It does not average repeated measurements or explicitly filter pollutant codes. The supplied EPA sample contains PM2.5 records.

### NOAA

`clean_noaa` retains `TMAX`, `TMIN`, `AWND`, and `PRCP`, parses dates, and pivots the long table into `tmax`, `tmin`, `awnd`, and `prcp` columns. When multiple values exist for a city-date-variable combination, the pivot uses the first non-null value.

Rows missing maximum temperature or average wind speed are removed. Minimum temperature and precipitation are optional. Values are retained as supplied; the code performs no unit conversions. If a required weather variable is absent from the entire input, the expected pivot column may be missing and cleaning can fail.

### OpenAQ

`clean_openaq` keeps `city` and `datetimeFirst`, extracts the `local` timestamp from its stringified dictionary using a regular expression, truncates it to a calendar date, and parses it. Invalid dates are dropped, followed by duplicate city-date pairs.

This input contains location metadata rather than a daily concentration series. Matching a location's first timestamp does not establish that the location reported on every subsequent day, and it does not validate EPA measurements.

### CDC PLACES

`clean_cdc` keeps `countyfips`, `measure`, and `data_value`, renaming them to `fips`, `measure`, and `value`. It selects measure names containing `asthma` or `respir`, drops missing values, pads FIPS strings to five characters, and keeps the first record for each FIPS-measure pair.

The sample contains two asthma records with different tract identifiers and values of 10.3 and 10.8. The cleaner retains 10.3. It discards tract identifiers, year, and estimate type, and does not calculate a county-level prevalence estimate.

### U.S. Census

`clean_census` renames `B19013_001E` to `median_income` and `B17001_002E` to `poverty_population`. It converts both fields to numeric values, drops rows where either conversion is missing, and constructs a five-character FIPS code from the state and county fields.

The cleaner preserves the other input columns. `poverty_population` is a population count, not a poverty rate.

## Merge Logic

1. **Daily joins:** EPA is the base table. NOAA is left-joined on `city` and `date`, followed by the cleaned OpenAQ city-date pairs. `openaq_present` records whether an exact OpenAQ match exists; unmatched rows receive `False`.
2. **AQI summary:** Each retained daily row is assigned a category. Counts are divided by the number of retained dated rows for each city and multiplied by 100. Missing category columns are added with zero values.
3. **FIPS joins:** City names are mapped to county FIPS codes. CDC measures are pivoted into columns, then CDC and selected Census fields are left-joined to the AQI summary.

| Code category | AQI rule | Output column |
|---|---|---|
| `good` | AQI ≤ 50 | `pct_good` |
| `moderate` | 50 < AQI ≤ 100 | `pct_moderate` |
| `unhealthy_sensitive` | 100 < AQI ≤ 150 | `pct_unhealthy_sensitive` |
| `unhealthy` | AQI > 150 | `pct_unhealthy` |

These are the implementation's four groups: all values above 150 are collapsed into one category. Percentages describe the retained observations, not a complete calendar year.

| City label | FIPS | Mapped geography |
|---|---|---|
| Boston | `25025` | Suffolk County |
| NYC | `36061` | New York County |
| Philadelphia | `42101` | Philadelphia County |
| DC | `11001` | District of Columbia |

New York County represents Manhattan, so the NYC mapping does not cover all five boroughs. City labels must match exactly; the supplied cleaning code does not normalize aliases such as `New York` to `NYC`.

## Running the Pipeline

Use Python 3. From the repository root, create an environment and install the runtime and test dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pandas numpy pyarrow pytest
```

On Windows, activate the environment with `.venv\Scripts\activate`.

Run the scripts from `src/`:

```bash
cd src
python clean.py
python merge.py
```

`clean.py` prints previews of the cleaned tables. `merge.py` cleans the samples, prints previews of the daily and final tables, and writes `../data/final_dataset.parquet`. Re-running it overwrites that output.

No API credentials are required for this sample-based workflow.

## Outputs and Verified Sample Results

`build_pipeline(...)` returns two Pandas DataFrames: `(daily, final)`.

- **Daily table:** 13 rows and 10 columns: `date`, `city`, `aqi`, `pm25`, `awnd`, `prcp`, `tmax`, `tmin`, `openaq_present`, and `aqi_category`. It is returned in memory and previewed in the terminal, but is not automatically saved.
- **Final table:** One Boston row and 10 columns, exported to Parquet. It contains the city, four AQI percentages, FIPS, the retained CDC measure, income, poverty population, and `city_census`.

The verified final sample row contains:

| Field | Value |
|---|---|
| `city` | Boston |
| `pct_good` | 100.0 |
| `pct_moderate` | 0.0 |
| `pct_unhealthy_sensitive` | 0.0 |
| `pct_unhealthy` | 0.0 |
| `fips` | `25025` |
| `Current asthma among adults` | 10.3 |
| `median_income` | 87669 |
| `poverty_population` | 126977 |
| `city_census` | Boston |

All 13 EPA observations fall in the code's `good` category. This is a result for the small supplied sample, not a claim about Boston's overall air quality.

None of the retained NOAA dates overlap the EPA dates, so all daily weather values are missing. No OpenAQ first-date records match the EPA city-date pairs, so all `openaq_present` values are `False`. Weather, PM2.5 values, and the OpenAQ flag are not carried into the final city summary.

## Testing

From the repository root:

```bash
python -m pytest src/test_pipeline.py -v
```

The supplied suite contains 33 tests. Verification with the recommended layout produced **32 passes and 1 failure**. The failing test, `test_fetch_census_uses_correct_variables`, attempts to read the absent `src/project_proposal_code.py`.

To run only the tests supported by the included files:

```bash
python -m pytest src/test_pipeline.py -v -k "not test_fetch_census_uses_correct_variables"
```

Coverage includes EPA/NOAA CSV column checks, duplicate removal, date parsing, NOAA pivoting, CDC filtering, Census numeric conversion and FIPS construction, left-join behavior, OpenAQ match flags, AQI percentage calculations, the AQI 50 boundary, FIPS joins, and pipeline return types.

Most checks use small synthetic fixtures. Assertions about nonnegative values, positive income, or temperature ordering do not mean the cleaners enforce those constraints on arbitrary inputs. The suite does not establish complete sample join coverage, geographic validity, or successful Parquet export. The Parquet export was verified separately by running `merge.py`.

The verified environment also emitted a Pandas future warning for the OpenAQ flag's `fillna(False)` operation.

## Interpretation and Limitations

This is a coursework pipeline prototype with a reproducible sample transformation. Its main limitations are incomplete temporal overlap, first-record selection instead of principled aggregation, an OpenAQ metadata match rather than measurement validation, and loss of geographic and temporal detail in CDC cleaning.

The final health value must not be presented as a county-wide asthma estimate. The output also does not support causal conclusions or a comparison of health outcomes across the four configured cities. Additional source coverage, consistent geographic units, aligned years, and stronger validation would be needed for those analyses.

## Coursework and Contributors

Created for **DS3500 — Advanced Programming with Data**.

The submission metadata lists these contributors:

- Edlawit Zewde
- Rau-Shawn Tribuce
- Ilanna Lam
- Gabrielle Tugano
