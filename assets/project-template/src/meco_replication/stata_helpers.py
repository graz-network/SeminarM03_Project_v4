"""
stata_helpers.py

stata_helpers.py est le module central qui traduit en Python plusieurs utilitaires Stata clés du projet, en combinant calcul de bandes passantes RD, tests t formatés à la Stata, graphiques RD, et une interface CLI de démonstration. 

Unified Python module regrouping three Stata-to-Python translations:

- bandwidth_and_weights   (from bandwidth_and_weights.ado)
- post_ttest             (from post_ttest.ado)
- rdd_plot               (from rdd_plot.ado)

This module is designed to serve two roles:

1. **Importable helper library**
   It provides reusable econometric and plotting utilities for the rest
   of the replication project.

2. **Standalone executable script**
   It also exposes a small command-line interface so it can be used
   independently for quick tests, demonstrations, and debugging.

----------------------------------------------------------------------
Why this module exists
----------------------------------------------------------------------

The original replication package relied on several Stata `.ado` helper
programs. In a Python-first reorganization of the project, it is better
to centralize their functionality in a single reusable module rather
than duplicate code across many table and figure scripts.

This file therefore acts as a shared "toolbox" for:

- regression discontinuity bandwidth calculations
- post-estimation t-test style summaries
- RD plots with binned means and local linear fits

----------------------------------------------------------------------
Main sections
----------------------------------------------------------------------

1. Bandwidth and weight construction
   - Computes optimal bandwidths using `rdrobust`
   - Builds triangular kernel weights for:
       * optimal bandwidth
       * half bandwidth
       * double bandwidth

2. Post t-test summaries
   - Reconstructs matrix-style outputs similar to Stata's `post_ttest`
   - Supports both raw sample inputs and pre-computed summary statistics

3. RD plotting
   - Creates RD plots with:
       * binned sample means
       * local linear fits
       * confidence bands

4. CLI / demonstration interface
   - Allows quick command-line use for testing the helper logic

----------------------------------------------------------------------
Dependencies
----------------------------------------------------------------------

Required:
    pip install pandas numpy scipy statsmodels matplotlib rdrobust

Optional for reading Stata datasets:
    pip install pyreadstat
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

import argparse
import math
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

# ---------------------------------------------------------------------
# Optional third-party dependency: rdrobust
# ---------------------------------------------------------------------
# This package is required for the bandwidth calculation helper.
# We fail early with a clear message if the package is missing.
try:
    from rdrobust import rdrobust
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'rdrobust' package is required. Install it with: pip install rdrobust"
    ) from exc


# =============================================================================
# 1) bandwidth_and_weights.ado -> Python
# =============================================================================

@dataclass
class BandwidthWeightsResult:
    """
    Structured return object for `bandwidth_and_weights()`.

    Attributes
    ----------
    data : pd.DataFrame
        Original dataframe enriched with temporary variables and
        triangular-kernel weights.
    bw_opt : float
        Optimal bandwidth extracted from the rdrobust result.
    bw_half : float
        Half of the optimal bandwidth.
    bw_double : float
        Double the optimal bandwidth.
    rdrobust_result : Any
        Raw result object returned by `rdrobust`.
    """

    data: pd.DataFrame
    bw_opt: float
    bw_half: float
    bw_double: float
    rdrobust_result: Any


def _map_bwselect(name: str) -> str:
    """
    Map legacy Stata/rdrobust bandwidth aliases to the values expected
    by Python `rdrobust`.

    Why this function exists
    ------------------------
    The original Stata code may refer to bandwidth selectors with
    historical names such as `CCT` or `IK`. The Python `rdrobust`
    implementation uses modern selector names such as `mserd` or
    `msetwo`.

    This helper preserves conceptual continuity between the Stata
    replication package and the Python translation.

    Parameters
    ----------
    name : str
        Bandwidth selector name as used in older code or configuration.

    Returns
    -------
    str
        Selector name compatible with Python `rdrobust`.
    """
    key = str(name).strip().lower()
    mapping = {
        "cct": "mserd",
        "mserd": "mserd",
        "cerrd": "cerrd",
        "ik": "msetwo",
        "msetwo": "msetwo",
        "msesum": "msesum",
        "msecomb1": "msecomb1",
        "msecomb2": "msecomb2",
        "certwo": "certwo",
        "cersum": "cersum",
        "cercomb1": "cercomb1",
        "cercomb2": "cercomb2",
    }
    return mapping.get(key, key)


def _extract_bandwidth(result: Any) -> float:
    """
    Extract the main bandwidth from a `rdrobust` result object.

    Why this function exists
    ------------------------
    Different versions of `rdrobust` may expose bandwidth information
    using different attribute names or shapes. This helper tries several
    plausible locations and formats to make the code more robust.

    Search strategy
    ---------------
    1. Check common attributes such as:
       - `bws`
       - `bw`
       - `h`
    2. If needed, inspect the object's internal `__dict__`
       for anything that looks like a bandwidth field.

    Parameters
    ----------
    result : Any
        Object returned by `rdrobust`.

    Returns
    -------
    float
        Extracted optimal bandwidth.

    Raises
    ------
    ValueError
        If no usable bandwidth can be extracted.
    """
    candidate_attrs = ["bws", "bw", "h"]

    for attr in candidate_attrs:
        if hasattr(result, attr):
            value = getattr(result, attr)

            # Scalar case
            if np.isscalar(value):
                return float(value)

            # Array-like case
            try:
                arr = np.asarray(value, dtype=float).ravel()
                if arr.size > 0 and np.isfinite(arr[0]):
                    return float(arr[0])
            except Exception:
                pass

    # Fallback: inspect the object's attribute dictionary
    if hasattr(result, "__dict__"):
        for key, value in result.__dict__.items():
            if "bw" in key.lower() or key.lower() == "h":
                try:
                    if np.isscalar(value):
                        return float(value)
                    arr = np.asarray(value, dtype=float).ravel()
                    if arr.size > 0 and np.isfinite(arr[0]):
                        return float(arr[0])
                except Exception:
                    continue

    raise ValueError(
        "Could not extract the optimal bandwidth from the rdrobust result. "
        "Inspect the returned object structure for your installed rdrobust version."
    )


def _triangular_weights(running: pd.Series, bandwidth: float, prefix: str) -> pd.DataFrame:
    """
    Construct triangular-kernel weights and related temporary variables.

    Mathematical logic
    ------------------
    For each observation with running variable x and bandwidth h:

        scaled = x / h
        indicator = 1(|scaled| <= 1)
        temp2 = 1 - |scaled|
        weight = temp2 * indicator

    This reproduces the triangular-kernel structure used in many
    regression discontinuity procedures and mirrors the temporary
    variables typically created in Stata helper code.

    Parameters
    ----------
    running : pd.Series
        Running (forcing) variable.
    bandwidth : float
        Bandwidth used to rescale the running variable.
    prefix : str
        Suffix/prefix marker used to distinguish columns corresponding
        to different bandwidth variants (optimal, half, double).

    Returns
    -------
    pd.DataFrame
        DataFrame with four columns:
        - temp1{prefix}
        - ind{prefix}
        - temp2{prefix}
        - weight{prefix}
    """
    scaled = running / bandwidth
    indicator = (scaled.abs() <= 1).astype(int)
    temp2 = 1 - scaled.abs()
    weight = temp2 * indicator

    return pd.DataFrame(
        {
            f"temp1{prefix}": scaled,
            f"ind{prefix}": indicator,
            f"temp2{prefix}": temp2,
            f"weight{prefix}": weight,
        }
    )


def bandwidth_and_weights(
    df: pd.DataFrame,
    depvar: str,
    var: str,
    bwmethod: str,
    kernel: str,
    degree: int,
    subset: Optional[pd.Series] = None,
) -> BandwidthWeightsResult:
    """
    Python equivalent of the Stata program `bandwidth_and_weights`.

    What this function does
    -----------------------
    1. Takes a dataframe and selects observations with non-missing values
       for the dependent variable and running variable.
    2. Optionally applies a user-provided subset mask.
    3. Calls `rdrobust` to estimate the optimal bandwidth.
    4. Builds triangular-kernel weights for:
       - the optimal bandwidth
       - half the bandwidth
       - double the bandwidth
    5. Returns the enriched dataframe and the bandwidth summary.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    depvar : str
        Name of the dependent variable.
    var : str
        Name of the running variable.
    bwmethod : str
        Bandwidth selector name.
    kernel : str
        Kernel specification passed to `rdrobust`.
    degree : int
        Polynomial degree passed to `rdrobust`.
    subset : Optional[pd.Series], optional
        Boolean mask used to restrict the estimation sample before
        bandwidth selection.

    Returns
    -------
    BandwidthWeightsResult
        Structured object containing the enriched data and bandwidths.

    Raises
    ------
    ValueError
        If no valid observations remain or if a bandwidth becomes zero
        after rounding.
    """
    data = df.copy()

    # Restrict to user subset if provided
    if subset is not None:
        work = data.loc[subset].copy()
    else:
        work = data.copy()

    # Keep only observations usable for rdrobust
    work = work.loc[work[[depvar, var]].notna().all(axis=1)].copy()

    if work.empty:
        raise ValueError("No non-missing observations available for depvar and var.")

    # Estimate bandwidth with rdrobust
    rd_result = rdrobust(
        y=work[depvar].to_numpy(),
        x=work[var].to_numpy(),
        c=0,
        kernel=kernel,
        p=degree,
        bwselect=_map_bwselect(bwmethod),
    )

    # Extract and derive bandwidth variants
    bw_opt = round(_extract_bandwidth(rd_result), 2)
    bw_half = round(bw_opt / 2.0, 2)
    bw_double = round(bw_opt * 2.0, 2)

    if bw_opt == 0 or bw_half == 0 or bw_double == 0:
        raise ValueError("A computed bandwidth is zero after rounding; weights cannot be built.")

    # Build weight sets for the full dataframe, not only the estimation subset.
    # This mirrors the Stata logic where helper variables are typically created
    # on the working dataset.
    out_opt = _triangular_weights(data[var], bw_opt, prefix="")
    out_half = _triangular_weights(data[var], bw_half, prefix="_half")
    out_double = _triangular_weights(data[var], bw_double, prefix="_double")

    # Attach all helper columns
    data = pd.concat([data, out_opt, out_half, out_double], axis=1)

    return BandwidthWeightsResult(
        data=data,
        bw_opt=bw_opt,
        bw_half=bw_half,
        bw_double=bw_double,
        rdrobust_result=rd_result,
    )


# =============================================================================
# 2) post_ttest.ado -> Python
# =============================================================================

@dataclass
class PostTTestResult:
    """
    Structured result object for Stata-style post t-test outputs.

    Attributes
    ----------
    diff : np.ndarray
        Difference in means matrix.
    se_1 : np.ndarray
        Standard error matrix for group 1 mean.
    se_2 : np.ndarray
        Standard error matrix for group 2 mean.
    sd : np.ndarray
        Matrix storing a scale term analogous to the Stata helper output.
    mu : np.ndarray
        Mean matrix: group 1, group 2, difference.
    se : np.ndarray
        Standard error matrix aligned with `mu`.
    p : np.ndarray
        P-value matrix aligned with `mu`.
    obs : np.ndarray
        Observation count matrix aligned with `mu`.
    colnames : List[str]
        Column labels for the Stata-style display.
    """

    diff: np.ndarray
    se_1: np.ndarray
    se_2: np.ndarray
    sd: np.ndarray
    mu: np.ndarray
    se: np.ndarray
    p: np.ndarray
    obs: np.ndarray
    colnames: List[str]

    def as_dict(self) -> Dict[str, np.ndarray]:
        """
        Return all matrix-like outputs as a dictionary.

        This is useful when the caller wants programmatic access to
        all the components without manually unpacking the dataclass.
        """
        return {
            "diff": self.diff,
            "se_1": self.se_1,
            "se_2": self.se_2,
            "sd": self.sd,
            "mu": self.mu,
            "se": self.se,
            "p": self.p,
            "obs": self.obs,
        }


def _validate_colnames(colnames: Sequence[str]) -> List[str]:
    """
    Validate that Stata-style output column names are correctly specified.

    Expected structure
    ------------------
    Exactly three names:
    1. first group label
    2. second group label
    3. difference label

    Parameters
    ----------
    colnames : Sequence[str]
        Candidate output column names.

    Returns
    -------
    List[str]
        Validated list of three column names.

    Raises
    ------
    ValueError
        If the number of names is not exactly three.
    """
    colnames = list(colnames)
    if len(colnames) != 3:
        raise ValueError(
            "colnames must contain exactly 3 names, for example: "
            "['group_1', 'group_2', 'difference']"
        )
    return colnames


def _sample_sd(x: np.ndarray) -> float:
    """
    Compute the sample standard deviation (ddof=1).

    Parameters
    ----------
    x : np.ndarray
        Sample values.

    Returns
    -------
    float
        Sample standard deviation.
    """
    return float(np.std(x, ddof=1))


def _mean_se(sd: float, n: int) -> float:
    """
    Compute the standard error of a sample mean.

    Formula
    -------
        se(mean) = sd / sqrt(n)

    Parameters
    ----------
    sd : float
        Sample standard deviation.
    n : int
        Sample size.

    Returns
    -------
    float
        Standard error of the mean.
    """
    return float(sd / math.sqrt(n))


def _se_of_difference_equal_var(sd1: float, sd2: float, n1: int, n2: int) -> float:
    """
    Compute the standard error of the difference in means under the
    equal-variance assumption.

    Parameters
    ----------
    sd1 : float
        Sample SD for group 1.
    sd2 : float
        Sample SD for group 2.
    n1 : int
        Sample size for group 1.
    n2 : int
        Sample size for group 2.

    Returns
    -------
    float
        Standard error of the mean difference.

    Raises
    ------
    ValueError
        If one of the groups has fewer than 2 observations.
    """
    if n1 < 2 or n2 < 2:
        raise ValueError("Each group must contain at least 2 observations.")

    pooled_var = (((n1 - 1) * sd1**2) + ((n2 - 1) * sd2**2)) / (n1 + n2 - 2)
    return float(math.sqrt(pooled_var * (1 / n1 + 1 / n2)))


def post_ttest_from_samples(
    group1: Sequence[float],
    group2: Sequence[float],
    colnames: Sequence[str],
    equal_var: bool = True,
    nan_policy: str = "omit",
) -> PostTTestResult:
    """
    Python equivalent of the Stata `post_ttest` helper using raw samples.

    What this function does
    -----------------------
    1. Takes two groups of observations.
    2. Handles missing values according to `nan_policy`.
    3. Computes means, standard deviations, standard errors.
    4. Runs a two-sample t-test via `scipy.stats.ttest_ind`.
    5. Reconstructs a Stata-style set of output matrices.

    Parameters
    ----------
    group1 : Sequence[float]
        Observations from the first group.
    group2 : Sequence[float]
        Observations from the second group.
    colnames : Sequence[str]
        Three Stata-style output column labels.
    equal_var : bool, optional
        Whether to assume equal variances in the t-test.
    nan_policy : str, optional
        How to handle NaN values:
        - "omit"
        - "raise"
        - "propagate"

    Returns
    -------
    PostTTestResult
        Structured Stata-style t-test result.

    Raises
    ------
    ValueError
        If there are insufficient observations or invalid arguments.
    """
    colnames = _validate_colnames(colnames)

    x1 = np.asarray(group1, dtype=float)
    x2 = np.asarray(group2, dtype=float)

    # Missing-value handling
    if nan_policy == "omit":
        x1 = x1[~np.isnan(x1)]
        x2 = x2[~np.isnan(x2)]
    elif nan_policy == "raise":
        if np.isnan(x1).any() or np.isnan(x2).any():
            raise ValueError("NaN values found in input groups.")
    elif nan_policy == "propagate":
        pass
    else:
        raise ValueError("nan_policy must be one of: 'omit', 'raise', 'propagate'.")

    n1 = int(len(x1))
    n2 = int(len(x2))
    if n1 < 2 or n2 < 2:
        raise ValueError("Each group must contain at least 2 non-missing observations.")

    # Summary statistics
    mu1 = float(np.mean(x1))
    mu2 = float(np.mean(x2))
    diff_value = mu1 - mu2

    sd1 = _sample_sd(x1)
    sd2 = _sample_sd(x2)
    se1 = _mean_se(sd1, n1)
    se2 = _mean_se(sd2, n2)

    # Two-sample t-test
    ttest = stats.ttest_ind(x1, x2, equal_var=equal_var, nan_policy=nan_policy)
    p_value = float(ttest.pvalue)

    if equal_var:
        se_diff = _se_of_difference_equal_var(sd1, sd2, n1, n2)
    else:
        se_diff = float(math.sqrt(sd1**2 / n1 + sd2**2 / n2))

    # Build Stata-style matrices
    diff = np.array([[diff_value]], dtype=float)
    se_1 = np.array([[se1]], dtype=float)
    se_2 = np.array([[se2]], dtype=float)
    sd = np.array([[se_diff * math.sqrt(n1)]], dtype=float)

    empty = np.nan
    mu = np.array([[mu1, mu2, diff_value]], dtype=float)
    se = np.array([[se1, se2, se_diff]], dtype=float)
    p = np.array([[empty, empty, p_value]], dtype=float)
    obs = np.array([[empty, empty, float(n1)]], dtype=float)

    return PostTTestResult(
        diff=diff,
        se_1=se_1,
        se_2=se_2,
        sd=sd,
        mu=mu,
        se=se,
        p=p,
        obs=obs,
        colnames=colnames,
    )


def post_ttest_from_stats(
    mu1: float,
    mu2: float,
    sd1: float,
    sd2: float,
    n1: int,
    n2: int,
    p_value: float,
    colnames: Sequence[str],
    equal_var: bool = True,
) -> PostTTestResult:
    """
    Build Stata-style t-test outputs from precomputed summary statistics.

    Why this function exists
    ------------------------
    Sometimes the raw sample values are not available, but summary
    statistics already are. This function reconstructs a result object
    in the same style as `post_ttest_from_samples()`.

    Parameters
    ----------
    mu1, mu2 : float
        Group means.
    sd1, sd2 : float
        Group standard deviations.
    n1, n2 : int
        Group sample sizes.
    p_value : float
        Precomputed p-value for the difference in means.
    colnames : Sequence[str]
        Stata-style output column names.
    equal_var : bool, optional
        Whether to use equal-variance logic for the SE of the difference.

    Returns
    -------
    PostTTestResult
        Structured result object.
    """
    colnames = _validate_colnames(colnames)

    if n1 < 2 or n2 < 2:
        raise ValueError("n1 and n2 must each be at least 2.")

    diff_value = float(mu1 - mu2)
    se1 = _mean_se(float(sd1), int(n1))
    se2 = _mean_se(float(sd2), int(n2))

    if equal_var:
        se_diff = _se_of_difference_equal_var(float(sd1), float(sd2), int(n1), int(n2))
    else:
        se_diff = float(math.sqrt(float(sd1) ** 2 / n1 + float(sd2) ** 2 / n2))

    diff = np.array([[diff_value]], dtype=float)
    se_1 = np.array([[se1]], dtype=float)
    se_2 = np.array([[se2]], dtype=float)
    sd = np.array([[se_diff * math.sqrt(n1)]], dtype=float)

    empty = np.nan
    mu = np.array([[float(mu1), float(mu2), diff_value]], dtype=float)
    se = np.array([[se1, se2, se_diff]], dtype=float)
    p = np.array([[empty, empty, float(p_value)]], dtype=float)
    obs = np.array([[empty, empty, float(n1)]], dtype=float)

    return PostTTestResult(
        diff=diff,
        se_1=se_1,
        se_2=se_2,
        sd=sd,
        mu=mu,
        se=se,
        p=p,
        obs=obs,
        colnames=colnames,
    )


def print_post_ttest_result(result: PostTTestResult, decimals: int = 4) -> None:
    """
    Pretty-print a `PostTTestResult` in a console-friendly Stata-like style.

    Parameters
    ----------
    result : PostTTestResult
        Result object to display.
    decimals : int, optional
        Number of decimals to print.
    """
    fmt = f"{{:.{decimals}f}}"

    print("\nmu")
    mu_df = pd.DataFrame(result.mu, columns=result.colnames)
    print(mu_df.to_string(index=False, float_format=lambda x: fmt.format(x)))

    print("\nse")
    se_df = pd.DataFrame(result.se, columns=result.colnames)
    print(se_df.to_string(index=False, float_format=lambda x: fmt.format(x)))

    print("\np")
    p_df = pd.DataFrame(result.p, columns=result.colnames)
    print(p_df.to_string(index=False, float_format=lambda x: fmt.format(x) if pd.notna(x) else ""))

    print("\nobs")
    obs_df = pd.DataFrame(result.obs, columns=result.colnames)
    print(obs_df.to_string(index=False, float_format=lambda x: fmt.format(x) if pd.notna(x) else ""))


# =============================================================================
# 3) rdd_plot.ado -> Python
# =============================================================================

@dataclass
class RDPlotResult:
    """
    Structured result object for RD plot generation.

    Attributes
    ----------
    plot_df : pd.DataFrame
        Binned means used for the scatter plot.
    left_curve : pd.DataFrame
        Local-linear fit and confidence band on the left of the cutoff.
    right_curve : pd.DataFrame
        Local-linear fit and confidence band on the right of the cutoff.
    figure : plt.Figure
        Matplotlib figure object.
    axis : plt.Axes
        Matplotlib axis object.
    """

    plot_df: pd.DataFrame
    left_curve: pd.DataFrame
    right_curve: pd.DataFrame
    figure: plt.Figure
    axis: plt.Axes


def triangular_kernel(u: np.ndarray) -> np.ndarray:
    """
    Triangular kernel function.

    Definition
    ----------
        K(u) = 1 - |u|    if |u| <= 1
             = 0          otherwise

    Parameters
    ----------
    u : np.ndarray
        Scaled distances.

    Returns
    -------
    np.ndarray
        Kernel weights.
    """
    u = np.asarray(u, dtype=float)
    return np.where(np.abs(u) <= 1, 1 - np.abs(u), 0.0)


def _weighted_local_linear_predict(
    x: np.ndarray,
    y: np.ndarray,
    grid: np.ndarray,
    bw: float,
) -> pd.DataFrame:
    """
    Fit local-linear regressions on a prediction grid using
    triangular-kernel weights.

    For each grid point g:
    ----------------------
    1. Compute scaled distances (x - g) / bw
    2. Apply triangular-kernel weights
    3. Keep only observations with strictly positive weight
    4. Fit a weighted local-linear regression
    5. Store:
       - fitted value
       - standard error
       - upper/lower 95% confidence interval

    Parameters
    ----------
    x : np.ndarray
        Running variable.
    y : np.ndarray
        Outcome variable.
    grid : np.ndarray
        Prediction grid.
    bw : float
        Bandwidth.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - x
        - fit
        - se
        - ul
        - ll
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    grid = np.asarray(grid, dtype=float)

    rows = []
    for g in grid:
        u = (x - g) / bw
        w = triangular_kernel(u)
        mask = w > 0

        # Require a minimal local sample size
        if mask.sum() < 3:
            rows.append((g, np.nan, np.nan))
            continue

        x_centered = x[mask] - g
        X = np.column_stack([np.ones(mask.sum()), x_centered])
        y_local = y[mask]
        w_local = w[mask]

        model = sm.WLS(y_local, X, weights=w_local)
        result = model.fit()

        pred = result.params[0]
        se = result.bse[0]
        rows.append((g, pred, se))

    out = pd.DataFrame(rows, columns=["x", "fit", "se"])
    out["ul"] = out["fit"] + 1.96 * out["se"]
    out["ll"] = out["fit"] - 1.96 * out["se"]
    return out


def rdd_plot(
    df: pd.DataFrame,
    outcome: str,
    running: str,
    *,
    xtitle: str,
    bw: float,
    includedbw: float,
    title: str,
    binsize: float,
    yscale: Optional[Sequence[float] | str] = None,
    if_mask: Optional[Iterable[bool]] = None,
    output_path: Optional[str] = None,
    figsize: tuple[float, float] = (9, 6),
) -> RDPlotResult:
    """
    Reproduce the Stata `rdd_plot` behavior in Python.

    High-level workflow
    -------------------
    1. Optionally subset the sample.
    2. Drop missing outcome/running values.
    3. Restrict to observations within `includedbw`.
    4. Create bins and compute binned means.
    5. Split the sample left/right of the cutoff.
    6. Fit local-linear curves separately on both sides.
    7. Build a plot with:
       - binned means
       - fitted curves
       - confidence bands
       - vertical cutoff line at 0
    8. Optionally save the figure.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    outcome : str
        Outcome variable name.
    running : str
        Running variable name.
    xtitle : str
        X-axis label.
    bw : float
        Bandwidth used for local fitting.
    includedbw : float
        Sample window used to keep observations for plotting.
    title : str
        Y-axis label / plot title context.
    binsize : float
        Bin width used for mean aggregation.
    yscale : Optional[Sequence[float] | str], optional
        Optional custom y-axis ticks.
    if_mask : Optional[Iterable[bool]], optional
        Optional boolean mask for sample restriction.
    output_path : Optional[str], optional
        Path where the figure should be saved.
    figsize : tuple[float, float], optional
        Figure size passed to matplotlib.

    Returns
    -------
    RDPlotResult
        Structured plotting result.

    Raises
    ------
    ValueError
        If the remaining sample is empty or if one side of the cutoff
        has no observations.
    """
    work = df.copy()

    # Apply optional Stata-like "if" restriction
    if if_mask is not None:
        mask = np.asarray(list(if_mask), dtype=bool)
        work = work.loc[mask].copy()

    # Keep only relevant variables and drop missing values
    work = work[[outcome, running]].dropna().copy()

    # Restrict to the chosen plotting window
    work = work.loc[work[running].abs() < includedbw].copy()

    if work.empty:
        raise ValueError("No observations remain after applying the plot restrictions.")

    # Construct bins centered around their midpoint
    work["bin"] = work[running] - np.mod(work[running], binsize) + binsize / 2.0

    # Compute mean outcome per bin
    plot_df = (
        work.groupby("bin", as_index=False)
        .agg(mean=(outcome, "mean"), n=(outcome, "size"))
        .sort_values("bin")
        .reset_index(drop=True)
    )

    # Split sample at the cutoff
    left = work.loc[work[running] < 0].copy()
    right = work.loc[work[running] >= 0].copy()

    if left.empty or right.empty:
        raise ValueError("The RD plot requires observations on both sides of the cutoff.")

    # Prediction grids
    left_grid = np.linspace(left[running].min(), min(left[running].max(), 0.0), 100)
    right_grid = np.linspace(max(right[running].min(), 0.0), right[running].max(), 100)

    # Local-linear fits on both sides
    left_curve = _weighted_local_linear_predict(
        x=left[running].to_numpy(),
        y=left[outcome].to_numpy(),
        grid=left_grid,
        bw=bw,
    )
    right_curve = _weighted_local_linear_predict(
        x=right[running].to_numpy(),
        y=right[outcome].to_numpy(),
        grid=right_grid,
        bw=bw,
    )

    # Build the plot
    fig, ax = plt.subplots(figsize=figsize)

    # Confidence bands
    ax.fill_between(left_curve["x"], left_curve["ll"], left_curve["ul"], alpha=0.25)
    ax.fill_between(right_curve["x"], right_curve["ll"], right_curve["ul"], alpha=0.25)

    # Binned means
    ax.scatter(plot_df["bin"], plot_df["mean"], s=36)

    # Left-side fit and confidence interval bounds
    ax.plot(left_curve["x"], left_curve["fit"], linewidth=2)
    ax.plot(left_curve["x"], left_curve["ul"], linewidth=1)
    ax.plot(left_curve["x"], left_curve["ll"], linewidth=1)

    # Right-side fit and confidence interval bounds
    ax.plot(right_curve["x"], right_curve["fit"], linewidth=2)
    ax.plot(right_curve["x"], right_curve["ul"], linewidth=1)
    ax.plot(right_curve["x"], right_curve["ll"], linewidth=1)

    # RD cutoff
    ax.axvline(0.0, linewidth=1)

    # Labels
    ax.set_xlabel(xtitle)
    ax.set_ylabel(title)

    # Default x ticks similar to many RD plots in the project
    ax.set_xticks(np.arange(-30, 31, 10))

    # Optional user-defined y-axis ticks
    if yscale is not None and not isinstance(yscale, str):
        ax.set_yticks(list(yscale))

    # Optional file output
    if output_path:
        fig.savefig(output_path, bbox_inches="tight", dpi=300)

    return RDPlotResult(
        plot_df=plot_df,
        left_curve=left_curve,
        right_curve=right_curve,
        figure=fig,
        axis=ax,
    )


# =============================================================================
# 4) Small CLI / main example
# =============================================================================

def _load_data(data_path: str) -> pd.DataFrame:
    """
    Load a dataset from `.dta` or `.csv`.

    Parameters
    ----------
    data_path : str
        Path to the input file.

    Returns
    -------
    pd.DataFrame
        Loaded dataset.

    Raises
    ------
    ValueError
        If the file extension is unsupported.
    ImportError
        If reading a `.dta` file but `pyreadstat` is not installed.
    """
    lower = data_path.lower()

    if lower.endswith(".dta"):
        try:
            import pyreadstat  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Reading .dta files requires pyreadstat. Install it with: pip install pyreadstat"
            ) from exc

        df, _meta = pyreadstat.read_dta(data_path)
        return df

    if lower.endswith(".csv"):
        return pd.read_csv(data_path)

    raise ValueError("Unsupported file format. Use a .dta or .csv file.")


def main() -> None:
    """
    Small command-line interface for quick tests and demonstrations.

    Supported modes
    ---------------
    - bandwidth : run only the bandwidth/weight example
    - ttest     : run only the t-test example
    - plot      : run only the RD plot example
    - all       : run all compatible examples

    Example
    -------
    python stata_helpers.py mydata.dta \
        --depvar gewinn_norm \
        --running margin_1 \
        --outcome gewinn_norm \
        --group treated \
        --mode all
    """
    parser = argparse.ArgumentParser(
        description="Run merged helpers translated from Stata .ado files."
    )
    parser.add_argument("data", nargs="?", help="Path to the .dta or .csv dataset")
    parser.add_argument("--depvar", help="Dependent variable for bandwidth_and_weights")
    parser.add_argument("--running", help="Running variable for RD functions")
    parser.add_argument("--group", help="Binary grouping variable for t-test example")
    parser.add_argument("--outcome", help="Outcome variable for RD plot or t-test")
    parser.add_argument("--bwmethod", default="mserd", help="rdrobust bandwidth selector")
    parser.add_argument("--kernel", default="triangular", help="Kernel for rdrobust")
    parser.add_argument("--degree", type=int, default=1, help="Polynomial degree for rdrobust")
    parser.add_argument("--bw", type=float, help="Bandwidth for the RD plot")
    parser.add_argument("--includedbw", type=float, default=30.0, help="Sample window for the RD plot")
    parser.add_argument("--binsize", type=float, default=2.0, help="Bin size for the RD plot")
    parser.add_argument("--plot-output", default="rdd_plot.png", help="Output file for the RD plot")
    parser.add_argument(
        "--mode",
        choices=["all", "bandwidth", "ttest", "plot"],
        default="all",
        help="Which example to run",
    )

    args = parser.parse_args()

    # If the user did not provide data, show a usage example and exit.
    if not args.data:
        print("Example usage:")
        print(
            "python meco_replication.stata_helpers.py mydata.dta "
            "--depvar gewinn_norm --running margin_1 --outcome gewinn_norm "
            "--group treated --mode all"
        )
        return

    df = _load_data(args.data)
    print(f"Loaded dataset with shape: {df.shape}")

    # -------------------------------------------------------------
    # Bandwidth example
    # -------------------------------------------------------------
    if args.mode in {"all", "bandwidth"}:
        if not args.depvar or not args.running:
            print("Skipping bandwidth example: --depvar and --running are required.")
        else:
            bw_result = bandwidth_and_weights(
                df=df,
                depvar=args.depvar,
                var=args.running,
                bwmethod=args.bwmethod,
                kernel=args.kernel,
                degree=args.degree,
            )
            print("\nBandwidth example")
            print(f"Optimal bandwidth: {bw_result.bw_opt}")
            print(f"Half bandwidth:    {bw_result.bw_half}")
            print(f"Double bandwidth:  {bw_result.bw_double}")
            print("Added columns:")
            print(
                [
                    "temp1", "ind", "temp2", "weight",
                    "temp1_half", "ind_half", "temp2_half", "weight_half",
                    "temp1_double", "ind_double", "temp2_double", "weight_double",
                ]
            )

    # -------------------------------------------------------------
    # T-test example
    # -------------------------------------------------------------
    if args.mode in {"all", "ttest"}:
        if not args.outcome or not args.group:
            print("Skipping t-test example: --outcome and --group are required.")
        else:
            work = df[[args.outcome, args.group]].dropna().copy()
            groups = sorted(work[args.group].unique())
            if len(groups) != 2:
                print("Skipping t-test example: grouping variable must contain exactly 2 groups.")
            else:
                g1 = work.loc[work[args.group] == groups[0], args.outcome]
                g2 = work.loc[work[args.group] == groups[1], args.outcome]
                tt_result = post_ttest_from_samples(
                    group1=g1,
                    group2=g2,
                    colnames=[str(groups[0]), str(groups[1]), "difference"],
                )
                print("\nT-test example")
                print_post_ttest_result(tt_result)

    # -------------------------------------------------------------
    # RD plot example
    # -------------------------------------------------------------
    if args.mode in {"all", "plot"}:
        if not args.outcome or not args.running:
            print("Skipping plot example: --outcome and --running are required.")
        else:
            plot_bw = args.bw

            # If the user did not provide a bandwidth explicitly,
            # try to reuse the one computed in the bandwidth example.
            if plot_bw is None:
                try:
                    bw_result
                except UnboundLocalError:
                    bw_result = bandwidth_and_weights(
                        df=df,
                        depvar=args.outcome,
                        var=args.running,
                        bwmethod=args.bwmethod,
                        kernel=args.kernel,
                        degree=args.degree,
                    )
                plot_bw = bw_result.bw_opt

            _plot_result = rdd_plot(
                df=df,
                outcome=args.outcome,
                running=args.running,
                xtitle=args.running,
                bw=plot_bw,
                includedbw=args.includedbw,
                title=args.outcome,
                binsize=args.binsize,
                output_path=args.plot_output,
            )
            print("\nRD plot example")
            print(f"Plot saved to: {args.plot_output}")


# Public API exported by `from stata_helpers import *`
__all__ = [
    "BandwidthWeightsResult",
    "PostTTestResult",
    "RDPlotResult",
    "bandwidth_and_weights",
    "post_ttest_from_samples",
    "post_ttest_from_stats",
    "print_post_ttest_result",
    "rdd_plot",
    "triangular_kernel",
    "main",
]


# Standard Python entry point
if __name__ == "__main__":
    main()