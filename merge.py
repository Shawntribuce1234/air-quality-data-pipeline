"""
Merge layer for the air quality project.
Takes cleaned DataFrames from clean.py and merges them into one final dataset.
Follows the three step strategy: daily merge, AQI binning, then FIPS join.
"""

import pandas as pd
# maps each city name to its county FIPS code for joining with CDC and Census
CITY_TO_FIPS = {
    "Boston": "25025",
    "NYC": "36061",
    "Philadelphia": "42101",
    "DC": "11001",
}

# EPA standard AQI bin boundaries for the merging the daily aggregates into categories
AQI_GOOD = 50
AQI_MODERATE = 100
AQI_UNHEALTHY_SENSITIVE = 150

# expected AQI category columns after binning
AQI_CATEGORY_COLS = [
    "pct_good",
    "pct_moderate",
    "pct_unhealthy_sensitive",
    "pct_unhealthy"
]

# columns to keep from Census after merging
CENSUS_COLS = ["fips", "median_income", "poverty_population", "city"]

# path to save the final merged dataset
OUTPUT_PATH = "../data/final_dataset.parquet"


def merge_daily(epa_clean, noaa_clean, openaq_clean):
    # merge EPA and NOAA on city + date
    daily = pd.merge(epa_clean, noaa_clean, on=["city", "date"], how="left")

    # merge OpenAQ in as a cross validation column (left join keeps all EPA rows)
    openaq_slim = openaq_clean[["city", "date"]].copy()
    openaq_slim["openaq_present"] = True
    daily = pd.merge(daily, openaq_slim, on=["city", "date"], how="left")

    # flag rows where OpenAQ confirmed a reading
    daily["openaq_present"] = daily["openaq_present"].fillna(False)
    return daily


def bin_aqi(daily):
    # create AQI category column based on EPA standard bins
    def categorize(aqi):
        if aqi <= AQI_GOOD:
            return "good"
        elif aqi <= AQI_MODERATE:
            return "moderate"
        elif aqi <= AQI_UNHEALTHY_SENSITIVE:
            return "unhealthy_sensitive"
        else:
            return "unhealthy"

    daily["aqi_category"] = daily["aqi"].apply(categorize)

    # count total days per city
    total_days = daily.groupby("city")["date"].count().rename("total_days")

    # count days in each category per city
    category_counts = daily.groupby(["city", "aqi_category"]).size().unstack(fill_value=0)

    # calculate percentage of days in each category
    pct = category_counts.div(total_days, axis=0) * 100
    pct.columns = [f"pct_{col}" for col in pct.columns]

    # make sure all 4 category columns exist even if a city had zero days in that category
    for col in AQI_CATEGORY_COLS:
        if col not in pct.columns:
            pct[col] = 0.0

    return pct.reset_index()


def merge_fips(binned, cdc_clean, census_clean):
    # add FIPS code to the binned AQI table using the city name
    binned["fips"] = binned["city"].map(CITY_TO_FIPS)

    # pivot CDC so each health measure becomes its own column
    cdc_pivot = cdc_clean.pivot_table(
        index="fips",
        columns="measure",
        values="value",
        aggfunc="first"
    ).reset_index()

    # join CDC health outcomes on FIPS
    merged = pd.merge(binned, cdc_pivot, on="fips", how="left")

    # join Census socioeconomic data on FIPS
    census_slim = census_clean[CENSUS_COLS].copy()
    merged = pd.merge(merged, census_slim, on="fips", how="left", suffixes=("", "_census"))

    return merged


def build_pipeline(epa_clean, noaa_clean, openaq_clean, cdc_clean, census_clean):
    # run all three merge steps in order
    daily = merge_daily(epa_clean, noaa_clean, openaq_clean)
    binned = bin_aqi(daily)
    final = merge_fips(binned, cdc_clean, census_clean)
    return daily, final


if __name__ == "__main__":
    from clean import clean_epa, clean_noaa, clean_openaq, clean_cdc, clean_census

    epa_clean = clean_epa(pd.read_csv("../data/sample_epa.csv"))
    noaa_clean = clean_noaa(pd.read_csv("../data/sample_noaa.csv"))
    openaq_clean = clean_openaq(pd.read_csv("../data/sample_openaq.csv"))
    cdc_clean = clean_cdc(pd.read_csv("../data/sample_cdc.csv"))
    census_clean = clean_census(pd.read_csv("../data/sample_census.csv"))

    daily, final = build_pipeline(epa_clean, noaa_clean, openaq_clean, cdc_clean, census_clean)

    print("Daily merged table:")
    print(daily.head(), "\n")

    print("Final merged table:")
    print(final.head(), "\n")

    # save final dataset to parquet
    final.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved to {OUTPUT_PATH}")