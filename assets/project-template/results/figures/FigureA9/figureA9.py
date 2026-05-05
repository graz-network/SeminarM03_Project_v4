"""
figureA9.py

Python translation of the Stata script `figureA9.do`.

Original Stata logic
--------------------
The workflow reproduced here is:

1. Load `main_dataset.dta`
2. Keep one observation per election:
   - unique `(gkz, jahr)` pair
3. Restrict the sample to:
   - `rdd_sample == 1`
4. Estimate the RD-optimal bandwidth using:
   - dependent variable: `wahlbet`
   - running variable: `margin_1`
5. Generate the RD plot
6. Export the figure as `FigureA9/figureA9.pdf`

Research interpretation
-----------------------
This figure studies whether voter turnout (`wahlbet`) changes
discontinuously around the female mayoral candidate margin-of-victory
cutoff.

Because turnout is an election-level variable, the script first collapses
the candidate-level dataset to one observation per municipality-year
election by keeping one unique `(gkz, jahr)` pair.

What this script does
---------------------
This Python implementation:

- loads `.dta` or `.csv` data
- keeps one row per municipality-year election
- restricts the sample to the RD sample
- estimates the optimal RD bandwidth
- produces an RD-style figure using shared helper functions
- saves the result as a PDF

Why this script exists
----------------------
The original replication package produced Figure A9 in Stata.
This Python version preserves the same empirical workflow while reusing
the shared helper functions already defined for the project.

Shared helper functions used
----------------------------
- `bandwidth_and_weights`:
    estimates the optimal RD bandwidth using `rdrobust`
- `rdd_plot`:
    builds and saves the RD-style plot

Expected input
--------------
The input dataset must contain at least:

- `gkz`
- `jahr`
- `rdd_sample`
- `wahlbet`
- `margin_1`

Typical usage
-------------
    python figureA9.py /path/to/main_dataset.dta --output-dir FigureA9

Dependencies
------------
    pip install pandas pyreadstat rdrobust matplotlib scipy statsmodels
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

# Shared project helpers:
# - bandwidth_and_weights estimates the RD bandwidth
# - rdd_plot builds and saves the RD figure
from meco_replication.stata_helpers import bandwidth_and_weights, rdd_plot


# ---------------------------------------------------------------------
# Required columns for Figure A9
# ---------------------------------------------------------------------
# The script checks these explicitly before running the workflow.
REQUIRED_COLUMNS = [
    "gkz",
    "jahr",
    "rdd_sample",
    "wahlbet",
    "margin_1",
]


def load_data(data_path: str) -> pd.DataFrame:
    """
    Load a dataset from `.dta` or `.csv`.

    Parameters
    ----------
    data_path : str
        Path to the input dataset.

    Returns
    -------
    pd.DataFrame
        Loaded dataframe.

    Raises
    ------
    ValueError
        If the file format is unsupported.

    Notes
    -----
    - `.dta` files are read with `pyreadstat`
    - `.csv` files are read with `pandas.read_csv`
    """
    path = Path(data_path)

    if path.suffix.lower() == ".dta":
        import pyreadstat

        df, _ = pyreadstat.read_dta(str(path))
        return df

    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)

    raise ValueError(f"Unsupported file format: {path.suffix}")


def validate_columns(df: pd.DataFrame) -> None:
    """
    Ensure that the input dataset contains all variables required for Figure A9.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.

    Raises
    ------
    KeyError
        If one or more required columns are missing.

    Why this matters
    ----------------
    This makes the script fail early with a clear and informative error
    instead of failing later during the RD bandwidth or plotting steps.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def build_figure_a9(df: pd.DataFrame, output_dir: str | Path) -> str:
    """
    Reproduce the workflow of `figureA9.do`.

    High-level workflow
    -------------------
    1. Validate required columns
    2. Keep one observation per election:
       - unique `(gkz, jahr)` pair
    3. Restrict the sample to:
       - `rdd_sample == 1`
    4. Estimate the RD-optimal bandwidth using:
       - dependent variable: `wahlbet`
       - running variable: `margin_1`
    5. Generate the RD plot
    6. Save the figure as `figureA9.pdf`

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    output_dir : str | Path
        Directory where `figureA9.pdf` should be saved.

    Returns
    -------
    str
        Full path to the saved output figure.

    Raises
    ------
    ValueError
        If no observations remain after collapsing or filtering.
    """
    validate_columns(df)

    # -------------------------------------------------------------
    # Keep one observation per election
    # -------------------------------------------------------------
    # Equivalent to Stata logic:
    #   bysort gkz jahr: keep if _n == 1
    #
    # Interpretation:
    # Turnout is an election-level outcome, so we keep one unique row
    # per municipality-year election.
    work = df.sort_values(["gkz", "jahr"]).drop_duplicates(
        subset=["gkz", "jahr"],
        keep="first",
    )

    # -------------------------------------------------------------
    # Sample restriction
    # -------------------------------------------------------------
    # Equivalent to:
    #   keep if rdd_sample == 1
    #
    # Interpretation:
    # Keep only elections belonging to the RD sample.
    work = work.loc[work["rdd_sample"] == 1].copy()

    if work.empty:
        raise ValueError("No observations remain after collapsing and filtering rdd_sample == 1.")

    # -------------------------------------------------------------
    # Bandwidth selection
    # -------------------------------------------------------------
    # Estimate the optimal RD bandwidth using:
    # - outcome = wahlbet
    # - running = margin_1
    #
    # This mirrors the RD setup used in the original Stata workflow.
    bw_result = bandwidth_and_weights(
        df=work,
        depvar="wahlbet",
        var="margin_1",
        bwmethod="CCT",
        kernel="triangular",
        degree=1,
    )

    # -------------------------------------------------------------
    # Output path
    # -------------------------------------------------------------
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "figureA9.pdf")

    # -------------------------------------------------------------
    # RD plot generation
    # -------------------------------------------------------------
    # The shared helper `rdd_plot` handles:
    # - binned means
    # - local linear fits on both sides of the cutoff
    # - confidence bands
    # - PDF export
    rdd_plot(
        df=work,
        outcome="wahlbet",
        running="margin_1",
        xtitle="Female mayoral candidate margin of victory (%)",
        bw=bw_result.bw_opt,
        includedbw=30,
        title="Turnout",
        binsize=3,
        yscale=[30, 50, 70, 90],
        output_path=output_path,
    )

    return output_path


def main() -> None:
    """
    Command-line entry point.

    Workflow
    --------
    1. Parse command-line arguments
    2. Load the dataset
    3. Build and save Figure A9
    4. Print the saved file location

    Command-line arguments
    ----------------------
    data_path :
        Path to `main_dataset.dta` (or CSV equivalent)
    --output-dir :
        Directory where `figureA9.pdf` will be saved
    """
    parser = argparse.ArgumentParser(
        description="Reproduce Figure A9 from the Stata replication file."
    )
    parser.add_argument(
        "data_path",
        help="Path to main_dataset.dta (or CSV equivalent).",
    )
    parser.add_argument(
        "--output-dir",
        default="FigureA9",
        help="Directory where figureA9.pdf will be saved.",
    )
    args = parser.parse_args()

    df = load_data(args.data_path)
    output_path = build_figure_a9(df, args.output_dir)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()