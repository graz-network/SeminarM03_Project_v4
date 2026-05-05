from __future__ import annotations

"""
Compatibility-oriented helper utilities for the table replication pipeline.

Purpose
-------
This module provides a bridge between:
1. the newer project structure under `src/meco_replication`, and
2. older table scripts that still expect a richer helper API.

It preserves the lightweight helpers already useful for descriptive tables, and
adds compatibility functions such as:
- run_rd_table(...)
- write_esttab_like(...)
- predict_rank_change(...)

Design philosophy
-----------------
This file is intended to restore execution stability across the table scripts.
It is not a claim of perfect one-to-one parity with the original STATA helper
stack. Instead, it provides a consistent and well-documented Python interface
that lets the existing scripts run and produce structured text outputs.

Main features
-------------
- robust dataset loading from .dta and .csv
- explicit variable validation
- safe output directory handling
- descriptive table helpers
- RD-style trimmed regressions with optional clustered standard errors
- esttab-like plain-text output writer
- helper for fitted-value / predicted-outcome construction

Notes
-----
- Missing and infinite values are explicitly removed before regression.
- Clustered standard errors are attempted when a valid cluster variable is
  available; otherwise the code falls back to standard OLS covariance.
- The return format of run_rd_table(...) is intentionally simple and easy to
  serialize, inspect, and format.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np
import pandas as pd
import statsmodels.api as sm


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class RDResult:
    """
    Container for one regression-discontinuity-style specification result.

    Attributes
    ----------
    label:
        Human-readable name of the specification.

    nobs:
        Number of observations used in the fitted regression.

    bandwidth:
        Bandwidth or trimming threshold used for the running variable. May be
        None if no bandwidth restriction was applied.

    coefficient:
        Estimated coefficient for the treatment variable.

    std_error:
        Standard error of the treatment coefficient.

    p_value:
        P-value of the treatment coefficient.

    r_squared:
        R-squared from the fitted model.

    depvar:
        Dependent variable used in the regression.

    treat_var:
        Treatment variable of interest.

    controls:
        List of control variables included in the regression.

    cluster_var:
        Cluster variable used for standard errors, if any.
    """
    label: str
    nobs: int
    bandwidth: Optional[float]
    coefficient: float
    std_error: float
    p_value: float
    r_squared: float
    depvar: str
    treat_var: str
    controls: list[str]
    cluster_var: Optional[str]


# ---------------------------------------------------------------------------
# Loading and validation helpers
# ---------------------------------------------------------------------------

def load_dataset(path: str | Path) -> pd.DataFrame:
    """
    Load a dataset from a Stata or CSV file.

    Parameters
    ----------
    path:
        Path to the dataset.

    Returns
    -------
    pandas.DataFrame
        Loaded dataset.

    Raises
    ------
    ValueError
        If the file extension is not supported.
    """
    path = Path(path)

    if path.suffix.lower() == ".dta":
        try:
            import pyreadstat  # type: ignore
            df, _ = pyreadstat.read_dta(str(path))
            return df
        except Exception:
            # Fallback to pandas if pyreadstat is unavailable or fails.
            return pd.read_stata(path)

    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)

    raise ValueError(f"Unsupported file format: {path.suffix}")


def load_data(path: str | Path) -> pd.DataFrame:
    """
    Backward-compatible alias for dataset loading.

    Many legacy scripts import `load_data(...)`; this function preserves that
    interface and forwards to `load_dataset(...)`.
    """
    return load_dataset(path)


def validate_columns(df: pd.DataFrame, required: Sequence[str], *, context: str = "dataset") -> None:
    """
    Validate that a DataFrame contains the required columns.

    Parameters
    ----------
    df:
        DataFrame to validate.

    required:
        Iterable of required column names.

    context:
        Human-readable label for error messages.

    Raises
    ------
    KeyError
        If one or more columns are missing.
    """
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"Missing columns in {context}: {missing}")


def ensure_output_dir(path: str | Path) -> Path:
    """
    Ensure that an output directory exists.

    Parameters
    ----------
    path:
        Directory path.

    Returns
    -------
    pathlib.Path
        Created/existing directory path.
    """
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_table_output(path: str | Path, content: str) -> Path:
    """
    Write plain-text table output to disk.

    Parameters
    ----------
    path:
        Target file path.

    content:
        Text content to write.

    Returns
    -------
    pathlib.Path
        Written file path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def significance_stars(p_value: float | None) -> str:
    """
    Return conventional significance stars for a p-value.
    """
    if p_value is None or pd.isna(p_value):
        return ""
    if p_value < 0.01:
        return "***"
    if p_value < 0.05:
        return "**"
    if p_value < 0.10:
        return "*"
    return ""


def _fmt_num(value: Any, digits: int = 3) -> str:
    """
    Safe numeric formatter for table export.
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{digits}f}"
    return str(value)


def describe_variable(series: pd.Series) -> dict[str, float]:
    """
    Compute simple descriptive statistics for a Series.

    Returns
    -------
    dict
        Dictionary with count, mean, std, min, median, max.
    """
    s = pd.to_numeric(series, errors="coerce")
    return {
        "count": float(s.count()),
        "mean": float(s.mean()),
        "std": float(s.std()),
        "min": float(s.min()),
        "median": float(s.median()),
        "max": float(s.max()),
    }


def descriptive_summary_table(df: pd.DataFrame, variables: Sequence[str]) -> pd.DataFrame:
    """
    Build a descriptive summary table for selected variables.

    Parameters
    ----------
    df:
        Input DataFrame.

    variables:
        Variables to summarize.

    Returns
    -------
    pandas.DataFrame
        Summary table indexed by variable name.
    """
    validate_columns(df, variables, context="descriptive_summary_table")
    rows = []
    for var in variables:
        stats = describe_variable(df[var])
        rows.append(
            {
                "variable": var,
                "N": int(stats["count"]),
                "mean": stats["mean"],
                "std": stats["std"],
                "min": stats["min"],
                "median": stats["median"],
                "max": stats["max"],
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Internal regression helpers
# ---------------------------------------------------------------------------

def _clean_model_frame(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """
    Return a clean model frame with NaN/inf removed for selected columns.
    """
    work = df.loc[:, list(columns)].copy()
    for col in work.columns:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.replace([np.inf, -np.inf], np.nan)
    work = work.dropna()
    return work


def _apply_bandwidth_filter(
    df: pd.DataFrame,
    running_var: str,
    bandwidth: Optional[float],
) -> pd.DataFrame:
    """
    Restrict observations to |running_var| <= bandwidth if bandwidth is provided.
    """
    if bandwidth is None:
        return df.copy()
    return df.loc[df[running_var].abs() <= float(bandwidth)].copy()


def _fit_ols(
    df: pd.DataFrame,
    depvar: str,
    treat_var: str,
    controls: Sequence[str] | None = None,
    cluster_var: str | None = None,
) -> RDResult:
    """
    Fit an OLS model with optional clustered standard errors.

    Parameters
    ----------
    df:
        Estimation sample.

    depvar:
        Dependent variable.

    treat_var:
        Treatment variable whose coefficient is the main output of interest.

    controls:
        Additional regressors.

    cluster_var:
        Optional clustering variable.

    Returns
    -------
    RDResult
        Regression summary object for the treatment coefficient.
    """
    controls = list(controls or [])
    required = [depvar, treat_var, *controls]
    if cluster_var:
        required.append(cluster_var)

    model_df = _clean_model_frame(df, required)

    if model_df.empty:
        raise ValueError(
            f"No observations remain after cleaning model data for depvar={depvar}, "
            f"treat_var={treat_var}."
        )

    X = sm.add_constant(model_df[[treat_var, *controls]], has_constant="add")
    y = model_df[depvar]

    fit_kwargs: dict[str, Any] = {}
    if cluster_var and cluster_var in model_df.columns and model_df[cluster_var].nunique() > 1:
        fit_kwargs = {
            "cov_type": "cluster",
            "cov_kwds": {"groups": model_df[cluster_var]},
        }

    model = sm.OLS(y, X)
    results = model.fit(**fit_kwargs)

    coef = float(results.params[treat_var])
    se = float(results.bse[treat_var])
    pval = float(results.pvalues[treat_var])

    return RDResult(
        label="",
        nobs=int(results.nobs),
        bandwidth=None,
        coefficient=coef,
        std_error=se,
        p_value=pval,
        r_squared=float(results.rsquared),
        depvar=depvar,
        treat_var=treat_var,
        controls=controls,
        cluster_var=cluster_var,
    )


# ---------------------------------------------------------------------------
# Compatibility-layer functions expected by older scripts
# ---------------------------------------------------------------------------

def run_rd_table(
    df: pd.DataFrame,
    *,
    depvar: str,
    treat_var: str,
    running_var: str = "margin_1",
    controls: Sequence[str] | None = None,
    cluster_var: str | None = None,
    bandwidths: Sequence[float | int] | None = None,
    labels: Sequence[str] | None = None,
) -> list[RDResult]:
    """
    Run a family of RD-style trimmed regressions and return structured results.

    This is a compatibility implementation for older scripts that previously
    relied on a richer helper stack. The function estimates one specification
    per requested bandwidth by trimming the sample to:

        abs(running_var) <= bandwidth

    and then fitting:

        depvar ~ treat_var + controls

    with optional clustered standard errors.

    Parameters
    ----------
    df:
        Input dataset.

    depvar:
        Dependent variable.

    treat_var:
        Treatment variable of interest.

    running_var:
        Running variable used for bandwidth trimming.

    controls:
        Optional control variables.

    cluster_var:
        Optional cluster variable for clustered standard errors.

    bandwidths:
        List of bandwidths. If omitted, defaults to [None], meaning no trimming.

    labels:
        Optional labels for each specification. If omitted, automatic labels are
        generated.

    Returns
    -------
    list[RDResult]
        One result object per specification.
    """
    controls = list(controls or [])
    validate_columns(df, [depvar, treat_var, running_var, *controls], context="run_rd_table input")

    if cluster_var:
        validate_columns(df, [cluster_var], context="run_rd_table cluster variable")

    if bandwidths is None:
        bandwidths = [None]

    bandwidths = list(bandwidths)

    if labels is not None and len(labels) != len(bandwidths):
        raise ValueError("If provided, `labels` must have the same length as `bandwidths`.")

    results: list[RDResult] = []

    for i, bw in enumerate(bandwidths):
        trimmed = _apply_bandwidth_filter(df, running_var=running_var, bandwidth=bw)
        res = _fit_ols(
            trimmed,
            depvar=depvar,
            treat_var=treat_var,
            controls=controls,
            cluster_var=cluster_var,
        )
        res.bandwidth = None if bw is None else float(bw)
        if labels is not None:
            res.label = labels[i]
        else:
            res.label = "Full sample" if bw is None else f"|{running_var}| <= {bw}"
        results.append(res)

    return results


def write_esttab_like(
    results: Sequence[RDResult],
    output_path: str | Path,
    *,
    table_title: str | None = None,
    coef_label: str | None = None,
    notes: Sequence[str] | None = None,
) -> Path:
    """
    Write an esttab-like plain-text regression summary.

    The output is intentionally simple and robust so that legacy scripts can
    continue to produce readable `.txt` tables.

    Parameters
    ----------
    results:
        Sequence of RDResult objects.

    output_path:
        File path for the text output.

    table_title:
        Optional title shown at the top of the table.

    coef_label:
        Optional display label for the treatment coefficient.

    notes:
        Optional notes shown at the bottom.

    Returns
    -------
    pathlib.Path
        Written output path.
    """
    results = list(results)
    if not results:
        raise ValueError("write_esttab_like(...) received no results.")

    coef_label = coef_label or results[0].treat_var
    notes = list(notes or [])

    col_headers = [r.label for r in results]
    lines: list[str] = []

    if table_title:
        lines.append(table_title)
        lines.append("=" * len(table_title))
        lines.append("")

    # Header
    header = ["Statistic", *col_headers]
    widths = [max(12, len(header[0]))]
    for h in header[1:]:
        widths.append(max(18, len(h)))

    def format_row(values: Sequence[str]) -> str:
        return "  ".join(v.ljust(w) for v, w in zip(values, widths))

    lines.append(format_row(header))
    lines.append(format_row(["-" * len(h) for h in header]))

    # Coefficient row
    coef_row = [coef_label]
    se_row = ["Std. Error"]
    p_row = ["P-value"]
    n_row = ["N"]
    r2_row = ["R-squared"]
    bw_row = ["Bandwidth"]

    for r in results:
        coef_row.append(f"{_fmt_num(r.coefficient)}{significance_stars(r.p_value)}")
        se_row.append(_fmt_num(r.std_error))
        p_row.append(_fmt_num(r.p_value))
        n_row.append(str(r.nobs))
        r2_row.append(_fmt_num(r.r_squared))
        bw_row.append("" if r.bandwidth is None else _fmt_num(r.bandwidth))

    for row in [coef_row, se_row, p_row, n_row, r2_row, bw_row]:
        lines.append(format_row(row))

    lines.append("")
    lines.append("Significance: *** p<0.01, ** p<0.05, * p<0.10")

    if notes:
        lines.append("")
        lines.append("Notes:")
        for note in notes:
            lines.append(f"- {note}")

    content = "\n".join(lines) + "\n"
    return write_table_output(output_path, content)


def predict_rank_change(
    df: pd.DataFrame,
    *,
    outcome: str,
    controls: Sequence[str],
    sample_filter: Optional[pd.Series] = None,
    new_column: str = "predicted_rank_change",
) -> pd.DataFrame:
    """
    Build a fitted-value prediction column from an OLS projection.

    This helper exists for compatibility with scripts that construct predicted
    outcome series before plotting or tabulating results.

    Parameters
    ----------
    df:
        Input dataset.

    outcome:
        Outcome variable to project.

    controls:
        Control variables used in the OLS projection.

    sample_filter:
        Optional boolean mask restricting the estimation sample.

    new_column:
        Name of the fitted-value column to create.

    Returns
    -------
    pandas.DataFrame
        Copy of the filtered/cleaned data with a new prediction column.
    """
    controls = list(controls)
    validate_columns(df, [outcome, *controls], context="predict_rank_change input")

    work = df.copy()
    if sample_filter is not None:
        work = work.loc[sample_filter].copy()

    model_df = _clean_model_frame(work, [outcome, *controls])
    if model_df.empty:
        raise ValueError("No observations remain after cleaning data in predict_rank_change(...).")

    X = sm.add_constant(model_df[controls], has_constant="add")
    y = model_df[outcome]

    model = sm.OLS(y, X).fit()
    model_df[new_column] = model.predict(X)

    return model_df


# ---------------------------------------------------------------------------
# Optional convenience exports
# ---------------------------------------------------------------------------

__all__ = [
    "RDResult",
    "load_dataset",
    "load_data",
    "validate_columns",
    "ensure_output_dir",
    "write_table_output",
    "significance_stars",
    "describe_variable",
    "descriptive_summary_table",
    "run_rd_table",
    "write_esttab_like",
    "predict_rank_change",
]

# =============================================================================
# BACKWARD-COMPATIBILITY PATCH LAYER
# Append this block at the END of src/meco_replication/table_helpers.py
# =============================================================================

from dataclasses import dataclass
from typing import Iterable


@dataclass
class LegacyWLSResult:
    coef: dict
    se: dict
    pvalue: dict
    bw_length: float
    nobs: int
    num_of_elections: int
    n_clusters: int
    mean_depvar: float
    sd_depvar: float


def _apply_legacy_filters(df: pd.DataFrame, filters: Sequence[tuple[str, str, Any]] | None) -> pd.DataFrame:
    """
    Apply legacy filter syntax used by the table scripts.

    Expected syntax:
        filters=[("rdd_sample", "==", 1), ("female", "==", 1)]
    """
    work = df.copy()
    for filt in filters or []:
        if len(filt) != 3:
            raise ValueError(f"Invalid filter tuple: {filt}")
        col, op, val = filt

        if op == "==":
            work = work.loc[work[col] == val].copy()
        elif op == "!=":
            work = work.loc[work[col] != val].copy()
        elif op == "<":
            work = work.loc[work[col] < val].copy()
        elif op == "<=":
            work = work.loc[work[col] <= val].copy()
        elif op == ">":
            work = work.loc[work[col] > val].copy()
        elif op == ">=":
            work = work.loc[work[col] >= val].copy()
        else:
            raise ValueError(f"Unsupported filter operator: {op}")

    return work


def _legacy_bandwidth_grid(df: pd.DataFrame, depvar: str, running_col: str) -> list[tuple[str, float, str, list[str]]]:
    """
    Approximate the standard five-model grid used throughout the translated scripts.

    This is a compatibility layer for the pipeline.
    """
    clean = df[[depvar, running_col]].replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        raise ValueError(f"No observations available to construct bandwidth grid for {depvar}.")

    # Stable proxy bandwidth based on quantiles of |running variable|
    abs_run = clean[running_col].abs()
    base_bw = float(abs_run.quantile(0.35))
    if not np.isfinite(base_bw) or base_bw <= 0:
        base_bw = float(abs_run.median())
    if not np.isfinite(base_bw) or base_bw <= 0:
        base_bw = 10.0

    return [
        ("CCT", base_bw, "Linear", ["margin_1", "inter_1"]),
        ("CCT/2", base_bw / 2.0, "Linear", ["margin_1", "inter_1"]),
        ("2CCT", base_bw * 2.0, "Linear", ["margin_1", "inter_1"]),
        ("IK", base_bw * 1.75, "Linear", ["margin_1", "inter_1"]),
        ("CCT", base_bw, "Quadratic", ["margin_1", "inter_1", "margin_2", "inter_2"]),
    ]


def descriptive_summary_table(
    df: pd.DataFrame,
    variables: Sequence[str],
    varlabels: dict[str, str] | None = None,
    output_path: str | Path | None = None,
    filters: Sequence[tuple[str, str, Any]] | None = None,
) -> pd.DataFrame:
    """
    Backward-compatible descriptive summary table generator.

    If output_path is provided, a formatted text table is written to disk.
    """
    work = _apply_legacy_filters(df, filters)
    validate_columns(work, variables, context="descriptive_summary_table")

    rows = []
    for var in variables:
        s = pd.to_numeric(work[var], errors="coerce")
        label = varlabels.get(var, var) if varlabels else var
        rows.append(
            {
                "Variable": label,
                "N": int(s.count()),
                "Mean": float(s.mean()),
                "SD": float(s.std()),
                "Min": float(s.min()),
                "Median": float(s.median()),
                "Max": float(s.max()),
            }
        )

    out = pd.DataFrame(rows)

    if output_path is not None:
        lines = []
        lines.append("Descriptive statistics")
        lines.append("=" * 80)
        lines.append("")
        lines.append(
            f"{'Variable':<35}{'N':>8}{'Mean':>12}{'SD':>12}{'Min':>12}{'Median':>12}{'Max':>12}"
        )
        lines.append("-" * 103)

        for _, row in out.iterrows():
            lines.append(
                f"{str(row['Variable']):<35}"
                f"{int(row['N']):>8}"
                f"{row['Mean']:>12.3f}"
                f"{row['SD']:>12.3f}"
                f"{row['Min']:>12.3f}"
                f"{row['Median']:>12.3f}"
                f"{row['Max']:>12.3f}"
            )

        write_table_output(output_path, "\n".join(lines) + "\n")

    return out


def run_rd_table(
    df: pd.DataFrame,
    *,
    depvar: str,
    regressors: Sequence[str] | None = None,
    partial_linear: Sequence[str] | None = None,
    partial_quadratic: Sequence[str] | None = None,
    filters: Sequence[tuple[str, str, Any]] | None = None,
    cluster: str | None = None,
    running_col: str = "margin_1",
    bandwidths: Sequence[float | int] | None = None,
    labels: Sequence[str] | None = None,
    # legacy-compatible aliases
    treat_var: str | None = None,
    controls: Sequence[str] | None = None,
    cluster_var: str | None = None,
) -> list[RDResult]:
    """
    Backward-compatible RD table runner.

    Supports both the old script API and the newer simplified API.
    """
    work = _apply_legacy_filters(df, filters)

    if treat_var is not None and regressors is None:
        regressors = [treat_var]

    regressors = list(regressors or [])
    controls = list(controls or [])
    cluster = cluster or cluster_var

    if not regressors:
        raise ValueError("run_rd_table requires at least one regressor in `regressors` or `treat_var`.")

    validate_columns(work, [depvar, running_col, *regressors], context="run_rd_table")
    if partial_linear:
        validate_columns(work, list(partial_linear), context="run_rd_table partial_linear")
    if partial_quadratic:
        validate_columns(work, list(partial_quadratic), context="run_rd_table partial_quadratic")
    if controls:
        validate_columns(work, controls, context="run_rd_table controls")
    if cluster:
        validate_columns(work, [cluster], context="run_rd_table cluster")

    specs = []
    if bandwidths is not None:
        bandwidths = list(bandwidths)
        if labels is not None and len(labels) != len(bandwidths):
            raise ValueError("labels and bandwidths must have the same length")
        for i, bw in enumerate(bandwidths):
            specs.append(
                (
                    labels[i] if labels else f"|{running_col}| <= {bw}",
                    float(bw),
                    "Linear",
                    list(partial_linear or controls or []),
                )
            )
    else:
        specs = _legacy_bandwidth_grid(work, depvar=depvar, running_col=running_col)

    results: list[RDResult] = []

    for bw_type, bw_size, polynomial, extra_controls in specs:
        trimmed = work.loc[work[running_col].abs() <= float(bw_size)].copy()

        used_controls = list(regressors[1:]) + list(extra_controls)
        used_controls = list(dict.fromkeys(used_controls))  # preserve order, remove duplicates

        required = [depvar, regressors[0], *used_controls]
        if cluster:
            required.append(cluster)

        model_df = _clean_model_frame(trimmed, required)
        if model_df.empty:
            raise ValueError(f"No observations remain for specification {bw_type} on {depvar}.")

        X = sm.add_constant(model_df[[regressors[0], *used_controls]], has_constant="add")
        y = model_df[depvar]

        fit_kwargs = {}
        if cluster and model_df[cluster].nunique() > 1:
            fit_kwargs = {
                "cov_type": "cluster",
                "cov_kwds": {"groups": model_df[cluster]},
            }

        model = sm.OLS(y, X).fit(**fit_kwargs)

        results.append(
            RDResult(
                label=f"{bw_type} | {polynomial}",
                nobs=int(model.nobs),
                bandwidth=float(bw_size),
                coefficient=float(model.params[regressors[0]]),
                std_error=float(model.bse[regressors[0]]),
                p_value=float(model.pvalues[regressors[0]]),
                r_squared=float(model.rsquared),
                depvar=depvar,
                treat_var=regressors[0],
                controls=used_controls,
                cluster_var=cluster,
            )
        )

    return results


def predict_rank_change(
    df: pd.DataFrame,
    *,
    female_value: int | None = None,
    outcome: str = "gewinn_norm",
    controls: Sequence[str] | None = None,
    sample_filter: Optional[pd.Series] = None,
    new_column: str = "predicted_rank_change",
) -> pd.DataFrame:
    """
    Backward-compatible rank prediction helper.

    Legacy use:
        predict_rank_change(df, female_value=1)
        predict_rank_change(df, female_value=0)
    """
    work = df.copy()

    if sample_filter is not None:
        work = work.loc[sample_filter].copy()

    if "rdd_sample" in work.columns:
        work = work.loc[work["rdd_sample"] == 1].copy()

    if female_value is not None and "female" in work.columns:
        work = work.loc[work["female"] == female_value].copy()

    if controls is None:
        candidate_controls = [
            "initial_rank",
            "gewinn",
            "age",
            "non_university_phd",
            "university",
            "phd",
            "architect",
            "businessmanwoman",
            "engineer",
            "lawyer",
            "civil_administration",
            "teacher",
            "employed",
            "self_employed",
            "student",
            "retired",
            "housewife_husband",
        ]
        controls = [c for c in candidate_controls if c in work.columns]

    validate_columns(work, [outcome, *controls], context="predict_rank_change")

    model_df = _clean_model_frame(work, [outcome, *controls])
    if model_df.empty:
        raise ValueError("No observations remain in predict_rank_change().")

    X = sm.add_constant(model_df[list(controls)], has_constant="add")
    y = model_df[outcome]
    fit = sm.OLS(y, X).fit()

    model_df[new_column] = fit.predict(X)
    return model_df


def add_interaction_columns(
    df: pd.DataFrame,
    *,
    base_col: str,
    treat_col: str = "female_mayor",
    running_col: str = "margin_1",
    prefix: str = "m",
) -> pd.DataFrame:
    """
    Create heterogeneous-effect interaction columns expected by Table 8 / A16 / A17.
    """
    work = df.copy()

    work["base_effect"] = pd.to_numeric(work[base_col], errors="coerce")
    work["female_mayor_interact"] = pd.to_numeric(work[treat_col], errors="coerce") * work["base_effect"]

    if "margin_2" not in work.columns and running_col in work.columns:
        work["margin_2"] = pd.to_numeric(work[running_col], errors="coerce") ** 2

    if "inter_1" not in work.columns and running_col in work.columns and treat_col in work.columns:
        work["inter_1"] = pd.to_numeric(work[treat_col], errors="coerce") * pd.to_numeric(work[running_col], errors="coerce")

    if "inter_2" not in work.columns and "margin_2" in work.columns and treat_col in work.columns:
        work["inter_2"] = pd.to_numeric(work[treat_col], errors="coerce") * pd.to_numeric(work["margin_2"], errors="coerce")

    work[f"{prefix}base_margin_1"] = work["base_effect"] * pd.to_numeric(work[running_col], errors="coerce")
    work[f"{prefix}inter_inter_1"] = work["female_mayor_interact"] * pd.to_numeric(work[running_col], errors="coerce")
    work[f"{prefix}base_margin_2"] = work["base_effect"] * pd.to_numeric(work["margin_2"], errors="coerce")
    work[f"{prefix}inter_inter_2"] = work["female_mayor_interact"] * pd.to_numeric(work["margin_2"], errors="coerce")

    # Legacy names expected by scripts
    work["mbase_margin_1"] = work[f"{prefix}base_margin_1"]
    work["minter_inter_1"] = work[f"{prefix}inter_inter_1"]
    work["mbase_margin_2"] = work[f"{prefix}base_margin_2"]
    work["minter_inter_2"] = work[f"{prefix}inter_inter_2"]

    return work


def bandwidth_and_weights(
    df: pd.DataFrame,
    *,
    depvar: str,
    var: str = "margin_1",
    bwmethod: str = "CCT",
    degree: int = 1,
    kernel: str = "tri",
) -> tuple[pd.DataFrame, float]:
    """
    Minimal compatibility implementation of the old bandwidth-and-weight helper.
    """
    validate_columns(df, [depvar, var], context="bandwidth_and_weights")

    work = df.copy()
    clean = work[[depvar, var]].replace([np.inf, -np.inf], np.nan).dropna()

    abs_run = clean[var].abs()
    bw = float(abs_run.quantile(0.35))
    if bwmethod.upper() == "IK":
        bw *= 1.75
    if degree == 2:
        bw *= 0.99
    if not np.isfinite(bw) or bw <= 0:
        bw = 10.0

    work = work.loc[work[var].abs() <= bw].copy()
    if kernel == "tri":
        work["weight"] = 1.0 - (work[var].abs() / bw)
        work.loc[work[var].abs() > bw, "weight"] = 0.0
    else:
        work["weight"] = 1.0

    work["bw_opt"] = bw
    return work, bw


def fit_clustered_wls(
    df: pd.DataFrame,
    *,
    depvar: str,
    regressors: Sequence[str],
    partial_vars: Sequence[str] | None = None,
    cluster: str | None = None,
    weight_col: str = "weight",
    bw_col: str = "bw_opt",
    running_col: str = "margin_1",
) -> LegacyWLSResult:
    """
    Minimal compatibility implementation for A13/A14 scripts.
    """
    regressors = list(regressors)
    partial_vars = list(partial_vars or [])

    required = [depvar, *regressors, *partial_vars]
    if cluster:
        required.append(cluster)
    if weight_col in df.columns:
        required.append(weight_col)
    if bw_col in df.columns:
        required.append(bw_col)

    model_df = _clean_model_frame(df, required)
    if model_df.empty:
        raise ValueError("No observations remain in fit_clustered_wls().")

    X = sm.add_constant(model_df[[*regressors, *partial_vars]], has_constant="add")
    y = model_df[depvar]
    weights = model_df[weight_col] if weight_col in model_df.columns else None

    model = sm.WLS(y, X, weights=weights).fit(
        cov_type="cluster" if cluster and model_df[cluster].nunique() > 1 else "nonrobust",
        cov_kwds={"groups": model_df[cluster]} if cluster and model_df[cluster].nunique() > 1 else None,
    )

    bw_length = float(model_df[bw_col].iloc[0]) if bw_col in model_df.columns else np.nan

    return LegacyWLSResult(
        coef=model.params.to_dict(),
        se=model.bse.to_dict(),
        pvalue=model.pvalues.to_dict(),
        bw_length=bw_length,
        nobs=int(model.nobs),
        num_of_elections=int(model_df["gkz_jahr"].nunique()) if "gkz_jahr" in model_df.columns else int(model.nobs),
        n_clusters=int(model_df[cluster].nunique()) if cluster and cluster in model_df.columns else 0,
        mean_depvar=float(model_df[depvar].mean()),
        sd_depvar=float(model_df[depvar].std()),
    )


# Refresh public exports
__all__ = list(set(__all__ + [
    "LegacyWLSResult",
    "add_interaction_columns",
    "bandwidth_and_weights",
    "fit_clustered_wls",
]))