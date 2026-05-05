"""
figureA7.py

Python translation of the Stata script `figureA7.do`.

Original Stata logic
--------------------
The workflow reproduced in this script is:

1. Load `main_dataset.dta`
2. Keep only observations such that:
   - `rdd_sample == 1`
3. Estimate the RD-optimal bandwidth using:
   - dependent variable: `female`
   - running variable: `margin_1`
4. Generate the RD plot
5. Export the figure as `FigureA7/figureA7.pdf`

Research interpretation
-----------------------
This figure studies whether the probability of a female candidate being
on the ballot changes discontinuously around the female mayoral candidate
margin-of-victory cutoff.

What this script does
---------------------
This Python implementation:

- loads `.dta` or `.csv` data
- applies the same RD-sample restriction as the original Stata script
- estimates the optimal RD bandwidth
- generates an RD-style figure using shared helper functions
- saves the result as a PDF

Why this script exists
----------------------
The original replication package produced Figure A7 in Stata.
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

- `rdd_sample`
- `female`
- `margin_1`

Typical usage
-------------
    python figureA7.py /path/to/main_dataset.dta --output-dir FigureA7

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
# - rdd_plot creates and saves the RD figure
from meco_replication.stata_helpers import bandwidth_and_weights, rdd_plot


# ---------------------------------------------------------------------
# Required columns for Figure A7
# ---------------------------------------------------------------------
# The script checks these explicitly before running the workflow.
REQUIRED_COLUMNS = [
    "rdd_sample",
    "female",
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
    Ensure that the input dataset contains all variables required for Figure A7.

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
    instead of crashing later during the RD bandwidth or plotting steps.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def build_figure_a7(df: pd.DataFrame, output_dir: str | Path) -> str:
    """
    Reproduce the workflow of `figureA7.do`.

    High-level workflow
    -------------------
    1. Validate required columns
    2. Restrict the sample to:
       - `rdd_sample == 1`
    3. Estimate the RD-optimal bandwidth using:
       - dependent variable: `female`
       - running variable: `margin_1`
    4. Generate the RD plot
    5. Save the figure as `figureA7.pdf`

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    output_dir : str | Path
        Directory where `figureA7.pdf` should be saved.

    Returns
    -------
    str
        Full path to the saved output figure.

    Raises
    ------
    ValueError
        If no observations remain after filtering.
    """
    validate_columns(df)

    # -------------------------------------------------------------
    # Sample restriction
    # -------------------------------------------------------------
    # Equivalent to Stata:
    #   keep if rdd_sample == 1
    #
    # Interpretation:
    # Keep only observations belonging to the RD sample.
    work = df.loc[df["rdd_sample"] == 1].copy()

    if work.empty:
        raise ValueError("No observations remain after filtering rdd_sample == 1.")

    # -------------------------------------------------------------
    # Bandwidth selection
    # -------------------------------------------------------------
    # Estimate the optimal RD bandwidth using:
    # - outcome = female
    # - running = margin_1
    #
    # This mirrors the RD setup used in the original Stata workflow.
    bw_result = bandwidth_and_weights(
        df=work,
        depvar="female",
        var="margin_1",
        bwmethod="CCT",
        kernel="triangular",
        degree=1,
    )

    # -------------------------------------------------------------
    # Output path
    # -------------------------------------------------------------
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "figureA7.pdf")

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
        outcome="female",
        running="margin_1",
        xtitle="Female mayoral candidate margin of victory (%)",
        bw=bw_result.bw_opt,
        includedbw=30,
        title="Likelihood of female on the ballot",
        binsize=3,
        yscale=[0.1, 0.2, 0.3, 0.4, 0.5],
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
    3. Build and save Figure A7
    4. Print the saved file location

    Command-line arguments
    ----------------------
    data_path :
        Path to `main_dataset.dta` (or CSV equivalent)
    --output-dir :
        Directory where `figureA7.pdf` will be saved
    """
    parser = argparse.ArgumentParser(
        description="Reproduce Figure A7 from the Stata replication file."
    )
    parser.add_argument(
        "data_path",
        help="Path to main_dataset.dta (or CSV equivalent).",
    )
    parser.add_argument(
        "--output-dir",
        default="FigureA7",
        help="Directory where figureA7.pdf will be saved.",
    )
    args = parser.parse_args()

    df = load_data(args.data_path)
    output_path = build_figure_a7(df, args.output_dir)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()