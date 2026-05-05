"""
figure1.py

Python translation of the Stata script `figure1.do`.

What this script does
---------------------
1. Loads the dataset `main_dataset.dta` (or an equivalent file passed as input)
2. Creates a bar chart of:
   - the total number of candidates by year
   - the number of female candidates by year
3. Creates a bar chart of:
   - the number of municipalities by year
4. Exports both figures as PDF files

Why this script exists
----------------------
The original replication package produced Figure 1 in Stata. This Python
version reproduces the same logic using:

- pandas for data manipulation
- matplotlib for plotting
- pyreadstat for loading Stata `.dta` files

Expected input
--------------
The script expects a dataset containing at least the following columns:

For the candidates plot:
- `jahr`   : election year
- `female` : indicator for female candidate

For the municipalities plot:
- `gkz`    : municipality identifier
- `jahr`   : election year

Typical usage
-------------
Run with explicit dataset path:
    python figure1.py /path/to/main_dataset.dta --output-dir Figure1

Dependencies
------------
    pip install pandas matplotlib pyreadstat
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pyreadstat


def load_data(file_path: str | Path) -> pd.DataFrame:
    """
    Load a Stata `.dta` dataset into a pandas DataFrame.

    Parameters
    ----------
    file_path : str | Path
        Path to the input Stata dataset.

    Returns
    -------
    pd.DataFrame
        Loaded dataframe.

    Notes
    -----
    `pyreadstat.read_dta()` returns both:
    - the dataframe
    - metadata

    Only the dataframe is needed here, so the metadata is ignored.
    """
    df, _meta = pyreadstat.read_dta(str(file_path))
    return df


def plot_number_of_candidates(df: pd.DataFrame, output_dir: str | Path) -> Path:
    """
    Reproduce the first bar chart from the original Stata workflow:
    number of candidates and female candidates by year.

    Stata logic being translated
    ----------------------------
    Original Stata-style logic:

        gen temp = 1
        bysort jahr: egen sum_cand = sum(temp)
        gen female_cand = female * temp
        bysort jahr: egen sum_fem_cand = sum(female_cand)
        graph bar sum_cand sum_fem_cand, over(jahr) ...

    Interpretation
    --------------
    - Each row corresponds to one candidate.
    - `temp = 1` allows counting rows by year.
    - `female_cand = female * 1` gives a female-candidate indicator.
    - Summing by year produces:
      - total candidates
      - total female candidates

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    output_dir : str | Path
        Directory where the PDF file should be saved.

    Returns
    -------
    Path
        Path to the saved PDF file.

    Raises
    ------
    ValueError
        If required columns are missing.
    """
    required_cols = {"jahr", "female"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns for candidates plot: {sorted(missing)}")

    # Work on a copy to avoid mutating the original dataframe
    work = df.copy()

    # Equivalent to Stata:
    #   gen temp = 1
    # This creates a column equal to 1 for each row/candidate
    work["temp"] = 1

    # Equivalent to:
    #   gen female_cand = female * temp
    # Since temp = 1, this is just a numeric female indicator
    work["female_cand"] = work["female"] * work["temp"]

    # Equivalent to grouped Stata aggregation by year
    summary = (
        work.groupby("jahr", dropna=False)
        .agg(
            sum_cand=("temp", "sum"),
            sum_fem_cand=("female_cand", "sum"),
        )
        .reset_index()
        .sort_values("jahr")
    )

    # Extract plotting vectors
    years = summary["jahr"].tolist()
    all_candidates = summary["sum_cand"].tolist()
    female_candidates = summary["sum_fem_cand"].tolist()

    # Create side-by-side bars
    x = range(len(years))
    width = 0.38

    fig, ax = plt.subplots(figsize=(10, 6))

    bars1 = ax.bar(
        [i - width / 2 for i in x],
        all_candidates,
        width=width,
        label="All",
    )
    bars2 = ax.bar(
        [i + width / 2 for i in x],
        female_candidates,
        width=width,
        label="Female",
    )

    # Axis formatting
    ax.set_xticks(list(x))
    ax.set_xticklabels(years)
    ax.set_ylabel("Number of candidates")
    ax.legend()

    # Equivalent to Stata's blabel(total):
    # display the bar heights on top of each bar
    for bars in (bars1, bars2):
        ax.bar_label(bars, padding=3, fmt="%.0f")

    fig.tight_layout()

    # Save figure
    output_path = Path(output_dir) / "number_of_candidates.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, format="pdf", bbox_inches="tight")
    plt.close(fig)

    return output_path


def plot_number_of_municipalities(df: pd.DataFrame, output_dir: str | Path) -> Path:
    """
    Reproduce the second bar chart from the original Stata workflow:
    number of municipalities by year.

    Stata logic being translated
    ----------------------------
    Original Stata-style logic:

        bysort gkz jahr: keep if _n == 1
        gen temp = 1
        bysort jahr: egen sum_cand = sum(temp)
        graph bar sum_cand, over(jahr) ...

    Interpretation
    --------------
    The goal is to count the number of distinct municipality-year pairs.

    - `gkz` identifies a municipality
    - `jahr` identifies the year
    - `keep if _n==1` after sorting by `gkz jahr` keeps one row per municipality-year
    - summing `temp = 1` by year counts municipalities

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    output_dir : str | Path
        Directory where the PDF file should be saved.

    Returns
    -------
    Path
        Path to the saved PDF file.

    Raises
    ------
    ValueError
        If required columns are missing.
    """
    required_cols = {"gkz", "jahr"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns for municipalities plot: {sorted(missing)}")

    work = df.copy()

    # Equivalent to:
    #   bysort gkz jahr: keep if _n == 1
    # Keep one observation per municipality and year
    work = (
        work.sort_values(["gkz", "jahr"])
        .drop_duplicates(subset=["gkz", "jahr"], keep="first")
    )

    # Count one municipality-year pair as one unit
    work["temp"] = 1

    # Aggregate by year
    summary = (
        work.groupby("jahr", dropna=False)
        .agg(sum_cand=("temp", "sum"))
        .reset_index()
        .sort_values("jahr")
    )

    years = summary["jahr"].tolist()
    municipalities = summary["sum_cand"].tolist()

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(years, municipalities)

    # Match the original plot labeling style
    ax.set_ylabel("number of municipalities")
    ax.set_yticks(list(range(0, 451, 100)))
    ax.bar_label(bars, padding=3, fmt="%.0f")

    fig.tight_layout()

    output_path = Path(output_dir) / "number_of_municipalities.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, format="pdf", bbox_inches="tight")
    plt.close(fig)

    return output_path


def main() -> None:
    """
    Command-line entry point.

    Workflow
    --------
    1. Parse CLI arguments
    2. Load the dataset
    3. Generate the candidates plot
    4. Generate the municipalities plot
    5. Print the output file locations

    Command-line arguments
    ----------------------
    data_path :
        Path to the dataset file (expected: main_dataset.dta)
    --output-dir :
        Directory where the resulting PDF figures will be written
    """
    parser = argparse.ArgumentParser(
        description="Translate and run the Stata workflow from figure1.do"
    )
    parser.add_argument(
        "data_path",
        help="Path to the input dataset (expected: main_dataset.dta)",
    )
    parser.add_argument(
        "--output-dir",
        default="Figure1",
        help="Directory where PDF figures will be saved (default: Figure1)",
    )
    args = parser.parse_args()

    # Load input data
    df = load_data(args.data_path)

    # Generate both outputs
    out1 = plot_number_of_candidates(df, args.output_dir)
    out2 = plot_number_of_municipalities(df, args.output_dir)

    print(f"Saved: {out1}")
    print(f"Saved: {out2}")


if __name__ == "__main__":
    main()