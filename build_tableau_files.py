# generate_dashboard_csvs.py
# Purpose:
# 1) Assign each real estate listing to an Ottawa ward using latitude/longitude + official ward polygons (GeoJSON).
# 2) Aggregate listings to ward-level housing metrics (median price, counts, walkscore, style shares).
# 3) Merge with ward income and compute affordability metrics for your dashboard.
#
# Output files:
# - ottawa_real_estate_by_ward.csv
# - ottawa_affordability_risk_dashboard.csv

import re
import json
import math
import pandas as pd

# ---- Optional install note (run once in your environment) ----
# pip install shapely requests

from shapely.geometry import Point, shape
import requests


# ----------------------------
# Paths (edit if needed)
# ----------------------------
INCOME_PATH = r"/mnt/data/ottawa_income_clean.csv"
REAL_ESTATE_PATH = r"/mnt/data/ottawa_real_estate.csv"

OUT_WARD_AGG_PATH = r"ottawa_real_estate_by_ward.csv"
OUT_DASHBOARD_PATH = r"ottawa_affordability_risk_dashboard.csv"


# ----------------------------
# Helpers
# ----------------------------
def parse_money_to_float(x):
    """
    Convert price strings like "2,500,000" to 2500000.0
    Returns NaN for invalid values.
    """
    if pd.isna(x):
        return float("nan")
    s = str(x).strip()

    # Remove quotes and whitespace
    s = s.replace('"', "").strip()

    # Keep digits, decimal point, minus sign
    s = re.sub(r"[^0-9\.\-]", "", s)

    if s == "" or s == "." or s == "-" or s == "-.":
        return float("nan")

    try:
        return float(s)
    except ValueError:
        return float("nan")


def fetch_ottawa_wards_geojson():
    """
    Downloads Ottawa ward boundaries as GeoJSON from the City of Ottawa ArcGIS service.
    ArcGIS service supports geoJSON format.
    """
    url = (
        "https://maps.ottawa.ca/arcgis/rest/services/Wards/MapServer/0/query"
        "?where=1%3D1"
        "&outFields=*"
        "&outSR=4326"
        "&f=geojson"
    )

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def detect_ward_id_field(geojson_obj):
    """
    Tries to auto-detect which property field corresponds to the ward number (1..24-ish).
    This avoids you having to guess whether it's WARD, WARD_NUM, WARDID, etc.
    """
    features = geojson_obj.get("features", [])
    if not features:
        raise ValueError("No features found in wards GeoJSON.")

    props = features[0].get("properties", {})
    candidate_keys = list(props.keys())

    # For each key, see if values across features look like ward numbers (mostly ints 1..24)
    best_key = None
    best_score = -1

    for k in candidate_keys:
        vals = []
        for f in features:
            v = f.get("properties", {}).get(k, None)
            vals.append(v)

        # Try converting to ints
        converted = []
        ok = 0
        for v in vals:
            try:
                iv = int(str(v).strip())
                converted.append(iv)
                ok += 1
            except Exception:
                continue

        # Score: how many successfully parse + plausibility in range
        if ok == 0:
            continue

        in_range = sum(1 for iv in converted if 1 <= iv <= 30)
        score = ok + in_range  # crude but effective

        if score > best_score:
            best_score = score
            best_key = k

    if best_key is None:
        raise ValueError(
            "Could not auto-detect ward number field in GeoJSON properties. "
            "Open the GeoJSON and find which field stores ward IDs."
        )

    return best_key


def assign_ward_to_points(listings_df, ward_polygons, ward_id_field):
    """
    Brute-force point-in-polygon assignment.
    With 24 wards and ~1k listings, this is fast and avoids heavyweight geo dependencies.

    Returns a copy of listings_df with a new column: Ward (int)
    """
    wards = []
    for w in ward_polygons:
        geom = w["geometry"]      # shapely polygon
        ward_id = w["ward_id"]    # int ward ID
        wards.append((ward_id, geom))

    out = listings_df.copy()
    out["Ward"] = pd.NA

    # Iterate rows and test containment
    for i, row in out.iterrows():
        lat = row.get("latitude", None)
        lon = row.get("longitude", None)

        # Skip bad coordinates
        if pd.isna(lat) or pd.isna(lon):
            continue

        pt = Point(float(lon), float(lat))  # shapely uses (x=lon, y=lat)

        assigned = None
        for ward_id, poly in wards:
            # contains() excludes boundary sometimes; covers() includes boundary points
            if poly.covers(pt):
                assigned = ward_id
                break

        out.at[i, "Ward"] = assigned

    # Drop rows we couldn't assign to a ward
    out = out.dropna(subset=["Ward"]).copy()
    out["Ward"] = out["Ward"].astype(int)

    return out


def affordability_band(ratio):
    """
    Converts affordability ratio into a risk label.
    Ratio = MedianPrice / AvgIncome
    """
    if pd.isna(ratio):
        return "Unknown"
    if ratio < 4:
        return "More Affordable (<4x)"
    if ratio < 6:
        return "Stretched (4–6x)"
    if ratio < 8:
        return "High Risk (6–8x)"
    return "Severe Risk (8x+)"


# ----------------------------
# Main pipeline
# ----------------------------
def main():
    # --- Load income data ---
    income = pd.read_csv(INCOME_PATH)

    # Ensure Ward is int for clean joins
    income["Ward"] = pd.to_numeric(income["Ward"], errors="coerce")
    income = income.dropna(subset=["Ward"]).copy()
    income["Ward"] = income["Ward"].astype(int)

    # Ensure income is numeric
    income["Average_Household_Income"] = pd.to_numeric(
        income["Average_Household_Income"], errors="coerce"
    )
    income = income.dropna(subset=["Average_Household_Income"]).copy()

    # --- Load raw real estate listings ---
    re_df = pd.read_csv(REAL_ESTATE_PATH)

    # Rename the misleading "ward" column (it contains listing style in your file)
    # We keep it as a useful categorical dimension for composition analysis.
    if "ward" in re_df.columns:
        re_df = re_df.rename(columns={"ward": "Listing_Style"})

    # Parse price to numeric
    re_df["Price"] = re_df["price"].apply(parse_money_to_float)

    # Make walkScore numeric
    re_df["walkScore"] = pd.to_numeric(re_df["walkScore"], errors="coerce")

    # Drop listings missing key fields
    re_df = re_df.dropna(subset=["latitude", "longitude", "Price"]).copy()

    # --- Fetch ward polygons (GeoJSON) ---
    wards_geojson = fetch_ottawa_wards_geojson()
    ward_id_field = detect_ward_id_field(wards_geojson)

    # Convert GeoJSON features into shapely polygons + ward id
    ward_polygons = []
    for f in wards_geojson.get("features", []):
        props = f.get("properties", {})
        ward_id = int(str(props.get(ward_id_field)).strip())
        poly = shape(f.get("geometry"))
        ward_polygons.append({"ward_id": ward_id, "geometry": poly})

    # --- Assign each listing to a ward ---
    re_with_ward = assign_ward_to_points(re_df, ward_polygons, ward_id_field)

    # --- Aggregate to ward-level housing metrics ---
    ward_agg = (
        re_with_ward
        .groupby("Ward", as_index=False)
        .agg(
            Listings=("Price", "count"),                 # how many listings per ward
            Median_List_Price=("Price", "median"),       # median listing price
            Mean_List_Price=("Price", "mean"),           # average listing price
            Median_WalkScore=("walkScore", "median"),    # median walkability score
        )
    )

    # Optional: compute listing-style shares per ward (top-level composition)
    # This helps tell “what kind of housing is being listed where”.
    if "Listing_Style" in re_with_ward.columns:
        style_counts = (
            re_with_ward
            .groupby(["Ward", "Listing_Style"], as_index=False)
            .size()
            .rename(columns={"size": "Style_Count"})
        )

        # Total listings per ward for share calc
        totals = style_counts.groupby("Ward", as_index=False)["Style_Count"].sum().rename(
            columns={"Style_Count": "Ward_Total"}
        )

        style_counts = style_counts.merge(totals, on="Ward", how="left")
        style_counts["Style_Share"] = style_counts["Style_Count"] / style_counts["Ward_Total"]

        # Pivot to wide format: Style_Share_<Category> columns
        style_pivot = style_counts.pivot_table(
            index="Ward",
            columns="Listing_Style",
            values="Style_Share",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()

        # Flatten column names for CSV friendliness
        style_pivot.columns = [
            "Ward" if c == "Ward" else f"StyleShare_{str(c).strip().replace(' ', '_')}"
            for c in style_pivot.columns
        ]

        ward_agg = ward_agg.merge(style_pivot, on="Ward", how="left")

    # Save ward-level real estate metrics
    ward_agg.to_csv(OUT_WARD_AGG_PATH, index=False)

    # --- Merge with income and compute affordability metrics ---
    dashboard = income.merge(ward_agg, on="Ward", how="inner")

    dashboard["Affordability_Ratio"] = dashboard["Median_List_Price"] / dashboard["Average_Household_Income"]
    dashboard["Affordability_Band"] = dashboard["Affordability_Ratio"].apply(affordability_band)

    # Helpful labels for Tableau
    dashboard["Ward_Label"] = "Ward " + dashboard["Ward"].astype(str)

    # Save final dashboard dataset
    dashboard.to_csv(OUT_DASHBOARD_PATH, index=False)

    print("✅ Wrote:", OUT_WARD_AGG_PATH)
    print("✅ Wrote:", OUT_DASHBOARD_PATH)
    print(dashboard.head())


if __name__ == "__main__":
    main()
