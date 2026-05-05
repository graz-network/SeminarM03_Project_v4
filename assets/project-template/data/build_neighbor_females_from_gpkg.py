#!/usr/bin/env python3

"""
This script builds two output files from geographic boundary data and mayor election data:
https://daten.gdz.bkg.bund.de/produkte/vg/vg250_ebenen_0101/aktuell/vg250_01-01.utm32s.gpkg.ebenen.zip

1) A neighbor table:
   - tells you which municipalities touch each other

2) A "neighbor_females" dataset:
   - for each municipality and each council-election year,
     it counts how many neighboring municipalities had a female mayor

Why this script exists
----------------------
This is designed to work with a research replication setup.

It expects:
- a municipality boundary file (GeoPackage, shapefile, etc.)
- a Stata file with mayor election results

It produces:
- neighbor_pairs.csv
- neighbor_pairs.dta
- neighbor_females.csv
- neighbor_females.dta

Important assumptions
---------------------
- The replication data uses 6-digit municipality codes called GKZ.
- German boundary files often store municipality codes as 8-digit AGS/RS codes.
- For Hessen municipalities, this script converts an 8-digit code to the 6-digit GKZ
  by dropping the first two digits.

Geographic neighbor rule
------------------------
By default, the script uses ROOK contiguity:
- two municipalities are neighbors only if they share a border line
- touching at only one point does NOT count

If you wanted QUEEN contiguity instead:
- point touching would count as neighbors too
- you would change CONTIGUITY = "queen"

Typical example
---------------
python build_neighbor_females_from_gpkg.py \
    --gpkg /path/to/DE_VG250.gpkg \
    --layer VG250_GEM \
    --mayor-data /path/to/mayor_election_data.dta \
    --outdir /path/to/output

To only list the available layers inside a GeoPackage:
python build_neighbor_females_from_gpkg.py \
    --gpkg /path/to/DE_VG250.gpkg \
    --list-layers
    
A simple way to understand the script
-------------------------------------
1-Read municipality boundaries
2-Keep only Hessen municipalities
3-Figure out which municipalities touch each other
4-Read mayor election data
5-For each council year, determine who the current mayor is
6-Count how many neighbors have female mayors
7-Save the result as CSV and Stata files

"""

from __future__ import annotations

# argparse:
#   Reads command-line arguments such as --gpkg or --outdir
import argparse

# bisect:
#   Helps quickly find the latest mayor election year that is less than
#   or equal to a council year
import bisect

# Path:
#   Safer and cleaner way to work with file paths
from pathlib import Path

# Type hints:
#   These help document what kinds of values functions expect and return
from typing import Iterable, Optional

# geopandas:
#   Used for reading and working with geographic boundary files
import geopandas as gpd

# numpy:
#   Used here mainly for np.nan (missing numeric values)
import numpy as np

# pandas:
#   Used for regular table/data work
import pandas as pd

# fiona:
#   Used here to list layers inside a GeoPackage
#   We wrap it in try/except because not every installation has it available separately
try:
    import fiona
except Exception:
    fiona = None


# ============================================================
# User-configurable parameters
# ============================================================

# These are the council-election years used in the project.
# For each municipality, we want to know the mayor in office in these years.
COUNCIL_YEARS = [2001, 2006, 2011, 2016]

# Choose how neighbors are defined.
# "rook"  = must share a border line with positive length
# "queen" = touching at a point is also enough
CONTIGUITY = "rook"

# Prefix used by Hessen in German admin codes.
# Many 8-digit municipality codes in Hessen start with "06".
HESSEN_PREFIX = "06"

# Possible column names that may contain municipality codes in boundary files.
# Different files use different names, so the script tries these possibilities.
MUNICIPALITY_CODE_CANDIDATES = [
    "AGS", "ags", "RS", "rs", "ARS", "ars",
    "SCHLUESSEL", "schluessel", "GEMEINDESCHLUESSEL", "gemeindeschluessel",
    "GKZ", "gkz",
]

# Possible column names that might hold municipality names
NAME_CANDIDATES = ["GEN", "gen", "NAME", "name", "BEZ", "bez"]

# Possible column names that might identify Hessen directly
POSSIBLE_HESSEN_COLS = ["SN_L", "sn_l", "AGS_LAND", "ags_land", "LAND", "land", "NUTS", "nuts"]


# ============================================================
# Helper functions
# ============================================================

def _clean_digits(x: object) -> Optional[str]:
    """
    Turn a value into a digit-only string.

    Example:
    - "06 435 012" -> "06435012"
    - "GKZ=123456" -> "123456"
    - missing value -> None

    Why this is useful:
    Boundary and Stata files often store codes in inconsistent ways
    (numbers, strings, with spaces, punctuation, etc.). This function standardizes them.

    Parameters
    ----------
    x : object
        Any value from a dataframe cell

    Returns
    -------
    Optional[str]
        A string containing only digits, or None if nothing usable exists
    """
    if pd.isna(x):
        return None

    # Keep only digit characters
    s = "".join(ch for ch in str(x) if ch.isdigit())

    # Return None instead of an empty string
    return s or None


def list_layers(path: Path) -> list[str]:
    """
    List all layers inside a GeoPackage file.

    GeoPackages can contain multiple layers (for example states, districts,
    municipalities, etc.), so this is useful when you do not know which one to read.

    Parameters
    ----------
    path : Path
        Path to the GeoPackage file

    Returns
    -------
    list[str]
        List of layer names

    Raises
    ------
    RuntimeError
        If fiona is not available
    """
    if fiona is None:
        raise RuntimeError("fiona is required to list GeoPackage layers. Install it with geopandas.")
    return list(fiona.listlayers(path))


def auto_pick_layer(path: Path) -> Optional[str]:
    """
    Try to automatically choose the municipality layer from a GeoPackage.

    Strategy:
    1) If the file is not a .gpkg, return None
    2) Look for exact common municipality layer names
    3) If that fails, look for names that contain words like "gem" or "gemeinde"
    4) If exactly one good candidate is found, use it
    5) Otherwise return None and let the user choose manually with --layer

    Parameters
    ----------
    path : Path
        Path to the boundary file

    Returns
    -------
    Optional[str]
        Best guess for the municipality layer name, or None if ambiguous
    """
    suffix = path.suffix.lower()
    if suffix != ".gpkg":
        return None

    layers = list_layers(path)
    if not layers:
        return None

    # Common municipality layer names used in some BKG files
    exact_candidates = [
        "VG250_GEM",
        "vg250_gem",
        "gemeinden",
        "Gemeinden",
    ]
    for cand in exact_candidates:
        if cand in layers:
            return cand

    # If exact matching fails, look for likely municipality names
    semantic_hits = []
    for layer in layers:
        low = layer.lower()
        if "gem" in low or "gemeinde" in low or "municip" in low:
            semantic_hits.append(layer)

    # Only auto-pick when there is exactly one reasonable choice
    if len(semantic_hits) == 1:
        return semantic_hits[0]

    return None


def read_boundaries(path: Path, layer: Optional[str]) -> gpd.GeoDataFrame:
    """
    Read a boundary file into a GeoDataFrame.

    If the file is a GeoPackage:
    - use the requested layer, or
    - try to auto-detect one

    If the file is not a GeoPackage:
    - just read it directly

    Parameters
    ----------
    path : Path
        Path to the boundary file
    layer : Optional[str]
        Name of the GeoPackage layer to read, if needed

    Returns
    -------
    gpd.GeoDataFrame
        Geographic table with boundaries

    Raises
    ------
    ValueError
        If the layer cannot be auto-detected for a GeoPackage
    """
    suffix = path.suffix.lower()

    if suffix == ".gpkg":
        # If the user did not specify a layer, try to guess
        if layer is None:
            layer = auto_pick_layer(path)
            if layer is None:
                available = list_layers(path)
                raise ValueError(
                    "Could not auto-detect the municipality layer in the GeoPackage. "
                    f"Available layers: {available}. Please pass --layer explicitly."
                )

        return gpd.read_file(path, layer=layer)

    # For shapefiles and other vector formats
    return gpd.read_file(path)


def _pick_code_column(df: pd.DataFrame) -> str:
    """
    Find the column most likely to contain municipality codes.

    How it works:
    1) First try known/common code column names
    2) If none work, scan all columns and look for one where most values
       look like 6-, 7-, or 8-digit codes

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe read from the boundary file

    Returns
    -------
    str
        The chosen column name

    Raises
    ------
    ValueError
        If no likely code column can be found
    """
    # First try the list of expected code columns
    for col in MUNICIPALITY_CODE_CANDIDATES:
        if col in df.columns:
            cleaned = df[col].map(_clean_digits)
            lengths = cleaned.dropna().str.len().value_counts()

            # We want a column that contains code-like values of at least 6 digits
            if not lengths.empty and lengths.index.max() >= 6:
                return col

    # Fallback: inspect all non-geometry columns
    for col in df.columns:
        if col == "geometry":
            continue

        cleaned = df[col].map(_clean_digits)
        lengths = cleaned.dropna().str.len()

        # If at least 80% of values look like code lengths, accept that column
        if not lengths.empty and lengths.isin([6, 7, 8]).mean() > 0.8:
            return col

    raise ValueError(
        "Could not detect a municipality code column. "
        f"Available columns: {list(df.columns)}"
    )


def _pick_name_column(df: pd.DataFrame) -> Optional[str]:
    """
    Try to find a municipality name column.

    This is optional. The script can still work without municipality names.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    Optional[str]
        Name of the likely municipality name column, or None
    """
    for col in NAME_CANDIDATES:
        if col in df.columns:
            return col
    return None


def filter_to_hessen(gdf: gpd.GeoDataFrame, code_col: str) -> gpd.GeoDataFrame:
    """
    Keep only Hessen municipalities from the geographic boundary data.

    Filtering logic:
    1) Clean the municipality code into digit-only form
    2) Keep only rows with 6-digit or 8-digit municipality-like codes
    3) If a Hessen-specific state column exists, use it
    4) Otherwise fall back to code-based logic:
       - keep 8-digit codes starting with "06"
       - also allow 6-digit project-specific Hessian GKZ codes

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Full geographic boundary dataframe
    code_col : str
        Column containing municipality codes

    Returns
    -------
    gpd.GeoDataFrame
        Hessen-only municipalities

    Raises
    ------
    ValueError
        If no Hessen municipalities remain after filtering
    """
    gdf = gdf.copy()

    # Create a cleaned version of the code
    gdf["code_raw"] = gdf[code_col].map(_clean_digits)

    # Remove rows with missing codes
    gdf = gdf[gdf["code_raw"].notna()].copy()

    # Keep only code lengths that make sense for municipality keys here
    gdf = gdf[gdf["code_raw"].str.len().isin([6, 8])].copy()

    # First try explicit Hessen indicators if such a column exists
    for col in POSSIBLE_HESSEN_COLS:
        if col in gdf.columns:
            vals = gdf[col].astype(str).str.strip().str.lower()

            # Accept common ways Hessen may be represented
            mask = (
                vals.eq("06") |
                vals.eq("6") |
                vals.str.contains("hessen", na=False)
            )

            if mask.any():
                gdf_h = gdf[mask].copy()
                if not gdf_h.empty:
                    return gdf_h

    # Fallback if no direct state indicator is available:
    # - 8-digit German admin codes for Hessen usually start with "06"
    # - 6-digit project codes are also allowed
    gdf_h = gdf[
        gdf["code_raw"].str.startswith(HESSEN_PREFIX) |
        (gdf["code_raw"].str.len() == 6)
    ].copy()

    if gdf_h.empty:
        raise ValueError(
            "No Hessen municipality features found after filtering. "
            "Check the layer choice or adjust the column detection."
        )

    return gdf_h


def prepare_hessen_municipalities(boundary_path: Path, layer: Optional[str]) -> gpd.GeoDataFrame:
    """
    Read the boundary file and prepare a clean municipality dataset for Hessen.

    Steps:
    1) Read the boundary file
    2) Detect the municipality code column
    3) Optionally detect a municipality name column
    4) Filter to Hessen only
    5) Convert codes to the 6-digit GKZ format used in the replication data
    6) Keep only needed columns
    7) Dissolve multipart geometries by municipality code
    8) Fix simple invalid geometries and drop empty ones

    Why dissolve?
    -------------
    Sometimes one municipality appears in multiple geometry pieces.
    Dissolving combines them into one row per municipality.

    Parameters
    ----------
    boundary_path : Path
        Path to the boundary file
    layer : Optional[str]
        GeoPackage layer name, if needed

    Returns
    -------
    gpd.GeoDataFrame
        Cleaned municipality GeoDataFrame with columns including:
        - gkz
        - geometry
        - optionally municipality_name
    """
    gdf = read_boundaries(boundary_path, layer=layer)

    if gdf.empty:
        raise ValueError("The selected boundary layer contains no features.")

    # Find important columns
    code_col = _pick_code_column(gdf)
    name_col = _pick_name_column(gdf)

    # Keep only Hessen municipalities
    gdf = filter_to_hessen(gdf, code_col)

    # Convert 8-digit codes to the 6-digit GKZ used by the project
    # If already 6 digits, keep them as they are
    gdf["gkz"] = gdf["code_raw"].where(
        gdf["code_raw"].str.len() == 6,
        gdf["code_raw"].str[-6:],
    )

    # Ensure all codes have exactly 6 digits
    gdf["gkz"] = gdf["gkz"].str.zfill(6)

    # Keep only the columns we need
    keep_cols = ["gkz", "geometry"]
    if name_col is not None:
        keep_cols.insert(1, name_col)

    gdf = gdf[keep_cols].copy()

    # Rename the name column to something standard
    if name_col is not None:
        gdf = gdf.rename(columns={name_col: "municipality_name"})

    # If municipality names exist, keep the first one during dissolve
    # Otherwise just use "first" as a simple aggregation rule
    aggfunc = {"municipality_name": "first"} if "municipality_name" in gdf.columns else "first"

    # Combine multiple geometry parts for the same municipality into one row
    gdf = gdf.dissolve(by="gkz", aggfunc=aggfunc).reset_index()

    # buffer(0) is a common trick to repair some invalid geometries
    gdf["geometry"] = gdf.geometry.buffer(0)

    # Drop missing or empty shapes
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    return gdf


def build_neighbor_pairs(munis: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Build a neighbor table.

    Output columns:
    - gkz
    - neighbor_gkz

    How it works
    ------------
    1) Make two copies of the municipality table:
       - left table
       - right table
    2) Spatially join them where geometries "touch"
    3) Remove self-matches
    4) If using ROOK contiguity:
       keep only pairs with a shared boundary of positive length
    5) Remove duplicate rows and sort

    Note on direction
    -----------------
    The result is directed, meaning:
    - if A neighbors B, you will typically also see B neighbors A
    - so the table has one row per direction

    Parameters
    ----------
    munis : gpd.GeoDataFrame
        Municipality geometries with gkz codes

    Returns
    -------
    pd.DataFrame
        Neighbor table with columns:
        - gkz
        - neighbor_gkz
    """
    # Left and right copies are needed for a self-join
    left = munis[["gkz", "geometry"]].copy()
    right = munis[["gkz", "geometry"]].copy()

    # Spatial join: find geometries that touch
    joined = gpd.sjoin(left, right, how="inner", predicate="touches")

    # Clean up the joined output column names
    joined = joined.reset_index().rename(columns={"gkz_left": "gkz", "gkz_right": "neighbor_gkz"})

    # Remove rows where a municipality matched itself
    joined = joined[joined["gkz"] != joined["neighbor_gkz"]].copy()

    # If using rook contiguity, touching at only a point should not count.
    # So we compute the length of the shared boundary.
    if CONTIGUITY.lower() == "rook":
        geom_map = munis.set_index("gkz")["geometry"]
        shared_length = []

        for a, b in zip(joined["gkz"], joined["neighbor_gkz"]):
            inter = geom_map[a].boundary.intersection(geom_map[b].boundary)
            shared_length.append(inter.length)

        joined["shared_boundary_length"] = shared_length

        # Keep only pairs sharing a border of positive length
        joined = joined[joined["shared_boundary_length"] > 0].copy()

    # Keep only the two key columns, drop duplicates, sort nicely
    pairs = joined[["gkz", "neighbor_gkz"]].drop_duplicates().sort_values(["gkz", "neighbor_gkz"])

    return pairs.reset_index(drop=True)


def build_current_mayor_panel(mayor_data_path: Path, gkz_universe: Iterable[str]) -> pd.DataFrame:
    """
    Build a municipality-year panel showing whether the current mayor is female.

    Goal
    ----
    For every municipality and every council year in COUNCIL_YEARS,
    determine the gender of the mayor who is in office in that year.

    Rule
    ----
    Use the most recent mayor election year that is less than or equal to the council year.

    Example
    -------
    Suppose a municipality has mayor elections in:
    - 1998 -> male
    - 2004 -> female

    Then:
    - for council year 2001, current mayor = male
    - for council year 2006, current mayor = female

    Required input columns in mayor_election_data.dta
    -----------------------------------------------
    - gkz
    - jahr
    - geschl_first_placed

    Output columns
    --------------
    - gkz
    - jahr
    - winner_female
    - last_mayor_election_year

    Parameters
    ----------
    mayor_data_path : Path
        Path to mayor election Stata file
    gkz_universe : Iterable[str]
        All municipality codes we want represented in the final panel,
        even if some have missing mayor information

    Returns
    -------
    pd.DataFrame
        Municipality-year panel
    """
    # Read the Stata file
    mayor = pd.read_stata(mayor_data_path, convert_categoricals=False)

    # Check that the required columns exist
    required = {"gkz", "jahr", "geschl_first_placed"}
    missing = required.difference(mayor.columns)
    if missing:
        raise ValueError(f"Mayor dataset is missing required columns: {sorted(missing)}")

    mayor = mayor.copy()

    # Standardize municipality code format to 6 digits
    mayor["gkz"] = mayor["gkz"].map(_clean_digits).str[-6:].str.zfill(6)

    # Convert year to numeric integer-like form
    mayor["election_year"] = pd.to_numeric(mayor["jahr"], errors="coerce").astype("Int64")

    # Convert gender code to a 0/1 variable:
    # f -> 1
    # m -> 0
    mayor["winner_female"] = mayor["geschl_first_placed"].astype(str).str.strip().str.lower().map({"f": 1, "m": 0})

    # Drop rows that are missing key information
    mayor = mayor.dropna(subset=["gkz", "election_year", "winner_female"]).copy()

    # Convert nullable integer columns to regular ints now that missing rows are removed
    mayor["election_year"] = mayor["election_year"].astype(int)
    mayor["winner_female"] = mayor["winner_female"].astype(int)

    # Sort by municipality and election year
    mayor = mayor.sort_values(["gkz", "election_year"])

    # If there are duplicate rows for the same municipality-year,
    # keep the last one
    mayor = mayor.drop_duplicates(subset=["gkz", "election_year"], keep="last")

    rows = []

    # Process one municipality at a time
    for gkz, sub in mayor.groupby("gkz", sort=True):
        years = sub["election_year"].tolist()
        winners = sub["winner_female"].tolist()

        # For each target council year, find the latest mayor election up to that year
        for council_year in COUNCIL_YEARS:
            idx = bisect.bisect_right(years, council_year) - 1

            rows.append(
                {
                    "gkz": gkz,
                    "jahr": council_year,
                    "winner_female": winners[idx] if idx >= 0 else pd.NA,
                    "last_mayor_election_year": years[idx] if idx >= 0 else pd.NA,
                }
            )

    panel = pd.DataFrame(rows)

    # Build a complete municipality x year grid
    # so every municipality appears in every council year
    universe = pd.DataFrame({"gkz": sorted(set(gkz_universe))})
    years = pd.DataFrame({"jahr": COUNCIL_YEARS})

    universe["_tmp"] = 1
    years["_tmp"] = 1

    full = universe.merge(years, on="_tmp").drop(columns="_tmp")

    # Merge the mayor info onto the full grid
    panel = full.merge(panel, on=["gkz", "jahr"], how="left")

    return panel.sort_values(["gkz", "jahr"]).reset_index(drop=True)


def build_neighbor_females(pairs: pd.DataFrame, mayor_panel: pd.DataFrame) -> pd.DataFrame:
    """
    Count female-led neighboring municipalities for each municipality-year.

    Example
    -------
    Suppose municipality A has 3 neighbors in 2006:
    - B has female mayor
    - C has male mayor
    - D has female mayor

    Then for A in 2006:
    - sum_female_neighbors = 2
    - total_neighbors = 3
    - female_neighbor_share = 66.67

    Output columns
    --------------
    - gkz
    - jahr
    - sum_female_neighbors
    - total_neighbors
    - known_neighbor_statuses
    - female_neighbor_share

    Parameters
    ----------
    pairs : pd.DataFrame
        Neighbor table with columns gkz and neighbor_gkz
    mayor_panel : pd.DataFrame
        Municipality-year mayor gender panel

    Returns
    -------
    pd.DataFrame
        Aggregated municipality-year table
    """
    # Build a small table of council years
    years = pd.DataFrame({"jahr": COUNCIL_YEARS})

    pairs = pairs.copy()

    # Cross join pairs with years:
    # every neighbor pair appears once for every council year
    pairs["_tmp"] = 1
    years["_tmp"] = 1
    pairs_year = pairs.merge(years, on="_tmp").drop(columns="_tmp")

    # Rename columns in mayor_panel so they can merge on neighbor_gkz
    neighbor_status = mayor_panel.rename(
        columns={
            "gkz": "neighbor_gkz",
            "winner_female": "neighbor_winner_female",
            "last_mayor_election_year": "neighbor_last_mayor_election_year",
        }
    )

    # Attach each neighbor's mayor status for the matching year
    merged = pairs_year.merge(neighbor_status, on=["neighbor_gkz", "jahr"], how="left")

    # Aggregate up to municipality-year level
    out = (
        merged.groupby(["gkz", "jahr"], as_index=False)
        .agg(
            # Sum of neighbors with female mayors
            sum_female_neighbors=("neighbor_winner_female", "sum"),

            # Number of unique neighbors
            total_neighbors=("neighbor_gkz", "nunique"),

            # Number of neighbors where we actually know the gender status
            known_neighbor_statuses=("neighbor_winner_female", lambda s: s.notna().sum()),
        )
        .sort_values(["gkz", "jahr"])
        .reset_index(drop=True)
    )

    # Clean types and fill missing totals
    out["sum_female_neighbors"] = out["sum_female_neighbors"].fillna(0).astype(int)
    out["total_neighbors"] = out["total_neighbors"].astype(int)
    out["known_neighbor_statuses"] = out["known_neighbor_statuses"].astype(int)

    # Create the share of neighbors with female mayors
    # Keep as float so Stata export treats it as numeric
    out["female_neighbor_share"] = np.nan

    mask = out["total_neighbors"] > 0
    out.loc[mask, "female_neighbor_share"] = (
        100.0 * out.loc[mask, "sum_female_neighbors"] / out.loc[mask, "total_neighbors"]
    )

    out["female_neighbor_share"] = pd.to_numeric(out["female_neighbor_share"], errors="coerce").astype(float)

    return out


def compare_with_main_dataset(
    neighbor_females: pd.DataFrame,
    main_dataset_path: Optional[Path],
    mayor_data_path: Path,
) -> None:
    """
    Optional quality check.

    If a main dataset is provided, compare:
    - female_mayor in the main dataset
    with
    - winner_female rebuilt from the mayor election data

    This does not change any output files.
    It only prints an agreement rate to help check whether the reconstruction looks right.

    Parameters
    ----------
    neighbor_females : pd.DataFrame
        Final neighbor_females dataset
    main_dataset_path : Optional[Path]
        Path to main_dataset.dta, or None
    mayor_data_path : Path
        Path to mayor_election_data.dta
    """
    if main_dataset_path is None:
        return

    main = pd.read_stata(main_dataset_path, convert_categoricals=False)

    # Ensure the expected columns exist
    if not {"gkz", "jahr", "female_mayor"}.issubset(main.columns):
        print("[QC] main_dataset missing expected columns; skipping QC.")
        return

    # Keep a unique municipality-year version
    main_u = main[["gkz", "jahr", "female_mayor"]].drop_duplicates().copy()

    # Standardize key columns
    main_u["gkz"] = main_u["gkz"].map(_clean_digits).str[-6:].str.zfill(6)
    main_u["jahr"] = pd.to_numeric(main_u["jahr"], errors="coerce").astype("Int64")

    # Rebuild the mayor panel using the same municipality universe as neighbor_females
    mayor_panel = build_current_mayor_panel(
        mayor_data_path=mayor_data_path,
        gkz_universe=neighbor_females["gkz"].unique(),
    )

    # Compare the two versions
    comp = main_u.merge(mayor_panel, on=["gkz", "jahr"], how="left")
    comp = comp[comp["female_mayor"].notna() & comp["winner_female"].notna()].copy()

    if not comp.empty:
        comp["female_mayor"] = comp["female_mayor"].astype(int)
        accuracy = (comp["female_mayor"] == comp["winner_female"]).mean()
        print(f"[QC] female_mayor agreement with main_dataset: {accuracy:.3f} over {len(comp)} municipality-years")


def _prepare_pairs_for_stata(pairs: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare the neighbor pairs table for Stata export.

    Why this exists:
    Stata export works more reliably when key code columns are explicitly strings.

    Parameters
    ----------
    pairs : pd.DataFrame

    Returns
    -------
    pd.DataFrame
    """
    out = pairs.copy()
    out["gkz"] = out["gkz"].astype(str)
    out["neighbor_gkz"] = out["neighbor_gkz"].astype(str)
    return out


def _prepare_neighbor_females_for_stata(neighbor_females: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare the final neighbor_females table for Stata export.

    This function:
    - keeps only the needed output columns
    - forces columns into clean numeric/string types

    Parameters
    ----------
    neighbor_females : pd.DataFrame

    Returns
    -------
    pd.DataFrame
    """
    out = neighbor_females[[
        "gkz", "jahr", "sum_female_neighbors", "total_neighbors", "female_neighbor_share", "known_neighbor_statuses"
    ]].copy()

    out["gkz"] = out["gkz"].astype(str)
    out["jahr"] = pd.to_numeric(out["jahr"], errors="coerce").astype(int)
    out["sum_female_neighbors"] = pd.to_numeric(out["sum_female_neighbors"], errors="coerce").astype(int)
    out["total_neighbors"] = pd.to_numeric(out["total_neighbors"], errors="coerce").astype(int)
    out["known_neighbor_statuses"] = pd.to_numeric(out["known_neighbor_statuses"], errors="coerce").astype(int)
    out["female_neighbor_share"] = pd.to_numeric(out["female_neighbor_share"], errors="coerce").astype(float)

    return out


def save_outputs(pairs: pd.DataFrame, neighbor_females: pd.DataFrame, outdir: Path) -> None:
    """
    Save the output tables as both CSV and Stata .dta files.

    Files written:
    - neighbor_pairs.csv
    - neighbor_pairs.dta
    - neighbor_females.csv
    - neighbor_females.dta

    Parameters
    ----------
    pairs : pd.DataFrame
        Neighbor pairs table
    neighbor_females : pd.DataFrame
        Final municipality-year output table
    outdir : Path
        Output folder
    """
    outdir.mkdir(parents=True, exist_ok=True)

    pairs_csv = outdir / "neighbor_pairs.csv"
    pairs_dta = outdir / "neighbor_pairs.dta"
    nf_csv = outdir / "neighbor_females.csv"
    nf_dta = outdir / "neighbor_females.dta"

    # Export neighbor pairs
    pairs_export = _prepare_pairs_for_stata(pairs)
    pairs_export.to_csv(pairs_csv, index=False)
    pairs_export.to_stata(pairs_dta, write_index=False, version=118)

    # Export neighbor_females
    nf_export = _prepare_neighbor_females_for_stata(neighbor_females)
    nf_export.to_csv(nf_csv, index=False)
    nf_export.to_stata(nf_dta, write_index=False, version=118)

    print(f"[OK] wrote {pairs_csv}")
    print(f"[OK] wrote {pairs_dta}")
    print(f"[OK] wrote {nf_csv}")
    print(f"[OK] wrote {nf_dta}")


def parse_args() -> argparse.Namespace:
    """
    Read and validate command-line arguments.

    Supported arguments
    -------------------
    --gpkg
        Path to a GeoPackage

    --shapefile
        Path to a shapefile, GeoJSON, or other vector file

    --layer
        Layer name inside the GeoPackage

    --list-layers
        Print all GeoPackage layers and exit

    --mayor-data
        Path to mayor_election_data.dta

    --main-data
        Optional path to main_dataset.dta for quality checks

    --outdir
        Output folder

    Validation rules
    ----------------
    - You must pass exactly one of:
      --gpkg OR --shapefile

    - If you use --list-layers:
      - you must also provide --gpkg
      - mayor-data and outdir are not required

    - Otherwise:
      - --mayor-data and --outdir are required

    Returns
    -------
    argparse.Namespace
        Parsed arguments
    """
    p = argparse.ArgumentParser(
        description="Build neighbor_females.dta from a municipality boundary file and mayor data."
    )

    p.add_argument("--gpkg", default=None, help="Path to a GeoPackage such as DE_VG250.gpkg")
    p.add_argument("--shapefile", default=None, help="Path to municipality shapefile / geojson / other vector file")
    p.add_argument("--layer", default=None, help="Layer name inside the GeoPackage, e.g. VG250_GEM")
    p.add_argument("--list-layers", action="store_true", help="List GeoPackage layers and exit")
    p.add_argument("--mayor-data", default=None, help="Path to mayor_election_data.dta")
    p.add_argument("--main-data", default=None, help="Optional path to main_dataset.dta for quality checks")
    p.add_argument("--outdir", default=None, help="Output directory")

    args = p.parse_args()

    # The user must provide exactly one boundary source
    boundary_sources = [x for x in [args.gpkg, args.shapefile] if x]
    if len(boundary_sources) != 1:
        p.error("Pass exactly one of --gpkg or --shapefile.")

    # Special mode: only list layers, then exit
    if args.list_layers:
        if not args.gpkg:
            p.error("--list-layers requires --gpkg.")
        return args

    # For normal processing mode, these are required
    if args.mayor_data is None or args.outdir is None:
        p.error("--mayor-data and --outdir are required unless you only use --list-layers.")

    return args


# ============================================================
# Main program
# ============================================================
if __name__ == "__main__":
    # Read command-line arguments
    args = parse_args()

    # Decide which boundary file path to use
    boundary_path = Path(args.gpkg) if args.gpkg else Path(args.shapefile)

    # If the user only wants to list GeoPackage layers, do that and stop
    if args.list_layers:
        layers = list_layers(boundary_path)
        print("[INFO] available layers:")
        for layer in layers:
            print(f" - {layer}")
        raise SystemExit(0)

    # Convert path strings into Path objects
    mayor_data_path = Path(args.mayor_data)
    main_data_path = Path(args.main_data) if args.main_data else None
    outdir = Path(args.outdir)

    # --------------------------------------------------------
    # Step 1: Read and prepare municipality boundaries
    # --------------------------------------------------------
    munis = prepare_hessen_municipalities(boundary_path, layer=args.layer)
    print(f"[INFO] municipalities kept: {len(munis)}")

    # --------------------------------------------------------
    # Step 2: Build neighbor pairs from municipality boundaries
    # --------------------------------------------------------
    pairs = build_neighbor_pairs(munis)
    print(f"[INFO] directed neighbor rows: {len(pairs)}")

    # --------------------------------------------------------
    # Step 3: Build a municipality-year panel of current mayors
    # --------------------------------------------------------
    mayor_panel = build_current_mayor_panel(mayor_data_path, munis["gkz"].tolist())

    missing_status = mayor_panel["winner_female"].isna().sum()
    print(f"[INFO] municipality-year rows in mayor panel: {len(mayor_panel)}")
    print(f"[INFO] municipality-year rows with missing current-mayor status: {missing_status}")

    # --------------------------------------------------------
    # Step 4: Count female-led neighbors for each municipality-year
    # --------------------------------------------------------
    neighbor_females = build_neighbor_females(pairs, mayor_panel)
    print(f"[INFO] rows in neighbor_females: {len(neighbor_females)}")
    print("[INFO] first rows:")
    print(neighbor_females.head(10).to_string(index=False))

    # --------------------------------------------------------
    # Step 5: Save outputs
    # --------------------------------------------------------
    save_outputs(pairs, neighbor_females, outdir)

    # --------------------------------------------------------
    # Step 6: Optional quality check
    # --------------------------------------------------------
    compare_with_main_dataset(neighbor_females, main_data_path, mayor_data_path)