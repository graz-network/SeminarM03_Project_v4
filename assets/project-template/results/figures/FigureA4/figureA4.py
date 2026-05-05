"""
figureA4.py

Python translation of the Stata script `figureA4.do`.

Original Stata logic
--------------------
This figure reproduces an RD plot using:

- dependent variable: `gewinn_norm`
- running variable: `margin_1`

The output is a regression discontinuity figure showing the relationship
between the female mayoral candidate's margin of victory and rank
improvement of women in the previous election.

What this script does
---------------------
1. Loads the dataset `dataset_with_lagged_rank_improvments.dta`
   (or a CSV equivalent)
2. Estimates the optimal RD bandwidth using:
   - dependent variable: `gewinn_norm`
   - running variable: `margin_1`
3. Builds the RD plot with:
   - binned means
   - local linear fits on both sides of the cutoff
   - confidence bands
4. Saves the figure as `figureA4.pdf`

Why this script exists
----------------------
The original replication package generated Figure A4 in Stata.
This Python version reuses shared helpers so that the plotting logic
remains consistent across all figures in the project.

Shared helper functions used
----------------------------
- `_load_data`:
    Loads `.dta` or `.csv` files
- `bandwidth_and_weights`:
    Estimates the RD bandwidth with `rdrobust`
- `rdd_plot`:
    Generates the final RD-style plot

Expected input
--------------
The input dataset must contain at least:

- `gewinn_norm`
- `margin_1`

Typical usage
-------------
    python figureA4.py /path/to/dataset_with_lagged_rank_improvments.dta --output-dir FigureA4

Dependencies
------------
    pip install pandas pyreadstat rdrobust matplotlib scipy statsmodels
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Shared project helpers:
# - _load_data reads .dta or .csv
# - bandwidth_and_weights estimates the RD bandwidth
# - rdd_plot builds and saves the figure
from meco_replication.stata_helpers import _load_data, bandwidth_and_weights, rdd_plot


# ---------------------------------------------------------------------
# Required variables for Figure A4
# ---------------------------------------------------------------------
# This figure only needs the dependent variable and the running variable.
REQUIRED_COLUMNS = [
    "gewinn_norm",
    "margin_1",
]


def validate_columns(df) -> None:
    """
    Ensure that the input dataset contains all variables needed for Figure A4.

    Parameters
    ----------
    df : pandas.DataFrame
        Input dataframe.

    Raises
    ------
    KeyError
        If one or more required columns are missing.

    Why this matters
    ----------------
    This function makes the script fail early with a clear error message,
    instead of failing later inside the RD helper functions.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def build_figure_a4(df, output_path: str | Path) -> None:
    """
    Reproduce the workflow of `figureA4.do`.

    High-level workflow
    -------------------
    1. Validate that the required variables are present
    2. Estimate the RD optimal bandwidth using:
       - dependent variable: `gewinn_norm`
       - running variable: `margin_1`
    3. Create the RD plot
    4. Save the output figure as PDF

    Parameters
    ----------
    df : pandas.DataFrame
        Input dataframe.
    output_path : str | Path
        Full path where the figure should be saved.

    Returns
    -------
    None

    Notes
    -----
    This figure does not apply an explicit sample restriction in the current
    implementation. It uses the dataset as provided and delegates the
    bandwidth estimation and plotting logic to the shared helper functions.
    """
    # Make sure the expected variables exist
    validate_columns(df)

    # -------------------------------------------------------------
    # Bandwidth selection
    # -------------------------------------------------------------
    # Estimate the optimal bandwidth for the RD plot using:
    # - outcome   = gewinn_norm
    # - running   = margin_1
    #
    # This mirrors the RD setup used in the original Stata workflow.
    bw = bandwidth_and_weights(
        df=df,
        depvar="gewinn_norm",
        var="margin_1",
        bwmethod="CCT",
        kernel="triangular",
        degree=1,
    )

    # -------------------------------------------------------------
    # Output location
    # -------------------------------------------------------------
    # Ensure the output directory exists before saving the figure.
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # RD plot generation
    # -------------------------------------------------------------
    # The helper `rdd_plot` handles:
    # - binning observations
    # - fitting local linear curves on both sides of 0
    # - drawing confidence bands
    # - exporting the final figure
    rdd_plot(
        df=bw.data,
        outcome="gewinn_norm",
        running="margin_1",
        xtitle="Female mayoral candidate margin of victory (%)",
        bw=bw.bw_opt,
        includedbw=30,
        title="Rank improvement of women in previous election",
        binsize=3,
        yscale=[-5, -2.5, 0, 2.5, 5],
        output_path=str(output_path),
    )


def main() -> None:
    """
    Command-line entry point.

    Workflow
    --------
    1. Parse command-line arguments
    2. Load the dataset from `.dta` or `.csv`
    3. Build and save Figure A4

    Command-line arguments
    ----------------------
    data :
        Path to `dataset_with_lagged_rank_improvments.dta` or `.csv`
    --output-dir :
        Directory where `figureA4.pdf` should be written
    """
    parser = argparse.ArgumentParser(description="Translate figureA4.do to Python.")
    parser.add_argument(
        "data",
        help="Path to dataset_with_lagged_rank_improvments.dta or .csv",
    )
    parser.add_argument(
        "--output-dir",
        default="FigureA4",
        help="Directory for exported figure",
    )
    args = parser.parse_args()

    # Load the dataset using the shared project loader
    df = _load_data(args.data)

    # Generate and save the figure
    build_figure_a4(df, Path(args.output_dir) / "figureA4.pdf")


if __name__ == "__main__":
    main()