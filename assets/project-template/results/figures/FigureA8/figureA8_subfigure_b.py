"""
Python translation of the Stata script `figureA8_subfigure_b.do`.

This script reproduces Appendix Figure A8, subfigure b, using the project's
current helper layout.

Why this patched version is needed
----------------------------------
Older project versions imported shared RDD plotting utilities from the legacy
compatibility module `meco_replication.stata_helpers`. Under the newer patching
strategy, figure scripts should import directly from the canonical helper
module:

    meco_replication.stata_helpers

This avoids compatibility issues with stale wrappers and keeps the figure code
aligned with the maintained project structure.

What this script does
---------------------
1. Loads the main dataset from a .dta or .csv file.
2. Restricts the sample to:
   - observations in the RDD sample (`rdd_sample == 1`)
   - male candidates only (`female == 0`)
3. Fits an OLS model of normalized rank change (`gewinn_norm`) on the control
   variables listed below.
4. Uses the fitted values as "predicted rank improvement of men".
5. Computes an RDD bandwidth using the project's helper routine.
6. Produces the RD-style plot and saves it as:
       figureA8_subfigure_b.pdf

Expected input
--------------
The script expects a dataset containing at least the following variables:

Core sample / plotting variables:
- rdd_sample
- female
- gewinn_norm
- margin_1

Control variables:
- age
- non_university_phd
- university
- phd
- employed
- selfemployed
- student
- retired
- housewifehusband
- architect
- businessmanwoman
- engineer
- lawyer
- civil_administration
- teacher

Usage
-----
From the project root:

    python results/figures/FigureA8/figureA8_subfigure_b.py \
        data/raw/main_dataset.dta \
        --output-dir results/figures/FigureA8

Output
------
A single PDF file:

    figureA8_subfigure_b.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

# Import directly from the maintained helper module.
# This is the recommended approach under the patched project structure.
from meco_replication.stata_helpers import bandwidth_and_weights, rdd_plot


# Control variables used to construct the fitted/predicted outcome.
# These match the structure of the original script logic and are used in the
# OLS projection for male candidates.
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


def load_data(data_path: str | Path) -> pd.DataFrame:
    """
    Load a dataset from either Stata (.dta) or CSV format.

    Parameters
    ----------
    data_path:
        Path to the input dataset.

    Returns
    -------
    pandas.DataFrame
        The loaded dataset.

    Raises
    ------
    ValueError
        If the file extension is not supported.
    """
    path = Path(data_path)

    if path.suffix.lower() == ".dta":
        import pyreadstat

        df, _ = pyreadstat.read_dta(str(path))
        return df

    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)

    raise ValueError(f"Unsupported file format: {path.suffix}")


def build_predicted_rank_improvement_for_men(df: pd.DataFrame) -> pd.DataFrame:
    """
    Restrict the sample and construct the predicted outcome used in Figure A8b.

    The logic is:
    - keep only RDD-sample observations,
    - keep only men (`female == 0`),
    - regress normalized rank change on the control set,
    - use fitted values as the predicted rank improvement outcome.

    Parameters
    ----------
    df:
        Full input dataset.

    Returns
    -------
    pandas.DataFrame
        A modeling dataset containing:
        - margin_1
        - predicted_rank_change

    Notes
    -----
    Rows with missing values in any required model variable are dropped before
    estimation.
    """
    work = df.loc[(df["rdd_sample"] == 1) & (df["female"] == 0)].copy()

    model_vars = ["gewinn_norm", "margin_1", *CONTROLS]
    model_df = work[model_vars].dropna().copy()

    # Add an intercept to mirror the usual regression specification.
    X = sm.add_constant(model_df[CONTROLS], has_constant="add")
    y = model_df["gewinn_norm"]

    model = sm.OLS(y, X).fit()
    model_df["predicted_rank_change"] = model.predict(X)

    return model_df


def make_figure_a8b(data_path: str | Path, output_dir: str | Path) -> Path:
    """
    Generate Appendix Figure A8, subfigure b, and save it to disk.

    Parameters
    ----------
    data_path:
        Path to the main dataset.

    output_dir:
        Directory where the PDF should be written.

    Returns
    -------
    pathlib.Path
        Path to the saved PDF file.
    """
    df = load_data(data_path)
    model_df = build_predicted_rank_improvement_for_men(df)

    # Compute the optimal bandwidth on the predicted outcome.
    bw_result = bandwidth_and_weights(
        df=model_df,
        depvar="predicted_rank_change",
        var="margin_1",
        bwmethod="CCT",
        kernel="triangular",
        degree=1,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "figureA8_subfigure_b.pdf"

    # Build the RD-style plot using the project's helper.
    rdd_plot(
        df=model_df,
        outcome="predicted_rank_change",
        running="margin_1",
        xtitle="female mayoral candidate margin of victory (%)",
        bw=bw_result.bw_opt,
        includedbw=30,
        title="Predicted rank improvement of men",
        binsize=3,
        yscale=[-3, -2, -1, 0, 1, 2, 3],
        output_path=str(output_path),
    )

    return output_path


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the figure script.

    Returns
    -------
    argparse.Namespace
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="Reproduce Figure A8 subfigure b from the Stata replication file."
    )
    parser.add_argument(
        "data_path",
        help="Path to main_dataset.dta (or a CSV equivalent).",
    )
    parser.add_argument(
        "--output-dir",
        default="FigureA8",
        help="Directory where figureA8_subfigure_b.pdf will be saved.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Script entry point.
    """
    args = parse_args()
    output_path = make_figure_a8b(args.data_path, args.output_dir)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()