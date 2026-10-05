"""
test_pipeline.py
Pytest suite for the air quality data pipeline (clean.py + merge.py).

Run with:
    pytest test_pipeline.py -v
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Import the modules under test.
# Adjust the import path if clean.py / merge.py live in a sub-package.
# ---------------------------------------------------------------------------
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from clean import clean_epa, clean_noaa, clean_cdc, clean_openaq, clean_census
from merge import merge_daily, bin_aqi, merge_fips, build_pipeline, AQI_GOOD, AQI_MODERATE


# ===========================================================================
# Shared fixtures
# ===========================================================================

@pytest.fixture
def raw_epa():
    """Minimal raw EPA DataFrame that mirrors the real CSV schema."""
    return pd.DataFrame({
        "date_local": ["2023-01-12", "2023-01-12", "2023-01-13", "2023-01-14"],
        "city":       ["Boston",     "Boston",     "Boston",     "NYC"],
        "aqi":        [49.0,         49.0,          65.0,         80.0],
        "arithmetic_mean": [8.8,     8.8,           12.1,         15.3],
        "extra_col":  ["x",          "x",           "y",          "z"],   # should be dropped
    })


@pytest.fixture
def raw_noaa():
    """Minimal raw NOAA DataFrame (long format, one row per datatype per day)."""
    rows = []
    for dt, val in [("TMAX", 50.0), ("TMIN", 30.0), ("AWND", 8.5), ("PRCP", 0.0)]:
        rows.append({"date": "2023-01-12", "city": "Boston", "datatype": dt, "value": val})
    for dt, val in [("TMAX", 55.0), ("TMIN", 35.0), ("AWND", 6.0), ("PRCP", 0.1)]:
        rows.append({"date": "2023-01-13", "city": "Boston", "datatype": dt, "value": val})
    # Duplicate row to verify deduplication
    rows.append({"date": "2023-01-12", "city": "Boston", "datatype": "TMAX", "value": 50.0})
    return pd.DataFrame(rows)


@pytest.fixture
def raw_cdc():
    """Minimal raw CDC DataFrame."""
    return pd.DataFrame({
        "countyfips": [25025,  25025,  25025,  36061],
        "measure":    [
            "Current asthma prevalence among adults aged >=18 years",
            "Stroke among adults",
            "Respiratory health indicator",
            "Current asthma prevalence among adults aged >=18 years",
        ],
        "data_value": [9.1, 3.2, 5.5, 10.0],
    })


@pytest.fixture
def raw_openaq():
    """Minimal raw OpenAQ DataFrame with the nested-dict date column."""
    return pd.DataFrame({
        "city": ["Boston", "Boston", "NYC"],
        "datetimeFirst": [
            "{'utc': '2023-01-12T08:00:00Z', 'local': '2023-01-12T03:00:00-05:00'}",
            "{'utc': '2023-01-12T08:00:00Z', 'local': '2023-01-12T03:00:00-05:00'}",  # dup
            "{'utc': '2023-01-13T08:00:00Z', 'local': '2023-01-13T03:00:00-05:00'}",
        ],
    })


@pytest.fixture
def raw_census():
    """Minimal raw Census DataFrame."""
    return pd.DataFrame({
        "B19013_001E": ["87669", "99880"],
        "B17001_002E": ["126977", "252677"],
        "NAME":  ["Suffolk County, Massachusetts", "New York County, New York"],
        "state":  ["25", "36"],
        "county": ["025", "061"],
        "city":   ["Boston", "NYC"],
    })


# ---------------------------------------------------------------------------
# Pre-cleaned fixtures used by the merge tests
# ---------------------------------------------------------------------------

@pytest.fixture
def epa_clean(raw_epa):
    return clean_epa(raw_epa)


@pytest.fixture
def noaa_clean(raw_noaa):
    return clean_noaa(raw_noaa)


@pytest.fixture
def openaq_clean(raw_openaq):
    return clean_openaq(raw_openaq)


@pytest.fixture
def cdc_clean(raw_cdc):
    return clean_cdc(raw_cdc)


@pytest.fixture
def census_clean(raw_census):
    return clean_census(raw_census)


# ===========================================================================
# 1. DATA LOADING / FETCHING
# ===========================================================================

class TestDataLoading:
    """Verify that sample CSV files load and contain the expected columns."""

    SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

    def test_epa_csv_loads_with_required_columns(self):
        """Sample EPA CSV must contain the four columns used by clean_epa."""
        required = {"date_local", "city", "aqi", "arithmetic_mean"}
        df = pd.read_csv(os.path.join(self.SAMPLE_DIR, "sample_epa.csv"))
        assert required.issubset(df.columns), (
            f"Missing columns: {required - set(df.columns)}"
        )

    def test_noaa_csv_loads_with_required_columns(self):
        """Sample NOAA CSV must contain date, city, datatype, value columns."""
        required = {"date", "city", "datatype", "value"}
        df = pd.read_csv(os.path.join(self.SAMPLE_DIR, "sample_noaa.csv"))
        assert required.issubset(df.columns)


    def test_fetch_census_uses_correct_variables(self):
        """project_proposal_code.py must request the two expected Census variables."""
        import ast, inspect
        # Read the source file and check that both ACS variable codes appear
        with open(os.path.join(os.path.dirname(__file__), "project_proposal_code.py")) as f:
            src = f.read()
        assert "B19013_001E" in src, "Median income variable missing from census fetch"
        assert "B17001_002E" in src, "Poverty population variable missing from census fetch"


# ===========================================================================
# 2. DATA CLEANING
# ===========================================================================

class TestCleanEPA:
    def test_duplicate_city_date_rows_are_removed(self, raw_epa):
        """clean_epa must drop duplicate (city, date) pairs."""
        result = clean_epa(raw_epa)
        assert result.duplicated(subset=["city", "date"]).sum() == 0

    def test_output_columns_are_exactly_date_city_aqi_pm25(self, raw_epa):
        """clean_epa must return only the four expected columns."""
        result = clean_epa(raw_epa)
        assert set(result.columns) == {"date", "city", "aqi", "pm25"}

    def test_date_column_is_datetime(self, raw_epa):
        """clean_epa must parse the date column as datetime64."""
        result = clean_epa(raw_epa)
        assert pd.api.types.is_datetime64_any_dtype(result["date"])

    def test_rows_with_null_aqi_are_dropped(self):
        """Rows where aqi is NaN must be removed."""
        df = pd.DataFrame({
            "date_local": ["2023-01-01", "2023-01-02"],
            "city":       ["Boston",      "Boston"],
            "aqi":        [None,           50.0],
            "arithmetic_mean": [5.0,       8.0],
        })
        result = clean_epa(df)
        assert len(result) == 1
        assert result.iloc[0]["aqi"] == 50.0


class TestCleanNOAA:
    def test_pivot_creates_tmax_tmin_awnd_prcp_columns(self, raw_noaa):
        """clean_noaa must pivot the long data into wide format with expected columns."""
        result = clean_noaa(raw_noaa)
        for col in ["tmax", "tmin", "awnd", "prcp"]:
            assert col in result.columns, f"Expected column '{col}' not found"

    def test_duplicate_city_date_rows_are_removed(self, raw_noaa):
        """After pivoting, clean_noaa must not have duplicate (city, date) rows."""
        result = clean_noaa(raw_noaa)
        assert result.duplicated(subset=["city", "date"]).sum() == 0

    def test_only_relevant_datatypes_are_kept(self, raw_noaa):
        """clean_noaa should silently ignore irrelevant datatypes (e.g. ADPT, ASLP)."""
        extra = pd.DataFrame([
            {"date": "2023-01-15", "city": "Boston", "datatype": "ADPT", "value": 44.0},
            {"date": "2023-01-15", "city": "Boston", "datatype": "TMAX", "value": 52.0},
            {"date": "2023-01-15", "city": "Boston", "datatype": "TMIN", "value": 31.0},
            {"date": "2023-01-15", "city": "Boston", "datatype": "AWND", "value": 7.0},
            {"date": "2023-01-15", "city": "Boston", "datatype": "PRCP", "value": 0.0},
        ])
        result = clean_noaa(extra)
        # ADPT is not a kept datatype, so it should not appear as a column
        assert "adpt" not in result.columns


class TestCleanCDC:
    def test_non_asthma_non_respiratory_measures_are_excluded(self, raw_cdc):
        """clean_cdc must filter to only asthma/respiratory measures."""
        result = clean_cdc(raw_cdc)
        assert all(
            "asthma" in m.lower() or "respir" in m.lower()
            for m in result["measure"]
        )

    def test_fips_is_zero_padded_to_5_digits(self, raw_cdc):
        """FIPS codes must be zero-padded strings of length 5."""
        result = clean_cdc(raw_cdc)
        assert all(len(f) == 5 for f in result["fips"])


class TestCleanCensus:
    def test_fips_is_constructed_correctly(self, raw_census):
        """FIPS = state (2 digits) + county (3 digits) must equal 5 characters."""
        result = clean_census(raw_census)
        assert all(len(f) == 5 for f in result["fips"])
        assert "25025" in result["fips"].values

    def test_numeric_conversion_of_income_and_poverty(self, raw_census):
        """median_income and poverty_population must be numeric after cleaning."""
        result = clean_census(raw_census)
        assert pd.api.types.is_numeric_dtype(result["median_income"])
        assert pd.api.types.is_numeric_dtype(result["poverty_population"])


class TestCleanOpenAQ:
    def test_date_is_extracted_from_nested_dict_string(self, raw_openaq):
        """clean_openaq must parse the date from the 'local' key of the stringified dict."""
        result = clean_openaq(raw_openaq)
        assert pd.api.types.is_datetime64_any_dtype(result["date"])
        assert not result["date"].isna().any()

    def test_duplicates_on_city_date_removed(self, raw_openaq):
        """clean_openaq must deduplicate on (city, date)."""
        result = clean_openaq(raw_openaq)
        assert result.duplicated(subset=["city", "date"]).sum() == 0


# ===========================================================================
# 3. MERGE LOGIC
# ===========================================================================

class TestMergeDaily:
    def test_merge_preserves_all_epa_rows(self, epa_clean, noaa_clean, openaq_clean):
        """merge_daily is a left join on EPA; all EPA rows must be in the result."""
        daily = merge_daily(epa_clean, noaa_clean, openaq_clean)
        assert len(daily) == len(epa_clean)

    def test_openaq_present_column_exists_and_is_boolean(self, epa_clean, noaa_clean, openaq_clean):
        """openaq_present must be a boolean column after merge_daily."""
        daily = merge_daily(epa_clean, noaa_clean, openaq_clean)
        assert "openaq_present" in daily.columns
        assert daily["openaq_present"].dtype == bool or daily["openaq_present"].isin([True, False]).all()

    def test_matched_openaq_rows_flagged_true(self, epa_clean, noaa_clean, openaq_clean):
        """Rows that match an OpenAQ record must have openaq_present == True."""
        daily = merge_daily(epa_clean, noaa_clean, openaq_clean)
        # Boston 2023-01-12 exists in our openaq fixture
        mask = (daily["city"] == "Boston") & (daily["date"] == pd.Timestamp("2023-01-12"))
        assert daily.loc[mask, "openaq_present"].all()


class TestBinAQI:
    def _make_daily(self, aqi_values, city="Boston"):
        dates = pd.date_range("2023-01-01", periods=len(aqi_values))
        return pd.DataFrame({"city": city, "aqi": aqi_values, "date": dates})

    def test_all_four_pct_columns_are_present(self):
        """bin_aqi must produce pct_good, pct_moderate, pct_unhealthy_sensitive, pct_unhealthy."""
        daily = self._make_daily([30, 75, 120, 200])
        result = bin_aqi(daily)
        for col in ["pct_good", "pct_moderate", "pct_unhealthy_sensitive", "pct_unhealthy"]:
            assert col in result.columns

    def test_pct_columns_sum_to_100(self):
        """Percentages across all four AQI categories must sum to 100 per city."""
        daily = self._make_daily([30, 75, 120, 200])
        result = bin_aqi(daily)
        pct_cols = ["pct_good", "pct_moderate", "pct_unhealthy_sensitive", "pct_unhealthy"]
        totals = result[pct_cols].sum(axis=1)
        assert (totals - 100.0).abs().max() < 1e-6

    def test_all_good_aqi_gives_100_pct_good(self):
        """When all AQI values are in the 'good' range, pct_good must be 100."""
        daily = self._make_daily([10, 20, 30, 40, 50])
        result = bin_aqi(daily)
        assert result["pct_good"].iloc[0] == pytest.approx(100.0)

    def test_bin_boundary_aqi_50_is_good(self):
        """AQI == 50 must be classified as 'good' (boundary-inclusive)."""
        daily = self._make_daily([50])
        result = bin_aqi(daily)
        assert result["pct_good"].iloc[0] == pytest.approx(100.0)


class TestMergeFIPS:
    def test_fips_column_added_from_city_map(self, epa_clean, noaa_clean, openaq_clean, cdc_clean, census_clean):
        """merge_fips must map city names to FIPS codes."""
        daily = merge_daily(epa_clean, noaa_clean, openaq_clean)
        binned = bin_aqi(daily)
        final = merge_fips(binned, cdc_clean, census_clean)
        assert "fips" in final.columns
        boston_row = final[final["city"] == "Boston"]
        assert not boston_row.empty
        assert boston_row["fips"].iloc[0] == "25025"

    def test_census_columns_present_after_fips_merge(self, epa_clean, noaa_clean, openaq_clean, cdc_clean, census_clean):
        """Final dataset must include Census columns median_income and poverty_population."""
        daily = merge_daily(epa_clean, noaa_clean, openaq_clean)
        binned = bin_aqi(daily)
        final = merge_fips(binned, cdc_clean, census_clean)
        assert "median_income" in final.columns
        assert "poverty_population" in final.columns


# ===========================================================================
# 4. DATA VALIDATION
# ===========================================================================

class TestDataValidation:
    def test_aqi_values_are_non_negative(self, raw_epa):
        """After cleaning, all AQI values must be >= 0."""
        result = clean_epa(raw_epa)
        assert (result["aqi"] >= 0).all(), "Negative AQI values found"

    def test_pm25_values_are_non_negative(self, raw_epa):
        """PM2.5 concentrations must be >= 0 µg/m³ after cleaning."""
        result = clean_epa(raw_epa)
        assert (result["pm25"] >= 0).all()

    def test_pct_columns_are_between_0_and_100(self):
        """All AQI percentage columns produced by bin_aqi must be in [0, 100]."""
        daily = pd.DataFrame({
            "city": ["Boston"] * 5 + ["NYC"] * 5,
            "aqi":  [20, 50, 80, 120, 180, 15, 60, 90, 140, 200],
            "date": pd.date_range("2023-01-01", periods=10),
        })
        result = bin_aqi(daily)
        for col in ["pct_good", "pct_moderate", "pct_unhealthy_sensitive", "pct_unhealthy"]:
            assert result[col].between(0, 100).all(), f"{col} has out-of-range values"

    def test_census_median_income_is_positive(self, raw_census):
        """Median household income must be a positive number after cleaning."""
        result = clean_census(raw_census)
        assert (result["median_income"] > 0).all()

    def test_noaa_tmax_greater_than_tmin(self, raw_noaa):
        """After cleaning, TMAX must be >= TMIN for every row."""
        result = clean_noaa(raw_noaa)
        assert (result["tmax"] >= result["tmin"]).all(), \
            "Found rows where TMAX < TMIN"

    def test_cdc_fips_codes_are_valid_strings(self, raw_cdc):
        """FIPS codes in the cleaned CDC table must be non-empty 5-char strings."""
        result = clean_cdc(raw_cdc)
        assert result["fips"].apply(lambda x: isinstance(x, str) and len(x) == 5).all()

    def test_no_nulls_in_epa_key_columns_after_cleaning(self, raw_epa):
        """date, city, aqi, and pm25 must all be non-null after clean_epa."""
        result = clean_epa(raw_epa)
        assert result[["date", "city", "aqi", "pm25"]].notna().all().all()

    def test_build_pipeline_returns_two_dataframes(self, epa_clean, noaa_clean, openaq_clean, cdc_clean, census_clean):
        """build_pipeline must return exactly two DataFrames: (daily, final)."""
        result = build_pipeline(epa_clean, noaa_clean, openaq_clean, cdc_clean, census_clean)
        assert isinstance(result, tuple) and len(result) == 2
        daily, final = result
        assert isinstance(daily, pd.DataFrame)
        assert isinstance(final, pd.DataFrame)