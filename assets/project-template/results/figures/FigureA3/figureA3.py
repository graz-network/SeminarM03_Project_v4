"""
figureA3.py

Python translation of the Stata script `figureA3.do`.

Original Stata workflow
-----------------------
The original logic reproduced here is:

1. Load `main_dataset.dta`
2. Keep observations such that:
   - `rdd_sample == 1`
   - `elected == 1`
3. Estimate an RD bandwidth using:
   - dependent variable: `female`
   - running variable: `margin_1`
4. Generate an RD plot of the probability of a female council member
5. Export the figure as PDF

What this script does
---------------------
This Python version reproduces the same workflow using shared helper
functions already defined elsewhere in the project:

- `_load_data` for loading `.dta` or `.csv` files
- `bandwidth_and_weights` for RD bandwidth selection
- `rdd_plot` for building the RD figure

Expected input
--------------
The input dataset must contain at least:

- `rdd_sample`
- `elected`
- `female`
- `margin_1`

Typical usage
-------------
    python figureA3.py /path/to/main_dataset.dta --output-dir FigureA3

Dependencies
------------
    pip install pandas pyreadstat rdrobust matplotlib scipy statsmodels
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Shared project helpers:
# - _load_data loads either .dta or .csv files
# - bandwidth_and_weights estimates the RD bandwidth
# - rdd_plot generates the RD figure
from meco_replication.stata_helpers import _load_data, bandwidth_and_weights, rdd_plot


# ---------------------------------------------------------------------
# Required columns for Figure A3
# ---------------------------------------------------------------------
# The script will check that these variables are present before trying
# to run the RD workflow.
REQUIRED_COLUMNS = [
    "rdd_sample",
    "elected",
    "female",
    "margin_1",
]


def validate_columns(df) -> None:
    """
    Ensure that all required variables are present.

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
    Failing early with a clear error is preferable to getting a less
    informative crash later inside the RD helper functions.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def build_figure_a3(df, output_path: str | Path) -> None:
    """
    Reproduce the workflow of `figureA3.do`.

    High-level workflow
    -------------------
    1. Restrict the sample to:
       - RD sample (`rdd_sample == 1`)
       - elected observations (`elected == 1`)
    2. Estimate the optimal RD bandwidth using:
       - dependent variable: `female`
       - running variable: `margin_1`
    3. Generate the RD plot
    4. Save the resulting figure as a PDF file

    Parameters
    ----------
    df : pandas.DataFrame
        Input dataset.
    output_path : str | Path
        Full path where the exported figure should be saved.

    Returns
    -------
    None

    Notes
    -----
    The figure is saved directly to disk by the shared plotting helper.
    """
    work = df.copy()

    # -------------------------------------------------------------
    # Sample restriction
    # -------------------------------------------------------------
    # Equivalent to the original Stata logic:
    #   keep if rdd_sample == 1
    #   keep if elected == 1
    #
    # Interpretation:
    # Keep only observations belonging to the RD sample and corresponding
    # to elected cases.
    work = work.loc[(work["rdd_sample"] == 1) & (work["elected"] == 1)].copy()

    if work.empty:
        raise ValueError(
            "No observations remain after filtering rdd_sample == 1 and elected == 1."
        )

    # -------------------------------------------------------------
    # Bandwidth selection
    # -------------------------------------------------------------
    # The bandwidth is estimated using:
    # - dependent variable: female
    # - running variable: margin_1
    #
    # This mirrors the original RD setup in the Stata figure script.
    bw = bandwidth_and_weights(
        df=work,
        depvar="female",
        var="margin_1",
        bwmethod="CCT",
        kernel="triangular",
        degree=1,
    )

    # -------------------------------------------------------------
    # Output location
    # -------------------------------------------------------------
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # RD plot generation
    # -------------------------------------------------------------
    # The helper `rdd_plot` will:
    # - bin the data
    # - estimate local linear fits on both sides of the cutoff
    # - draw confidence bands
    # - save the figure
    #
    # Note:
    # The title string below preserves the wording currently used in the
    # source script, including the spelling "Liklihood", so that the
    # Python output stays aligned with the existing implementation.
    rdd_plot(
        df=bw.data,
        outcome="female",
        running="margin_1",
        xtitle="Female mayoral candidate margin of victory (%)",
        bw=bw.bw_opt,
        includedbw=30,
        title="Liklihood of female council member",
        binsize=3,
        yscale=[0.1, 0.2, 0.3, 0.4, 0.5],
        output_path=str(output_path),
    )


def main() -> None:
    """
    Command-line entry point.

    Workflow
    --------
    1. Parse command-line arguments
    2. Load the dataset using the shared loader
    3. Validate the required columns
    4. Build and save Figure A3

    Command-line arguments
    ----------------------
    data :
        Path to `main_dataset.dta` or a `.csv` equivalent
    --output-dir :
        Directory where `figureA3.pdf` should be written
    """
    parser = argparse.ArgumentParser(description="Translate figureA3.do to Python.")
    parser.add_argument("data", help="Path to main_dataset.dta or .csv")
    parser.add_argument("--output-dir", default="FigureA3", help="Directory for exported figure")
    args = parser.parse_args()

    # Load the dataset from .dta or .csv
    df = _load_data(args.data)

    # Check that all required variables are available
    validate_columns(df)

    # Generate and save the figure
    build_figure_a3(df, Path(args.output_dir) / "figureA3.pdf")


if __name__ == "__main__":
    main()