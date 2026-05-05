"""
figureA5_subfigure_a.py

Python translation of the Stata script `figureA5_subfigure_a.do`.

Original Stata logic
--------------------
This subfigure reproduces an RD plot using:

- dependent variable: `gewinn`
- running variable: `margin_1`

on the subsample of:

- `rdd_sample == 1`
- `female == 1`

The output corresponds to subfigure A of Figure A5 and shows the
relationship between the female mayoral candidate's margin of victory
and women's rank improvement.

What this script does
---------------------
1. Loads `main_dataset.dta` (or a CSV equivalent)
2. Restricts the sample to:
   - `rdd_sample == 1`
   - `female == 1`
3. Estimates the RD optimal bandwidth using:
   - dependent variable: `gewinn`
   - running variable: `margin_1`
4. Builds the RD plot with:
   - binned means
   - local linear fits on both sides of the cutoff
   - confidence bands
5. Saves the resulting PDF as `Figure5_subfigure_a.pdf`

Why this script exists
----------------------
The original replication package produced Figure A5 subfigure A in Stata.
This Python version reuses the project's shared helper functions so that
the RD logic remains consistent across all translated figures.

Shared helper functions used
----------------------------
- `_load_data`:
    Loads input data from `.dta` or `.csv`
- `bandwidth_and_weights`:
    Estimates the optimal bandwidth with `rdrobust`
- `rdd_plot`:
    Generates and saves the final RD-style figure

Expected input
--------------
The input dataset must contain at least:

- `rdd_sample`
- `female`
- `gewinn`
- `margin_1`

Typical usage
-------------
    python figureA5_subfigure_a.py /path/to/main_dataset.dta --output-dir FigureA5

Dependencies
------------
    pip install pandas pyreadstat rdrobust matplotlib scipy statsmodels
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Shared helpers used across the project:
# - _load_data reads either .dta or .csv files
# - bandwidth_and_weights estimates the RD bandwidth
# - rdd_plot constructs and saves the RD figure
from meco_replication.stata_helpers import _load_data, bandwidth_and_weights, rdd_plot


# ---------------------------------------------------------------------
# Required columns for Figure A5 subfigure A
# ---------------------------------------------------------------------
# The script will fail early if one of these variables is missing.
REQUIRED_COLUMNS = [
    "rdd_sample",
    "female",
    "gewinn",
    "margin_1",
]


def validate_columns(df) -> None:
    """
    Ensure that all variables required for Figure A5 subfigure A are present.

    Parameters
    ----------
    df : pandas.DataFrame
        Input dataframe.

    Raises
    ------
    KeyError
        If one or more required variables are missing.

    Why this matters
    ----------------
    This provides a clear and early failure message before calling the
    econometric helper functions, which would otherwise fail less transparently.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def build_figure_a5a(df, output_path: str | Path) -> None:
    """
    Reproduce the workflow of `figureA5_subfigure_a.do`.

    High-level workflow
    -------------------
    1. Validate that the expected variables are present
    2. Restrict the sample to:
       - `rdd_sample == 1`
       - `female == 1`
    3. Estimate the RD optimal bandwidth using:
       - dependent variable: `gewinn`
       - running variable: `margin_1`
    4. Generate the RD plot
    5. Save the figure as PDF

    Parameters
    ----------
    df : pandas.DataFrame
        Input dataframe.
    output_path : str | Path
        Full path where the PDF figure should be saved.

    Returns
    -------
    None

    Notes
    -----
    The actual plotting and exporting are delegated to the shared helper
    `rdd_plot`, which ensures consistent RD plotting style across the project.
    """
    # Ensure the required columns are available
    validate_columns(df)

    # -------------------------------------------------------------
    # Sample restriction
    # -------------------------------------------------------------
    # Equivalent to Stata:
    #   keep if rdd_sample == 1
    #   keep if female == 1
    #
    # Interpretation:
    # Keep only observations belonging to the RD sample and corresponding
    # to female candidates.
    work = df.copy()
    work = work.loc[(work["rdd_sample"] == 1) & (work["female"] == 1)].copy()

    if work.empty:
        raise ValueError(
            "No observations remain after filtering rdd_sample == 1 and female == 1."
        )

    # -------------------------------------------------------------
    # Bandwidth selection
    # -------------------------------------------------------------
    # Estimate the optimal RD bandwidth for:
    # - outcome   = gewinn
    # - running   = margin_1
    #
    # This mirrors the bandwidth helper call used in the Stata workflow.
    bw = bandwidth_and_weights(
        df=work,
        depvar="gewinn",
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
    # The shared helper `rdd_plot` handles:
    # - binning observations
    # - estimating local linear fits on both sides of zero
    # - drawing confidence bands
    # - saving the final figure
    rdd_plot(
        df=bw.data,
        outcome="gewinn",
        running="margin_1",
        xtitle="Female mayoral candidate margin of victory (%)",
        bw=bw.bw_opt,
        includedbw=30,
        title="Rank improvement of women",
        binsize=3,
        yscale=[-2, -1, 0, 1, 2],
        output_path=str(output_path),
    )


def main() -> None:
    """
    Command-line entry point.

    Workflow
    --------
    1. Parse command-line arguments
    2. Load the dataset from `.dta` or `.csv`
    3. Generate and save Figure A5 subfigure A

    Command-line arguments
    ----------------------
    data :
        Path to `main_dataset.dta` or an equivalent `.csv`
    --output-dir :
        Directory where the figure should be saved

    Output
    ------
    The file is written as:
        Figure5_subfigure_a.pdf
    """
    parser = argparse.ArgumentParser(
        description="Translate figureA5_subfigure_a.do to Python."
    )
    parser.add_argument(
        "data",
        help="Path to main_dataset.dta or .csv",
    )
    parser.add_argument(
        "--output-dir",
        default="FigureA5",
        help="Directory for exported figure",
    )
    args = parser.parse_args()

    # Load input data using the shared project loader
    df = _load_data(args.data)

    # Generate and save the figure
    build_figure_a5a(df, Path(args.output_dir) / "Figure5_subfigure_a.pdf")


if __name__ == "__main__":
    main()