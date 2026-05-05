"""
figureA10.py

Python translation of the Stata script `figureA10.do`.

Original Stata logic
--------------------
The workflow reproduced here is:

1. Load `neighbor_regressions_dataset.dta`
2. Estimate the RD-optimal bandwidth using:
   - dependent variable: `gewinn_neighbor_norm`
   - running variable: `margin_1`
3. Generate the RD plot
4. Export the figure as `FigureA10/figureA10.pdf`

Research interpretation
-----------------------
This figure studies whether women's rank improvement in neighboring
municipalities changes discontinuously around the female mayoral candidate
margin-of-victory cutoff.

The variable `gewinn_neighbor_norm` is interpreted as a normalized outcome
measuring neighboring rank improvement, making this figure the spatial /
neighbor-based counterpart of the main RD outcome figures.

What this script does
---------------------
This Python implementation:

- loads `.dta` or `.csv` data
- estimates the optimal RD bandwidth
- generates an RD-style figure using shared helper functions
- saves the result as a PDF

Why this script exists
----------------------
The original replication package produced Figure A10 in Stata.
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

- `gewinn_neighbor_norm`
- `margin_1`

Typical usage
-------------
    python figureA10.py /path/to/neighbor_regressions_dataset.dta --output-dir FigureA10

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
# Required columns for Figure A10
# ---------------------------------------------------------------------
# The script checks these explicitly before running the workflow.
REQUIRED_COLUMNS = [
    "gewinn_neighbor_norm",
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
    Ensure that the input dataset contains all variables required for Figure A10.

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
    instead of crashing later during bandwidth estimation or plotting.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def build_figure_a10(df: pd.DataFrame, output_dir: str | Path) -> str:
    """
    Reproduce the workflow of `figureA10.do`.

    High-level workflow
    -------------------
    1. Validate required columns
    2. Estimate the RD-optimal bandwidth using:
       - dependent variable: `gewinn_neighbor_norm`
       - running variable: `margin_1`
    3. Generate the RD plot
    4. Save the figure as `figureA10.pdf`

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    output_dir : str | Path
        Directory where `figureA10.pdf` should be saved.

    Returns
    -------
    str
        Full path to the saved output figure.

    Notes
    -----
    Unlike some other figure scripts in the project, this workflow does
    not apply additional sample restrictions in the current implementation.
    It uses the dataset as provided and delegates the econometric work to
    the shared helper functions.
    """
    validate_columns(df)

    # -------------------------------------------------------------
    # Bandwidth selection
    # -------------------------------------------------------------
    # Estimate the optimal RD bandwidth using:
    # - outcome = gewinn_neighbor_norm
    # - running = margin_1
    #
    # This mirrors the RD setup used in the original Stata workflow.
    bw_result = bandwidth_and_weights(
        df=df,
        depvar="gewinn_neighbor_norm",
        var="margin_1",
        bwmethod="CCT",
        kernel="triangular",
        degree=1,
    )

    # -------------------------------------------------------------
    # Output path
    # -------------------------------------------------------------
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "figureA10.pdf")

    # -------------------------------------------------------------
    # RD plot generation
    # -------------------------------------------------------------
    # The shared helper `rdd_plot` handles:
    # - binned means
    # - local linear fits on both sides of the cutoff
    # - confidence bands
    # - PDF export
    rdd_plot(
        df=df,
        outcome="gewinn_neighbor_norm",
        running="margin_1",
        xtitle="Female mayoral candidate margin of victory (%)",
        bw=bw_result.bw_opt,
        includedbw=30,
        title="Rank improvement of women",
        binsize=3,
        yscale=[-5, -2.5, 0, 2.5, 5],
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
    3. Build and save Figure A10
    4. Print the saved file location

    Command-line arguments
    ----------------------
    data_path :
        Path to `neighbor_regressions_dataset.dta` (or CSV equivalent)
    --output-dir :
        Directory where `figureA10.pdf` will be saved
    """
    parser = argparse.ArgumentParser(
        description="Reproduce Figure A10 from the Stata replication file."
    )
    parser.add_argument(
        "data_path",
        help="Path to neighbor_regressions_dataset.dta (or CSV equivalent).",
    )
    parser.add_argument(
        "--output-dir",
        default="FigureA10",
        help="Directory where figureA10.pdf will be saved.",
    )
    args = parser.parse_args()

    df = load_data(args.data_path)
    output_path = build_figure_a10(df, args.output_dir)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()