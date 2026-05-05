"""
figure2.py

Python translation of the Stata script `figure2.do`.

Original Stata workflow
-----------------------
    use main_dataset.dta
    keep if rdd_sample==1
    keep if female==1
    bandwidth_and_weights, depvar(gewinn_norm) var(margin_1) bwmethod(CCT) kernel(tri) degree(1)
    rdd_plot gewinn_norm, includedbw(30) control(margin_1) binsize(3) bw($bw_opt)
        title("Rank improvement of women")
        xtitle("Female mayoral candidate margin of victory (%)")
        yscale(-5(2.5)5)
    graph export Figure2/figure2.pdf, replace

What this script does
---------------------
1. Loads `main_dataset.dta` (or a CSV equivalent)
2. Restricts the sample to:
   - `rdd_sample == 1`
   - `female == 1`
3. Estimates the optimal RD bandwidth using `rdrobust`
4. Builds an RD plot with:
   - binned means
   - local linear fits on both sides of the cutoff
   - pointwise confidence bands
5. Exports the figure to PDF

Why this script exists
----------------------
This file reproduces the same logic as the original Stata workflow but in
standalone Python form, using:

- pandas for data handling
- pyreadstat for reading `.dta` files
- rdrobust for bandwidth selection
- matplotlib for plotting
- scipy for confidence interval calculations

Typical usage
-------------
    python figure2.py /path/to/main_dataset.dta --output-dir Figure2

Dependencies
------------
    pip install pandas matplotlib scipy pyreadstat rdrobust
"""

from __future__ import annotations

import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm

# ---------------------------------------------------------------------
# Optional dataset reader for Stata files
# ---------------------------------------------------------------------
# The script supports `.dta` files via pyreadstat.
try:
    import pyreadstat
except ImportError as exc:
    raise ImportError(
        "pyreadstat is required to read .dta files. Install with: pip install pyreadstat"
    ) from exc

# ---------------------------------------------------------------------
# RD bandwidth estimation dependency
# ---------------------------------------------------------------------
# rdrobust is required to reproduce the bandwidth selection logic of Stata.
try:
    from rdrobust import rdrobust
except ImportError as exc:
    raise ImportError(
        "rdrobust is required for optimal bandwidth selection. Install with: pip install rdrobust"
    ) from exc


@dataclass
class BandwidthResult:
    """
    Minimal structured result for bandwidth estimation.

    Attributes
    ----------
    bw_opt : float
        Optimal bandwidth selected by `rdrobust`.
    """

    bw_opt: float


@dataclass
class RDPlotResult:
    """
    Structured output for the RD plot routine.

    Attributes
    ----------
    figure : plt.Figure
        Matplotlib figure object.
    ax : plt.Axes
        Matplotlib axes object.
    bw : float
        Bandwidth used in the plot.
    used_n : int
        Number of observations used within the plotting window.
    bin_summary : pd.DataFrame
        Binned means used for the scatter layer.
    fit_grid : pd.DataFrame
        Grid of fitted values and confidence intervals.
    """

    figure: plt.Figure
    ax: plt.Axes
    bw: float
    used_n: int
    bin_summary: pd.DataFrame
    fit_grid: pd.DataFrame


def _triangular_kernel(u: np.ndarray) -> np.ndarray:
    """
    Triangular kernel.

    Definition
    ----------
    K(u) = max(1 - |u|, 0)

    Parameters
    ----------
    u : np.ndarray
        Scaled distances from the evaluation point.

    Returns
    -------
    np.ndarray
        Kernel weights.
    """
    return np.clip(1.0 - np.abs(u), 0.0, None)


def _weighted_local_linear(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_eval: np.ndarray,
    bw: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute local-linear fitted values and pointwise standard errors.

    High-level logic
    ----------------
    For each evaluation point x0:
    1. Compute scaled distances from x0 using the bandwidth `bw`
    2. Apply the triangular kernel
    3. Keep only observations with positive weight
    4. Fit a weighted local-linear regression:
           y = a + b * (x - x0)
    5. Store:
       - fitted value at x0 = intercept `a`
       - standard error of `a`

    Parameters
    ----------
    x_train : np.ndarray
        Running variable for the estimation sample.
    y_train : np.ndarray
        Outcome variable for the estimation sample.
    x_eval : np.ndarray
        Grid of x-values where predictions should be computed.
    bw : float
        Bandwidth used for local weighting.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Fitted values and corresponding standard errors.
    """
    fitted = np.full_like(x_eval, np.nan, dtype=float)
    se = np.full_like(x_eval, np.nan, dtype=float)

    for i, x0 in enumerate(x_eval):
        # Rescale distance from evaluation point
        u = (x_train - x0) / bw
        w = _triangular_kernel(u)

        # Keep only observations within the support of the triangular kernel
        mask = w > 0
        if mask.sum() < 3:
            continue

        # Center x around the evaluation point
        xw = x_train[mask] - x0
        yw = y_train[mask]
        ww = w[mask]

        # Local linear regression design matrix
        X = np.column_stack([np.ones(mask.sum()), xw])
        WX = X * ww[:, None]
        XtWX = X.T @ WX

        try:
            XtWX_inv = np.linalg.inv(XtWX)
        except np.linalg.LinAlgError:
            continue

        # Weighted least squares estimator
        beta = XtWX_inv @ (X.T @ (ww * yw))

        # Residual-based variance estimate
        resid = yw - X @ beta
        dof = max(mask.sum() - X.shape[1], 1)
        sigma2 = float((ww * resid**2).sum() / dof)
        vcov = sigma2 * XtWX_inv

        fitted[i] = beta[0]
        se[i] = np.sqrt(max(vcov[0, 0], 0.0))

    return fitted, se


def bandwidth_and_weights(
    df: pd.DataFrame,
    depvar: str,
    var: str,
    bwmethod: str = "CCT",
    kernel: str = "tri",
    degree: int = 1,
) -> BandwidthResult:
    """
    Estimate the RD optimal bandwidth using `rdrobust`.

    This function mirrors the Stata helper call used in `figure2.do`.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    depvar : str
        Dependent variable name.
    var : str
        Running variable name.
    bwmethod : str, optional
        Bandwidth selector method. Defaults to "CCT".
    kernel : str, optional
        Kernel type. Defaults to "tri".
    degree : int, optional
        Polynomial degree. Defaults to 1.

    Returns
    -------
    BandwidthResult
        Object containing the optimal bandwidth.

    Raises
    ------
    RuntimeError
        If a positive bandwidth cannot be extracted from rdrobust output.
    """
    data = df[[depvar, var]].dropna().copy()
    y = data[depvar].to_numpy(dtype=float)
    x = data[var].to_numpy(dtype=float)

    # Map short names used in Stata-style code to Python rdrobust names
    kernel_map = {
        "tri": "triangular",
        "triangular": "triangular",
        "uni": "uniform",
        "uniform": "uniform",
        "epa": "epanechnikov",
        "epanechnikov": "epanechnikov",
    }
    bwmethod_map = {
        "CCT": "mserd",
        "cct": "mserd",
        "mserd": "mserd",
    }

    result = rdrobust(
        y=y,
        x=x,
        c=0,
        p=degree,
        kernel=kernel_map.get(kernel, kernel),
        bwselect=bwmethod_map.get(bwmethod, bwmethod),
    )

    # Different versions of rdrobust may expose bandwidth differently
    bw_candidates: list[float] = []
    for attr in ("bws", "bw"):
        obj = getattr(result, attr, None)
        if obj is None:
            continue
        arr = np.asarray(obj, dtype=float).ravel()
        bw_candidates.extend([float(v) for v in arr if np.isfinite(v) and v > 0])

    if not bw_candidates:
        raise RuntimeError("Unable to extract a positive bandwidth from rdrobust output.")

    return BandwidthResult(bw_opt=bw_candidates[0])


def rdd_plot(
    df: pd.DataFrame,
    outcome: str,
    running: str,
    bw: float,
    includedbw: float,
    binsize: float,
    title: str,
    xtitle: str,
    yscale: Iterable[float] | None = None,
    output_path: str | Path | None = None,
) -> RDPlotResult:
    """
    Create an RD plot matching the helper used in the original Stata code.

    High-level workflow
    -------------------
    1. Keep only the outcome and running variables
    2. Drop missing values
    3. Restrict to observations within `includedbw`
    4. Create bins of size `binsize`
    5. Compute bin-level means
    6. Split sample at the cutoff (0)
    7. Fit local-linear curves left and right of the cutoff
    8. Build confidence intervals
    9. Plot:
       - confidence bands
       - fitted curves
       - binned means
       - cutoff line
    10. Save the figure if requested

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    outcome : str
        Outcome variable name.
    running : str
        Running variable name.
    bw : float
        Bandwidth used for local fitting.
    includedbw : float
        Plotting window around the cutoff.
    binsize : float
        Width of the bins used for the scatter plot.
    title : str
        Plot title.
    xtitle : str
        X-axis label.
    yscale : Iterable[float] | None, optional
        Explicit y-axis tick values.
    output_path : str | Path | None, optional
        Path where the figure should be saved.

    Returns
    -------
    RDPlotResult
        Structured result object containing the figure and plot data.

    Raises
    ------
    ValueError
        If no observations remain inside the plotting window.
    """
    work = df[[outcome, running]].dropna().copy()
    work = work[np.abs(work[running]) < includedbw].copy()
    work = work.sort_values(running)

    if work.empty:
        raise ValueError("No observations remain after applying included bandwidth restriction.")

    # Create bin centers analogous to the Stata helper
    work["bin"] = np.floor(work[running] / binsize) * binsize + binsize / 2.0

    # Bin-level summary used for the scatter plot
    bin_summary = (
        work.groupby("bin", as_index=False)
        .agg(
            mean_outcome=(outcome, "mean"),
            n=(outcome, "size"),
            mean_running=(running, "mean"),
        )
        .sort_values("bin")
    )

    # Split sample at the cutoff
    left = work[work[running] < 0]
    right = work[work[running] >= 0]

    # Prediction grids on both sides
    x_left = (
        np.linspace(max(-includedbw, left[running].min()), 0, 200, endpoint=False)
        if not left.empty else np.array([])
    )
    x_right = (
        np.linspace(0, min(includedbw, right[running].max()), 200)
        if not right.empty else np.array([])
    )

    # Local fits and standard errors
    fit_left, se_left = _weighted_local_linear(
        left[running].to_numpy(dtype=float),
        left[outcome].to_numpy(dtype=float),
        x_left,
        bw,
    ) if not left.empty else (np.array([]), np.array([]))

    fit_right, se_right = _weighted_local_linear(
        right[running].to_numpy(dtype=float),
        right[outcome].to_numpy(dtype=float),
        x_right,
        bw,
    ) if not right.empty else (np.array([]), np.array([]))

    # 95% confidence interval multiplier
    z = norm.ppf(0.975)

    fit_grid = pd.DataFrame({
        "x": np.concatenate([x_left, x_right]),
        "fit": np.concatenate([fit_left, fit_right]),
        "se": np.concatenate([se_left, se_right]),
    })
    fit_grid["ci_low"] = fit_grid["fit"] - z * fit_grid["se"]
    fit_grid["ci_high"] = fit_grid["fit"] + z * fit_grid["se"]

    # -----------------------------------------------------------------
    # Plotting
    # -----------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5.5))

    # Confidence bands + fitted curves
    if len(x_left):
        ax.fill_between(x_left, fit_left - z * se_left, fit_left + z * se_left, alpha=0.2)
        ax.plot(x_left, fit_left, linewidth=2)

    if len(x_right):
        ax.fill_between(x_right, fit_right - z * se_right, fit_right + z * se_right, alpha=0.2)
        ax.plot(x_right, fit_right, linewidth=2)

    # Binned means
    ax.scatter(
        bin_summary["bin"],
        bin_summary["mean_outcome"],
        s=24,
        alpha=0.9,
    )

    # RD cutoff
    ax.axvline(0, linestyle="--", linewidth=1)

    # Titles and labels
    ax.set_title(title)
    ax.set_xlabel(xtitle)
    ax.set_ylabel(outcome)

    # Optional explicit y-axis scale
    if yscale is not None:
        y_ticks = list(yscale)
        if y_ticks:
            ax.set_yticks(y_ticks)
            ax.set_ylim(min(y_ticks), max(y_ticks))

    ax.set_xlim(-includedbw, includedbw)
    fig.tight_layout()

    # Save figure if requested
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, bbox_inches="tight")

    return RDPlotResult(
        figure=fig,
        ax=ax,
        bw=bw,
        used_n=len(work),
        bin_summary=bin_summary,
        fit_grid=fit_grid,
    )


def load_data(data_path: str | Path) -> pd.DataFrame:
    """
    Load Stata or CSV data.

    Parameters
    ----------
    data_path : str | Path
        Path to the input dataset.

    Returns
    -------
    pd.DataFrame
        Loaded dataframe.

    Raises
    ------
    ValueError
        If the file format is unsupported.
    """
    data_path = Path(data_path)
    suffix = data_path.suffix.lower()

    if suffix == ".dta":
        df, _meta = pyreadstat.read_dta(data_path)
        return df

    if suffix == ".csv":
        return pd.read_csv(data_path)

    raise ValueError(f"Unsupported file format: {suffix}. Use .dta or .csv")


def main() -> None:
    """
    Command-line entry point.

    Workflow
    --------
    1. Parse CLI arguments
    2. Load the dataset
    3. Check required columns
    4. Restrict sample to:
       - `rdd_sample == 1`
       - `female == 1`
    5. Estimate optimal bandwidth
    6. Generate the RD plot
    7. Save the PDF figure
    8. Print summary information

    Command-line arguments
    ----------------------
    data :
        Path to `main_dataset.dta` (or CSV equivalent)
    --output-dir :
        Directory for the exported figure
    --output-name :
        File name for the exported figure
    """
    parser = argparse.ArgumentParser(
        description="Convert Stata figure2.do into a standalone Python workflow."
    )
    parser.add_argument(
        "data",
        help="Path to main_dataset.dta (or CSV equivalent).",
    )
    parser.add_argument(
        "--output-dir",
        default="Figure2",
        help="Directory for exported figure. Default: Figure2",
    )
    parser.add_argument(
        "--output-name",
        default="figure2.pdf",
        help="Exported figure filename. Default: figure2.pdf",
    )
    args = parser.parse_args()

    df = load_data(args.data)

    required = ["rdd_sample", "female", "gewinn_norm", "margin_1"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

    # Equivalent to Stata:
    #   keep if rdd_sample==1
    #   keep if female==1
    filtered = df.loc[(df["rdd_sample"] == 1) & (df["female"] == 1)].copy()
    if filtered.empty:
        raise ValueError("No rows remain after filtering rdd_sample==1 and female==1.")

    # Bandwidth selection
    bw_result = bandwidth_and_weights(
        df=filtered,
        depvar="gewinn_norm",
        var="margin_1",
        bwmethod="CCT",
        kernel="tri",
        degree=1,
    )

    # Output path
    output_path = Path(args.output_dir) / args.output_name

    # Plot generation
    result = rdd_plot(
        df=filtered,
        outcome="gewinn_norm",
        running="margin_1",
        bw=bw_result.bw_opt,
        includedbw=30,
        binsize=3,
        title="Rank improvement of women",
        xtitle="Female mayoral candidate margin of victory (%)",
        yscale=np.arange(-5, 5.01, 2.5),
        output_path=output_path,
    )

    print(f"Saved: {output_path}")
    print(f"Optimal bandwidth: {bw_result.bw_opt:.6f}")
    print(f"Observations used in plot window: {result.used_n}")


if __name__ == "__main__":
    main()