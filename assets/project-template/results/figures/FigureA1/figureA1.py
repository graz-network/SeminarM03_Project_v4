"""
figureA1.py

Python translation of the Stata script `figureA1.do`.

Original Stata workflow
-----------------------
The original logic reproduced here is:

1. Load `main_dataset.dta`
2. Keep observations such that:
   - `rdd_sample == 1`
   - `female == 1`
3. Run an OLS regression to predict women's rank improvement
4. Keep one observation per election:
   - unique `(gkz, jahr)` pair
5. Compute an RD bandwidth using:
   - dependent variable: predicted rank change
   - running variable: `margin_1`
6. Generate the RD plot
7. Export the figure as PDF

What this script does
---------------------
This Python version reproduces the same workflow using:

- pandas for data handling
- statsmodels for the OLS prediction step
- shared helper functions for:
  - dataset loading
  - bandwidth selection
  - RD plotting

Expected input
--------------
The input dataset must contain at least:

Core filtering / plot variables:
- `rdd_sample`
- `female`
- `gewinn_norm`
- `margin_1`
- `gkz`
- `jahr`

Regressors used to predict rank change:
- `log_bevoelkerung`
- `log_flaeche`
- `log_debt_pc`
- `log_tottaxrev_pc`
- `log_gemeinde_beschaef_pc`
- `log_female_sh_gem_besch`
- `log_tot_beschaeft_pc`
- `log_female_share_totbesch`
- `log_prod_share_tot`
- `log_female_share_prod`

Typical usage
-------------
    python figureA1.py /path/to/main_dataset.dta --output-dir FigureA1

Dependencies
------------
    pip install pandas statsmodels pyreadstat rdrobust matplotlib scipy
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

# Shared project helpers:
# - _load_data loads either .dta or .csv files
# - bandwidth_and_weights estimates the RD bandwidth and creates helper weights
# - rdd_plot generates the RD-style figure
from meco_replication.stata_helpers import _load_data, bandwidth_and_weights, rdd_plot


# ---------------------------------------------------------------------
# Regressors used in the prediction model
# ---------------------------------------------------------------------
# These variables are used to predict `gewinn_norm` before constructing
# the RD plot on predicted values.
REGRESSORS = [
    "log_bevoelkerung",
    "log_flaeche",
    "log_debt_pc",
    "log_tottaxrev_pc",
    "log_gemeinde_beschaef_pc",
    "log_female_sh_gem_besch",
    "log_tot_beschaeft_pc",
    "log_female_share_totbesch",
    "log_prod_share_tot",
    "log_female_share_prod",
]


def build_figure_a1(df: pd.DataFrame, output_path: str | Path) -> None:
    """
    Reproduce the workflow of `figureA1.do`.

    High-level workflow
    -------------------
    1. Restrict the sample to:
       - RD sample (`rdd_sample == 1`)
       - female candidates (`female == 1`)
    2. Drop observations missing any variable needed for:
       - the OLS prediction step
       - the running variable
       - the election identifier
    3. Estimate an OLS model for `gewinn_norm`
    4. Compute predicted rank change
    5. Keep one observation per election `(gkz, jahr)`
    6. Estimate the optimal RD bandwidth on predicted rank change
    7. Generate the RD plot and save it

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    output_path : str | Path
        Full output path where the PDF figure should be saved.

    Returns
    -------
    None

    Notes
    -----
    The figure is saved directly to disk by `rdd_plot`.
    """

    # Work on a copy so the original dataframe remains unchanged
    work = df.copy()

    # -------------------------------------------------------------
    # Sample restriction
    # -------------------------------------------------------------
    # Keep only:
    # - observations belonging to the RD sample
    # - female candidates
    #
    # This matches the original Stata workflow.
    work = work.loc[(work["rdd_sample"] == 1) & (work["female"] == 1)].copy()

    # -------------------------------------------------------------
    # Ensure all variables needed by the OLS step are available
    # -------------------------------------------------------------
    # We need:
    # - the dependent variable (`gewinn_norm`)
    # - the running variable (`margin_1`)
    # - election identifiers (`gkz`, `jahr`)
    # - all OLS regressors
    needed = ["gewinn_norm", "margin_1", "gkz", "jahr"] + REGRESSORS
    work = work.dropna(subset=needed).copy()

    # -------------------------------------------------------------
    # OLS prediction step
    # -------------------------------------------------------------
    # Equivalent idea:
    # estimate a model of normalized winning rank (`gewinn_norm`)
    # on the selected municipality-level covariates, then use the
    # fitted values as `predicted_rank_change`.
    X = sm.add_constant(work[REGRESSORS], has_constant="add")
    y = work["gewinn_norm"]

    ols = sm.OLS(y, X).fit()
    work["predicted_rank_change"] = ols.predict(X)

    # -------------------------------------------------------------
    # Keep one observation per election
    # -------------------------------------------------------------
    # This matches the Stata pattern:
    #   bysort gkz jahr: keep if _n == 1
    #
    # The goal is to retain one row per municipality-year election.
    work = work.sort_values(["gkz", "jahr"]).drop_duplicates(["gkz", "jahr"], keep="first")

    # -------------------------------------------------------------
    # RD bandwidth selection
    # -------------------------------------------------------------
    # The bandwidth is estimated using:
    # - dependent variable: predicted_rank_change
    # - running variable: margin_1
    bw = bandwidth_and_weights(
        df=work,
        depvar="predicted_rank_change",
        var="margin_1",
        bwmethod="CCT",
        kernel="triangular",
        degree=1,
    )

    # -------------------------------------------------------------
    # Output path preparation
    # -------------------------------------------------------------
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # RD plot generation
    # -------------------------------------------------------------
    # The helper `rdd_plot` will:
    # - bin the data
    # - estimate local linear fits on both sides of the cutoff
    # - plot confidence bands
    # - save the final PDF
    rdd_plot(
        df=bw.data,
        outcome="predicted_rank_change",
        running="margin_1",
        xtitle="Female mayoral candidate margin of victory (%)",
        bw=bw.bw_opt,
        includedbw=30,
        title="Predicted rank improvement of women",
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
    2. Load the dataset with the shared loader
    3. Build and save Figure A1

    Command-line arguments
    ----------------------
    data :
        Path to `main_dataset.dta` or a `.csv` equivalent
    --output-dir :
        Directory where `figureA1.pdf` should be written
    """
    parser = argparse.ArgumentParser(description="Translate figureA1.do to Python.")
    parser.add_argument("data", help="Path to main_dataset.dta or .csv")
    parser.add_argument("--output-dir", default="FigureA1", help="Directory for exported figure")
    args = parser.parse_args()

    # Load the dataset from .dta or .csv
    df = _load_data(args.data)

    # Generate and save the figure
    build_figure_a1(df, Path(args.output_dir) / "figureA1.pdf")


if __name__ == "__main__":
    main()