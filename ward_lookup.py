"""
ward_lookup.py

Creates:
1) data/processed/ward_lookup_ottawa.csv
   - Ward (int)
   - Ward_Name (text)
   - Ward_Full (e.g., "Ward 1 - Orléans East-Cumberland")

2) data/processed/<input>_labeled.csv
   - Your original Tableau dataset plus Ward_Name + Ward_Full + Ward_Label

What it fixes:
- Auto-finds the combined Tableau dataset CSV (even if it's not in the base folder)
- Handles column name variants (Median Price vs Median Home Price, etc.)
- Forces Ward_Label to include the real ward name (Ward X - Name)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pandas as pd
import requests


# -----------------------------
# Ottawa ward names (fallback)
# -----------------------------
FALLBACK_WARDS = {
    1: "Orléans East-Cumberland",
    2: "Orléans West-Innes",
    3: "Barrhaven West",
    4: "Kanata North",
    5: "West Carleton-March",
    6: "Stittsville",
    7: "Bay",
    8: "College",
    9: "Knoxdale-Merivale",
    10: "Gloucester-Southgate",
    11: "Beacon Hill-Cyrville",
    12: "Rideau-Vanier",
    13: "Rideau-Rockcliffe",
    14: "Somerset",
    15: "Kitchissippi",
    16: "River",
    17: "Capital",
    18: "Alta Vista",
    19: "Orléans South-Navan",
    20: "Osgoode",
    21: "Rideau-Jock",
    22: "Riverside South-Findlay Creek",
    23: "Kanata South",
    24: "Barrhaven East",
}

WARDS_URL = "https://ottawa.ca/en/city-hall/council-committees-and-boards/how-city-government-works/city-wards"


# -----------------------------
# Column handling
# -----------------------------
# Canonical columns we want in the final dataset
CANONICAL = {
    "Ward": ["Ward", "ward", "WARD", "Ward Number", "Ward_Num", "Ward #"],
    "Average Household Income": [
        "Average Household Income",
        "Avg Household Income",
        "Average income",
        "Household Income",
        "Average_Household_Income",
    ],
    "Median Price": [
        "Median Price",
        "Median Home Price",
        "Median House Price",
        "Median Sale Price",
        "Median_Sale_Price",
    ],
    "Price to Income Ratio": [
        "Price to Income Ratio",
        "Price-to-Income Ratio",
        "Price to Income",
        "PTI Ratio",
        "Price_Income_Ratio",
    ],
}

REQUIRED_CANONICAL = {"Ward", "Average Household Income", "Median Price", "Price to Income Ratio"}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Renames columns from common variants to canonical names.
    """
    existing = {c.strip(): c for c in df.columns}
    rename_map = {}

    # Build a lookup of lowercase -> actual column name for robust matching
    lower_actual = {c.lower().strip(): c for c in df.columns}

    for canon, variants in CANONICAL.items():
        for v in variants:
            key = v.lower().strip()
            if key in lower_actual:
                rename_map[lower_actual[key]] = canon
                break

    df = df.rename(columns=rename_map)

    # Also strip whitespace from column names (Tableau exports love random spaces)
    df.columns = [c.strip() for c in df.columns]
    return df


def has_required(df: pd.DataFrame) -> bool:
    cols = set(df.columns)
    return REQUIRED_CANONICAL.issubset(cols)


def find_candidate_csvs(project_dir: Path) -> list[Path]:
    """
    Search likely locations for CSVs:
    - project root
    - project/data
    - project/data/processed
    """
    scan_roots = [
        project_dir,
        project_dir / "data",
        project_dir / "data" / "processed",
    ]

    found = []
    for root in scan_roots:
        if root.exists():
            found.extend(sorted(root.glob("*.csv")))
    # de-dupe while keeping order
    seen = set()
    uniq = []
    for p in found:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def choose_main_dataset(project_dir: Path) -> Path:
    """
    Picks the first CSV that contains (or can be normalized to) the required columns.
    Preference:
      - files with 'tableau' in the name
      - then anything that matches
    """
    csvs = find_candidate_csvs(project_dir)
    if not csvs:
        raise FileNotFoundError(f"No CSV files found under: {project_dir}")

    scored: list[tuple[int, Path]] = []
    for p in csvs:
        try:
            df = pd.read_csv(p, nrows=50)
            df = normalize_columns(df)
            if has_required(df):
                score = 0
                name = p.name.lower()
                if "tableau" in name:
                    score += 10
                if "income" in name and "market" in name:
                    score += 5
                scored.append((score, p))
        except Exception:
            continue

    if not scored:
        # Print a helpful list for humans (begrudgingly)
        print("❌ Found CSVs, but none contain the required columns (even after normalization).")
        print("Required canonical columns:", ", ".join(sorted(REQUIRED_CANONICAL)))
        print("\nCSV files scanned:")
        for p in csvs:
            print(" -", p.relative_to(project_dir))
        raise ValueError("No suitable main Tableau dataset found.")

    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[0][1]


def fetch_ward_lookup() -> pd.DataFrame:
    """
    Tries to fetch ward mapping from Ottawa website. Falls back to hardcoded mapping if it fails.
    """
    try:
        html = requests.get(WARDS_URL, timeout=60).text
        tables = pd.read_html(html)

        best = None
        for t in tables:
            cols = [str(c).lower() for c in t.columns]
            if any("ward" in c and "number" in c for c in cols) and any("ward" in c and "name" in c for c in cols):
                best = t.copy()
                break

        if best is None:
            raise ValueError("Could not find wards table.")

        colmap = {}
        for c in best.columns:
            cl = str(c).lower()
            if "ward" in cl and "number" in cl:
                colmap[c] = "Ward"
            elif "ward" in cl and "name" in cl:
                colmap[c] = "Ward_Name"

        best = best.rename(columns=colmap)[["Ward", "Ward_Name"]].copy()
        best["Ward"] = pd.to_numeric(best["Ward"], errors="coerce").astype("Int64")
        best = best.dropna(subset=["Ward"]).copy()
        best["Ward"] = best["Ward"].astype(int)
        best["Ward_Name"] = best["Ward_Name"].astype(str).str.strip()

        lookup = best.sort_values("Ward").reset_index(drop=True)
        source = "web"
    except Exception as e:
        print("⚠️ Web ward fetch failed, using fallback mapping.")
        print("   Reason:", e)
        lookup = pd.DataFrame({"Ward": list(FALLBACK_WARDS.keys()), "Ward_Name": list(FALLBACK_WARDS.values())})
        lookup = lookup.sort_values("Ward").reset_index(drop=True)
        source = "fallback"

    lookup["Ward_Full"] = "Ward " + lookup["Ward"].astype(str) + " - " + lookup["Ward_Name"]
    print(f"✅ Ward lookup ready (source: {source}), rows: {len(lookup)}")
    return lookup


def main() -> None:
    # Project directory = folder where this script lives
    project_dir = Path(__file__).resolve().parent

    # Output directory
    out_dir = project_dir / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Allow optional input path as an argument
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1]).expanduser().resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"Input CSV not found: {input_path}")
    else:
        input_path = choose_main_dataset(project_dir)

    print(f"📁 Project folder: {project_dir}")
    print(f"📄 Using main dataset: {input_path}")
    print(f"📦 Writing outputs to: {out_dir}")

    # Load + normalize
    df = pd.read_csv(input_path)
    df = normalize_columns(df)

    missing = REQUIRED_CANONICAL - set(df.columns)
    if missing:
        raise ValueError(f"Main dataset is missing required columns after normalization: {sorted(missing)}")

    # Make Ward numeric int
    df["Ward"] = pd.to_numeric(df["Ward"], errors="coerce")
    df = df.dropna(subset=["Ward"]).copy()
    df["Ward"] = df["Ward"].astype(int)

    # Get ward lookup + merge
    lookup = fetch_ward_lookup()
    labeled = df.merge(lookup, on="Ward", how="left")

    # Force Ward_Label to be the full name, so Tableau stops showing Ward 1/2/3
    labeled["Ward_Label"] = labeled["Ward_Full"]

    # Save outputs
    lookup_path = out_dir / "ward_lookup_ottawa.csv"

    # Output labeled dataset named after input file
    labeled_name = input_path.stem + "_labeled.csv"
    labeled_path = out_dir / labeled_name

    lookup.to_csv(lookup_path, index=False)
    labeled.to_csv(labeled_path, index=False)

    print(f"✅ Saved: {lookup_path}")
    print(f"✅ Saved: {labeled_path}")
    print("\nDone. Use Ward_Label or Ward_Full in Tableau for names.")


if __name__ == "__main__":
    main()

