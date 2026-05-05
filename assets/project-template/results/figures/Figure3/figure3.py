#!/usr/bin/env python3
"""
figure3.py

Python translation of the Stata script `figure3.do`.

Original Stata workflow
-----------------------
    use main_dataset.dta
    keep if rdd_sample == 1
    keep if female == 1
    bandwidth_and_weights, depvar(listenplatz_norm) var(margin_1)
        bwmethod(CCT) kernel(tri) degree(1)
    rdd_plot listenplatz_norm, includedbw(30) control(margin_1) binsize(3)
        bw($bw_opt)
        title("List placement of women")
        xtitle("Female mayoral candidate margin of victory (%)")
        yscale(25(5)50)
    graph export Figure3/figure3.pdf, replace

What this script does
---------------------
1. Loads `main_dataset.dta` (or a CSV equivalent)
2. Restricts the sample to:
   - `rdd_sample == 1`
   - `female == 1`
3. Computes the RD optimal bandwidth using `listenplatz_norm` as the
   dependent variable and `margin_1` as the running variable
4. Builds an RD plot using the shared helper `rdd_plot`
5. Saves the result to `Figure3/figure3.pdf`

Why this script exists
----------------------
The original replication package produced Figure 3 in Stata. This Python
version reproduces the same empirical workflow while reusing the shared
helper module `meco_replication.stata_helpers`, which centralizes:

- bandwidth selection
- triangular-kernel weighting
- RD plotting logic

Expected input
--------------
The input dataset must contain at least the following columns:

- `rdd_sample`
- `female`
- `listenplatz_norm`
- `margin_1`

Typical usage
-------------
    python figure3.py /path/to/main_dataset.dta --output-dir Figure3

Dependencies
------------
    pip install pandas pyreadstat rdrobust matplotlib scipy statsmodels
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyreadstat

# Reuse the merged helper module previously created in this project.
# This keeps the script short and ensures consistency with the rest of
# the replication workflow.
from meco_replication.stata_helpers import bandwidth_and_weights, rdd_plot


# ---------------------------------------------------------------------
# Required variables for Figure 3
# ---------------------------------------------------------------------
# The script will fail early if one of these columns is missing.
REQUIRED_COLUMNS = [
    "rdd_sample",
    "female",
    "listenplatz_norm",
    "margin_1",
]


def load_dataset(path: str | Path) -> pd.DataFrame:
    """
    Load a dataset from `.dta` or `.csv`.

    Parameters
    ----------
    path : str | Path
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
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".dta":
        df, _meta = pyreadstat.read_dta(str(path))
        return df

    if suffix == ".csv":
        return pd.read_csv(path)

    raise ValueError(f"Unsupported file type: {suffix}. Use .dta or .csv")


def validate_columns(df: pd.DataFrame) -> None:
    """
    Ensure that all required variables for Figure 3 are present.

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
    Figure 3 depends on a very specific RD setup. Failing early with a
    clear message is preferable to getting a downstream crash inside
    the helper functions.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def make_figure3(data_path: str | Path, output_dir: str | Path = "Figure3") -> Path:
    """
    Reproduce the Stata workflow of `figure3.do`.

    High-level workflow
    -------------------
    1. Load the dataset
    2. Validate required columns
    3. Restrict the sample to:
       - `rdd_sample == 1`
       - `female == 1`
    4. Estimate the RD optimal bandwidth using:
       - dependent variable: `listenplatz_norm`
       - running variable: `margin_1`
    5. Build the RD plot using the shared helper `rdd_plot`
    6. Save the output PDF in the requested directory

    Parameters
    ----------
    data_path : str | Path
        Path to `main_dataset.dta` or a CSV equivalent.
    output_dir : str | Path, optional
        Directory where `figure3.pdf` should be saved.
        Defaults to `"Figure3"`.

    Returns
    -------
    Path
        Path to the saved PDF file.

    Raises
    ------
    ValueError
        If no observations remain after sample filtering.
    """
    df = load_dataset(data_path)
    validate_columns(df)

    # -------------------------------------------------------------
    # Sample restriction
    # -------------------------------------------------------------
    # Stata:
    #   keep if rdd_sample==1
    #   keep if female==1
    #
    # Interpretation:
    # Keep only observations belonging to the RD sample and corresponding
    # to female candidates.
    df = df.loc[(df["rdd_sample"] == 1) & (df["female"] == 1)].copy()

    if df.empty:
        raise ValueError(
            "No observations remain after filtering rdd_sample == 1 and female == 1."
        )

    # -------------------------------------------------------------
    # Bandwidth selection
    # -------------------------------------------------------------
    # Stata:
    #   bandwidth_and_weights, depvar(listenplatz_norm) var(margin_1)
    #       bwmethod(CCT) kernel(tri) degree(1)
    #
    # Here we use the shared helper that estimates an RD bandwidth with
    # rdrobust and returns the optimal bandwidth among other outputs.
    bw_result = bandwidth_and_weights(
        df=df,
        depvar="listenplatz_norm",
        var="margin_1",
        bwmethod="CCT",
        kernel="triangular",
        degree=1,
    )

    # -------------------------------------------------------------
    # Output location
    # -------------------------------------------------------------
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "figure3.pdf"

    # -------------------------------------------------------------
    # RD plot
    # -------------------------------------------------------------
    # Stata:
    #   rdd_plot listenplatz_norm, includedbw(30) control(margin_1) binsize(3)
    #       bw($bw_opt)
    #       title("List placement of women")
    #       xtitle("Female mayoral candidate margin of victory (%)")
    #       yscale(25(5)50)
    #
    # The helper `rdd_plot` handles:
    # - binned means
    # - local linear fits on both sides of the cutoff
    # - confidence bands
    rdd_plot(
        df=df,
        outcome="listenplatz_norm",
        running="margin_1",
        xtitle="Female mayoral candidate margin of victory (%)",
        bw=bw_result.bw_opt,
        includedbw=30,
        title="List placement of women",
        binsize=3,
        yscale=[25, 30, 35, 40, 45, 50],
        output_path=str(output_path),
    )

    return output_path


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed command-line arguments.

    Arguments
    ---------
    data_path :
        Path to the main dataset file.
    --output-dir :
        Directory where `figure3.pdf` should be written.
    """
    parser = argparse.ArgumentParser(
        description="Reproduce Stata figure3.do in Python."
    )
    parser.add_argument(
        "data_path",
        help="Path to main_dataset.dta (or equivalent CSV).",
    )
    parser.add_argument(
        "--output-dir",
        default="Figure3",
        help="Directory where figure3.pdf will be saved.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Script entry point.

    Workflow
    --------
    1. Parse CLI arguments
    2. Generate Figure 3
    3. Print the saved file location
    """
    args = parse_args()
    output_path = make_figure3(args.data_path, args.output_dir)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()