"""
figureA8_subfigure_a.py

Python translation of the Stata script `figureA8_subfigure_a.do`.

Original Stata logic
--------------------
The workflow reproduced here is:

1. Load `main_dataset.dta`
2. Keep only observations such that:
   - `rdd_sample == 1`
   - `female == 1`
3. Estimate an OLS model:
   - dependent variable: `gewinn_norm`
   - regressors: a set of individual controls
4. Compute fitted values:
   - `predicted_rank_change`
5. Estimate the RD-optimal bandwidth using:
   - dependent variable: `predicted_rank_change`
   - running variable: `margin_1`
6. Generate the RD plot
7. Export the figure as `FigureA8/figureA8_subfigure_a.pdf`

Research interpretation
-----------------------
This figure studies predicted rank improvement of women, where the prediction
is based on a richer covariate set than in Figure A6. Instead of predicting
rank improvement only from list placement, this version uses a vector of
candidate characteristics and occupational controls.

What this script does
---------------------
This Python implementation:

- loads `.dta` or `.csv` data
- applies the same RD-sample and female-candidate restrictions
- estimates a multivariate OLS prediction model
- constructs a predicted outcome
- estimates an RD bandwidth on that predicted outcome
- produces an RD-style figure using the shared plotting helper

Why this script exists
----------------------
The original replication package produced Figure A8 subfigure A in Stata.
This Python version preserves the same empirical logic while reusing the
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

Core filtering / RD variables:
- `rdd_sample`
- `female`
- `gewinn_norm`
- `margin_1`

Control variables:
- `age`
- `non_university_phd`
- `university`
- `phd`
- `employed`
- `selfemployed`
- `student`
- `retired`
- `housewifehusband`
- `architect`
- `businessmanwoman`
- `engineer`
- `lawyer`
- `civil_administration`
- `teacher`

Typical usage
-------------
    python figureA8_subfigure_a.py /path/to/main_dataset.dta --output-dir FigureA8

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
# - rdd_plot builds and saves the RD figure
from meco_replication.stata_helpers import bandwidth_and_weights, rdd_plot


# ---------------------------------------------------------------------
# Control variables used in the OLS prediction model
# ---------------------------------------------------------------------
# These covariates are used to predict normalized rank improvement before
# building the RD plot on the predicted outcome.
CONTROLS = [
    "age",
    "non_university_phd",
    "university",
    "phd",
    "employed",
    "selfemployed",
    "student",
    "retired",
    "housewifehusband",
    "architect",
    "businessmanwoman",
    "engineer",
    "lawyer",
    "civil_administration",
    "teacher",
]


# ---------------------------------------------------------------------
# Required columns for Figure A8 subfigure A
# ---------------------------------------------------------------------
REQUIRED_COLUMNS = [
    "rdd_sample",
    "female",
    "gewinn_norm",
    "margin_1",
    *CONTROLS,
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
    Ensure that the input dataset contains all variables required for Figure A8a.

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
    instead of failing later during the OLS or RD steps.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def build_figure_a8a(df: pd.DataFrame, output_dir: str | Path) -> str:
    """
    Reproduce the workflow of `figureA8_subfigure_a.do`.

    High-level workflow
    -------------------
    1. Validate required columns
    2. Restrict the sample to:
       - `rdd_sample == 1`
       - `female == 1`
    3. Estimate the linear prediction model:
       `gewinn_norm ~ controls`
    4. Compute fitted values:
       `predicted_rank_change`
    5. Estimate the RD-optimal bandwidth using:
       - dependent variable: `predicted_rank_change`
       - running variable: `margin_1`
    6. Generate the RD plot
    7. Save the figure as `figureA8_subfigure_a.pdf`

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    output_dir : str | Path
        Directory where `figureA8_subfigure_a.pdf` should be saved.

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
    #   gewinn_norm ~ controls
    #
    # Then compute fitted values:
    #   predicted_rank_change
    #
    # We first drop rows with missing values in the outcome, running variable,
    # and all controls.
    model_vars = ["gewinn_norm", "margin_1", *CONTROLS]
    model_df = work[model_vars].dropna().copy()

    if model_df.empty:
        raise ValueError("No observations remain after dropping missing model variables.")

    X = sm.add_constant(model_df[CONTROLS], has_constant="add")
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
    output_path = os.path.join(output_dir, "figureA8_subfigure_a.pdf")

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
        title="Predicted rank improvement of women",
        binsize=3,
        yscale=[-3, -2, -1, 0, 1, 2, 3],
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
    3. Build and save Figure A8 subfigure A
    4. Print the saved file location

    Command-line arguments
    ----------------------
    data_path :
        Path to `main_dataset.dta` (or CSV equivalent)
    --output-dir :
        Directory where `figureA8_subfigure_a.pdf` will be saved
    """
    parser = argparse.ArgumentParser(
        description="Reproduce Figure A8 subfigure A from the Stata replication file."
    )
    parser.add_argument(
        "data_path",
        help="Path to main_dataset.dta (or CSV equivalent).",
    )
    parser.add_argument(
        "--output-dir",
        default="FigureA8",
        help="Directory where figureA8_subfigure_a.pdf will be saved.",
    )
    args = parser.parse_args()

    df = load_data(args.data_path)
    output_path = build_figure_a8a(df, args.output_dir)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()