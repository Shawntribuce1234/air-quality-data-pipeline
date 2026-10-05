import pandas as pd

# -----------------------------
# EPA CLEANING FUNCTION
# -----------------------------
def clean_epa(df):
    # Keep only relevant columns
    df = df[["date_local", "city", "aqi", "arithmetic_mean"]]

    # Rename columns for consistency across datasets
    df = df.rename(columns={
        "date_local": "date",
        "aqi": "aqi",
        "arithmetic_mean": "pm25"
    })

    # Convert date column to datetime
    df['date'] = pd.to_datetime(df['date'])

    # Remove rows missing AQI or PM2.5 values
    df = df.dropna(subset=['aqi', 'pm25'])

    # Remove duplicate city-date pairs
    df = df.drop_duplicates(subset=['city', 'date'])

    return df


# -----------------------------
# NOAA CLEANING FUNCTION
# -----------------------------
def clean_noaa(df):
    # Keep only the columns needed for weather metrics
    df = df[["date", "city", "datatype", "value"]].copy()

    # Filter for the weather variables of interest
    df = df[df["datatype"].isin(["TMAX", "TMIN", "AWND", "PRCP"])]

    # Convert date column to datetime
    df["date"] = pd.to_datetime(df["date"])

    # Pivot so each datatype becomes its own column
    df = df.pivot_table(
        index=["date", "city"],
        columns="datatype",
        values="value",
        aggfunc="first"  # Use first value if duplicates exist
    ).reset_index()

    # Rename columns to cleaner names
    df = df.rename(columns={
        "TMAX": "tmax",
        "TMIN": "tmin",
        "AWND": "awnd",
        "PRCP": "prcp"
    })

    # Require at least temperature max and wind speed
    df = df.dropna(subset=["tmax", "awnd"])

    # Remove duplicate city-date pairs
    df = df.drop_duplicates(subset=["city", "date"])

    return df


# -----------------------------
# CDC CLEANING FUNCTION
# -----------------------------
def clean_cdc(df):
    # Keep only relevant columns
    df = df[["countyfips", "measure", "data_value"]].copy()

    # Standardize column names
    df = df.rename(columns={
        "countyfips": "fips",
        "data_value": "value"
    })

    # Keep only asthma/respiratory-related measures
    df = df[df["measure"].str.contains("asthma|respir", case=False, na=False)]

    # Remove rows missing the value
    df = df.dropna(subset=["value"])

    # Ensure FIPS codes are 5-digit strings
    df["fips"] = df["fips"].astype(str).str.zfill(5)

    # Remove duplicate FIPS-measure pairs
    df = df.drop_duplicates(subset=["fips", "measure"])

    return df


# -----------------------------
# OPENAQ CLEANING FUNCTION
# -----------------------------
def clean_openaq(df):
    # Keep only city and datetime info
    df = df[["city", "datetimeFirst"]].copy()

    # Rename for consistency
    df = df.rename(columns={"datetimeFirst": "date"})

    # Extract the 'local' timestamp from nested string structure
    df["date"] = df["date"].str.extract(r"'local': '([^']+)'")

    # Keep only the YYYY-MM-DD portion
    df["date"] = df["date"].str[:10]

    # Convert to datetime, coercing invalid formats to NaT
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Drop rows with invalid or missing dates
    df = df.dropna(subset=["date"])

    # Remove duplicate city-date pairs
    df = df.drop_duplicates(subset=["city", "date"])

    return df


# -----------------------------
# CENSUS CLEANING FUNCTION
# -----------------------------
def clean_census(df):
    # Rename census variables to readable names
    df = df.rename(columns={
        "B19013_001E": "median_income",
        "B17001_002E": "poverty_population"
    })

    # Convert numeric fields, coercing invalid values
    df["median_income"] = pd.to_numeric(df["median_income"], errors="coerce")
    df["poverty_population"] = pd.to_numeric(df['poverty_population'], errors="coerce")

    # Drop rows missing key socioeconomic indicators
    df = df.dropna(subset=['median_income', 'poverty_population'])

    # Construct FIPS code from state + county codes
    df['fips'] = df['state'].astype(str).str.zfill(2) + df['county'].astype(str).str.zfill(3)

    return df


# -----------------------------
# MAIN EXECUTION BLOCK
# -----------------------------
if __name__ == "__main__":
    # Load raw datasets
    epa_raw = pd.read_csv("../data/sample_epa.csv")
    noaa_raw = pd.read_csv("../data/sample_noaa.csv")
    openaq_raw = pd.read_csv("../data/sample_openaq.csv")
    cdc_raw = pd.read_csv("../data/sample_cdc.csv")
    census_raw = pd.read_csv("../data/sample_census.csv")

    # Apply cleaning functions
    epa_clean = clean_epa(epa_raw)
    noaa_clean = clean_noaa(noaa_raw)
    openaq_clean = clean_openaq(openaq_raw)
    cdc_clean = clean_cdc(cdc_raw)
    census_clean = clean_census(census_raw)

    # Display cleaned outputs
    print("EPA cleaned:")
    print(epa_clean.head(), "\n")

    print("NOAA cleaned:")
    print(noaa_clean.head(), "\n")

    print("OpenAQ cleaned:")
    print(openaq_clean.head(), "\n")

    print("CDC cleaned:")
    print(cdc_clean.head(), "\n")

    print("Census cleaned:")
    print(census_clean.head(), "\n")