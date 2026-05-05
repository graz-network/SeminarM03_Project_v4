"""
figureA2.py

Python translation of the Stata script `figureA2.do`.

Research purpose
----------------
This script reproduces a McCrary-style density plot for the running variable
around the regression discontinuity cutoff at 0.

In the original Stata workflow, this type of figure is typically produced
with `DCdensity`, which is used to visually assess whether the density of
the running variable appears smooth around the cutoff or whether there is
evidence of manipulation / sorting.

What this script does
---------------------
1. Loads the input dataset (typically `mayor_election_data.dta`)
2. Restricts the sample to the RD sample:
   - `rdd_sample == 1`
3. Extracts the running variable (default: `margin_1`)
4. Constructs a histogram-based density estimate
5. Transforms density into log density
6. Fits separate local-linear smooths on the left and right of zero
7. Builds a McCrary-style plot:
   - binned log-density points
   - smooth fit on each side
   - vertical cutoff line at 0
8. Exports the figure to PDF

Why this script exists
----------------------
The original replication package produced a density discontinuity figure
in Stata. This Python implementation recreates the same spirit of the plot
using:

- pandas for data handling
- numpy for histogram construction and linear algebra
- matplotlib for plotting

Expected input
--------------
The input dataset must contain at least:

- `rdd_sample`
- `margin_1`   (or another running variable passed explicitly)

Typical usage
-------------
    python figureA2.py /path/to/mayor_election_data.dta --output-dir FigureA2

Dependencies
------------
    pip install pandas numpy matplotlib pyreadstat
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Shared helper used across the project to load either:
# - .dta files (via pyreadstat)
# - .csv files (via pandas)
from meco_replication.stata_helpers import _load_data


def triangular_kernel(u: np.ndarray) -> np.ndarray:
    """
    Triangular kernel function.

    Definition
    ----------
    K(u) = max(1 - |u|, 0)

    Parameters
    ----------
    u : np.ndarray
        Scaled distances from the local evaluation point.

    Returns
    -------
    np.ndarray
        Kernel weights.

    Why this function matters
    -------------------------
    The local-linear smoothing used in the McCrary-style figure relies on
    kernel weighting. The triangular kernel gives more weight to points
    close to the evaluation point and zero weight to distant observations.
    """
    return np.maximum(1.0 - np.abs(u), 0.0)


def local_linear_fit(x: np.ndarray, y: np.ndarray, grid: np.ndarray, bw: float) -> np.ndarray:
    """
    Compute a local-linear fit over a grid of evaluation points.

    High-level logic
    ----------------
    For each grid point x0:
    1. Compute scaled distances from x0 using bandwidth `bw`
    2. Apply the triangular kernel
    3. Keep observations with positive kernel weight
    4. Run a weighted local linear regression:
           y = a + b * (x - x0)
    5. Store the intercept `a` as the fitted value at x0

    Parameters
    ----------
    x : np.ndarray
        X-values of the observed binned points.
    y : np.ndarray
        Y-values to smooth (here: log densities).
    grid : np.ndarray
        Evaluation points where the smooth curve should be computed.
    bw : float
        Bandwidth used for local smoothing.

    Returns
    -------
    np.ndarray
        Fitted values at each point of the grid.

    Notes
    -----
    This is a lightweight implementation of local-linear smoothing.
    It does not compute confidence intervals; it only returns the fit.
    """
    fits = np.full_like(grid, fill_value=np.nan, dtype=float)

    for i, x0 in enumerate(grid):
        # Distance from current evaluation point, rescaled by bandwidth
        u = (x - x0) / bw

        # Triangular kernel weights
        w = triangular_kernel(u)

        # Only keep observations inside the effective support of the kernel
        keep = w > 0
        if keep.sum() < 3:
            continue

        x_use = x[keep]
        y_use = y[keep]
        w_use = w[keep]

        # Local linear regression design:
        # intercept + centered running variable
        X = np.column_stack([np.ones(len(x_use)), x_use - x0])

        # Weighted least squares using explicit matrix algebra
        XtW = X.T * w_use
        beta = np.linalg.pinv(XtW @ X) @ (XtW @ y_use)

        # The fitted value at x0 is the intercept
        fits[i] = beta[0]

    return fits


def build_mccrary_plot(df: pd.DataFrame, output_path: str | Path, running: str = "margin_1") -> None:
    """
    Build and save a McCrary-style density plot.

    High-level workflow
    -------------------
    1. Restrict the sample to `rdd_sample == 1`
    2. Keep only the running variable
    3. Compute histogram bins and densities
    4. Convert densities to log densities
    5. Split the support left and right of zero
    6. Smooth the log-density separately on each side with local-linear fits
    7. Plot:
       - observed log-density points
       - left fit
       - right fit
       - cutoff line at zero
    8. Save the figure as PDF

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    output_path : str | Path
        Path where the output figure should be saved.
    running : str, optional
        Name of the running variable. Defaults to `"margin_1"`.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        If:
        - too few observations are available
        - support is missing on one side of zero

    Interpretation
    --------------
    A smooth density around zero supports the idea that the running variable
    is not manipulated at the cutoff. A visible jump may indicate sorting
    or manipulation around the threshold.
    """
    work = df.copy()

    # Restrict to the RD sample, as in the original Stata logic
    work = work.loc[work["rdd_sample"] == 1].copy()

    # Keep only the running variable and drop missing values
    work = work[[running]].dropna().copy()

    x = work[running].to_numpy()
    n = len(x)

    if n < 20:
        raise ValueError("Not enough observations to produce a McCrary-style density plot.")

    # -------------------------------------------------------------
    # Data-driven bin width and smoothing bandwidth
    # -------------------------------------------------------------
    # The bin width is based on a robust scale estimate:
    #   scale = min(sd, IQR / 1.349)
    #
    # This is similar in spirit to standard histogram rules.
    sigma = np.nanstd(x, ddof=1)
    iqr = np.subtract(*np.nanpercentile(x, [75, 25]))
    scale = min(sigma, iqr / 1.349) if iqr > 0 else sigma

    # Histogram bin width
    binwidth = max(2.0 * scale * (n ** (-1 / 3)), 0.5)

    # Smoothing bandwidth for the local-linear fit
    bandwidth = max(2.0 * 1.06 * sigma * (n ** (-1 / 5)), binwidth * 2.0)

    # -------------------------------------------------------------
    # Histogram construction
    # -------------------------------------------------------------
    xmin = np.floor(x.min() / binwidth) * binwidth
    xmax = np.ceil(x.max() / binwidth) * binwidth
    edges = np.arange(xmin, xmax + binwidth, binwidth)

    counts, edges = np.histogram(x, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2.0

    # Convert counts into density
    density = counts / (n * binwidth)

    # Build plotting dataframe
    plot_df = pd.DataFrame({
        "x": centers,
        "density": density,
        "count": counts,
    })

    # Ignore empty bins when taking logs
    plot_df = plot_df.loc[plot_df["count"] > 0].copy()
    plot_df["log_density"] = np.log(plot_df["density"])

    # -------------------------------------------------------------
    # Split support around the cutoff
    # -------------------------------------------------------------
    left = plot_df.loc[plot_df["x"] < 0].copy()
    right = plot_df.loc[plot_df["x"] >= 0].copy()

    if left.empty or right.empty:
        raise ValueError("Need support on both sides of zero to reproduce the DCdensity plot.")

    # Prediction grids on both sides of zero
    left_grid = np.linspace(left["x"].min(), min(left["x"].max(), 0.0), 100)
    right_grid = np.linspace(max(right["x"].min(), 0.0), right["x"].max(), 100)

    # Separate smooth fits on each side
    left_fit = local_linear_fit(
        left["x"].to_numpy(),
        left["log_density"].to_numpy(),
        left_grid,
        bandwidth,
    )
    right_fit = local_linear_fit(
        right["x"].to_numpy(),
        right["log_density"].to_numpy(),
        right_grid,
        bandwidth,
    )

    # -------------------------------------------------------------
    # Plotting
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 6))

    # Scatter of observed binned log densities
    ax.scatter(plot_df["x"], plot_df["log_density"], s=32)

    # Smoothed fits left and right of the cutoff
    ax.plot(left_grid, left_fit, linewidth=2)
    ax.plot(right_grid, right_fit, linewidth=2)

    # Vertical cutoff line
    ax.axvline(0.0, linewidth=1)

    # Labels
    ax.set_xlabel("Female mayoral candidate margin of victory (%)")
    ax.set_ylabel("Log density")
    ax.set_title("McCrary density test")

    # Save output
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight", dpi=300)
    plt.close(fig)


def main() -> None:
    """
    Command-line entry point.

    Workflow
    --------
    1. Parse command-line arguments
    2. Load the dataset using the shared project loader
    3. Build the McCrary-style density plot
    4. Save the PDF figure in the requested output directory

    Command-line arguments
    ----------------------
    data :
        Path to `mayor_election_data.dta` (or CSV equivalent)
    --output-dir :
        Directory where `figureA2.pdf` should be written
    """
    parser = argparse.ArgumentParser(description="Translate figureA2.do to Python.")
    parser.add_argument("data", help="Path to mayor_election_data(.dta/.csv)")
    parser.add_argument(
        "--output-dir",
        default="FigureA2",
        help="Directory for exported figure",
    )
    args = parser.parse_args()

    # Load the data from .dta or .csv
    df = _load_data(args.data)

    # Build and save the figure
    build_mccrary_plot(df, Path(args.output_dir) / "figureA2.pdf")


if __name__ == "__main__":
    main()