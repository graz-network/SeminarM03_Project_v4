"""
figureA6.py

Python translation of the Stata script `figureA6.do`.

Original Stata logic
--------------------
The workflow reproduced in this script is:

1. Load `main_dataset.dta`
2. Keep only observations such that:
   - `rdd_sample == 1`
   - `female == 1`
3. Estimate a linear model:
   - dependent variable: `gewinn_norm`
   - regressor: `listenplatz_norm`
4. Compute fitted values:
   - `predicted_rank_change`
5. Estimate the RD-optimal bandwidth using:
   - dependent variable: `predicted_rank_change`
   - running variable: `margin_1`
6. Generate the RD plot
7. Export the figure as `FigureA6/figureA6.pdf`

Research interpretation
-----------------------
The figure studies whether women's rank improvement can be predicted from
their list placement, and then examines how this predicted rank improvement
behaves around the female mayoral candidate margin-of-victory cutoff.

What this script does
---------------------
This Python implementation:

- loads `.dta` or `.csv` data
- applies the same sample restrictions as the original Stata script
- estimates a simple OLS prediction model
- constructs a predicted outcome
- computes an RD bandwidth
- produces an RD-style figure using the shared plotting helper

Why this script exists
----------------------
The original replication package produced Figure A6 in Stata.
This Python version keeps the same empirical logic while reusing the
shared helper functions already defined for the project.

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
- `gewinn_norm`
- `listenplatz_norm`
- `margin_1`

Typical usage
-------------
    python figureA6.py /path/to/main_dataset.dta --output-dir FigureA6

Dependencies
------------
    pip install pandas pyreadstat statsmodels rdrobust matplotlib scipy
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

# Shared project helpers:
# - bandwidth_and_weights estimates the RD bandwidth
# - rdd_plot creates and saves the RD figure
from meco_replication.stata_helpers import bandwidth_and_weights, rdd_plot


# ---------------------------------------------------------------------
# Required columns for Figure A6
# ---------------------------------------------------------------------
# The script checks these explicitly before running the workflow.
REQUIRED_COLUMNS = [
    "rdd_sample",
    "female",
    "gewinn_norm",
    "listenplatz_norm",
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
    Ensure that the input dataset contains all variables required for Figure A6.

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
    instead of crashing later during the regression or RD steps.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def build_figure_a6(df: pd.DataFrame, output_dir: str | Path) -> str:
    """
    Reproduce the workflow of `figureA6.do`.

    High-level workflow
    -------------------
    1. Validate required columns
    2. Restrict the sample to:
       - `rdd_sample == 1`
       - `female == 1`
    3. Estimate the linear model:
       `gewinn_norm ~ listenplatz_norm`
    4. Predict fitted values:
       `predicted_rank_change`
    5. Estimate the RD-optimal bandwidth using:
       - dependent variable: `predicted_rank_change`
       - running variable: `margin_1`
    6. Generate the RD plot
    7. Save the figure as `figureA6.pdf`

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    output_dir : str | Path
        Directory where `figureA6.pdf` should be saved.

    Returns
    -------
    str
        Full path to the saved output figure.

    Raises
    ------
    ValueError
        If no observations remain after filtering or model preparation.
    """
    validate_columns(df)

    # -------------------------------------------------------------
    # Sample restriction
    # -------------------------------------------------------------
    # Equivalent to Stata:
    #   keep if rdd_sample == 1
    #   keep if female == 1
    #
    # Interpretation:
    # Keep only women in the RD sample.
    work = df.loc[(df["rdd_sample"] == 1) & (df["female"] == 1)].copy()

    if work.empty:
        raise ValueError(
            "No observations remain after filtering rdd_sample == 1 and female == 1."
        )

    # -------------------------------------------------------------
    # Prediction model
    # -------------------------------------------------------------
    # Estimate:
    #   gewinn_norm ~ listenplatz_norm
    #
    # Then compute fitted values and store them as:
    #   predicted_rank_change
    #
    # We drop rows with missing values in the model variables first.
    model_df = work[["gewinn_norm", "listenplatz_norm", "margin_1"]].dropna().copy()

    if model_df.empty:
        raise ValueError("No observations remain after dropping missing model variables.")

    X = sm.add_constant(model_df[["listenplatz_norm"]], has_constant="add")
    model = sm.OLS(model_df["gewinn_norm"], X).fit()
    model_df["predicted_rank_change"] = model.predict(X)

    # -------------------------------------------------------------
    # RD bandwidth selection
    # -------------------------------------------------------------
    # Estimate the optimal RD bandwidth using:
    # - outcome = predicted_rank_change
    # - running = margin_1
    bw_result = bandwidth_and_weights(
        df=model_df,
        depvar="predicted_rank_change",
        var="margin_1",
        bwmethod="CCT",
        kernel="triangular",
        degree=1,
    )

    # -------------------------------------------------------------
    # Output path
    # -------------------------------------------------------------
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "figureA6.pdf")

    # -------------------------------------------------------------
    # RD plot generation
    # -------------------------------------------------------------
    # The shared helper `rdd_plot` handles:
    # - binned means
    # - local linear fits on both sides of the cutoff
    # - confidence bands
    # - PDF export
    rdd_plot(
        df=model_df,
        outcome="predicted_rank_change",
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
    3. Build and save Figure A6
    4. Print the saved file location

    Command-line arguments
    ----------------------
    data_path :
        Path to `main_dataset.dta` (or CSV equivalent)
    --output-dir :
        Directory where `figureA6.pdf` will be saved
    """
    parser = argparse.ArgumentParser(
        description="Reproduce Figure A6 from the Stata replication file."
    )
    parser.add_argument(
        "data_path",
        help="Path to main_dataset.dta (or CSV equivalent).",
    )
    parser.add_argument(
        "--output-dir",
        default="FigureA6",
        help="Directory where figureA6.pdf will be saved.",
    )
    args = parser.parse_args()

    df = load_data(args.data_path)
    output_path = build_figure_a6(df, args.output_dir)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()