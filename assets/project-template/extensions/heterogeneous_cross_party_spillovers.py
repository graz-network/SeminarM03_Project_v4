#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm


PARTY_ALIASES = {
    "grune": "green",
    "gruene": "green",
    "grunen": "green",
    "grune/b90": "green",
    "grune b90": "green",
    "die grunen": "green",
    "diegrunen": "green",
    "b90/gruene": "green",
    "b90": "green",
    "b90 die grunen": "green",
    "diefrauen": "frauen",
    "die linke": "linke",
    "die-linke": "linke",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate benchmark and heterogeneous cross-party spillovers from female mayors."
    )
    parser.add_argument("--main", default="data/raw/main_dataset.dta")
    parser.add_argument("--party", default="data/raw/dataset_for_party_level_results.dta")
    parser.add_argument("--lagged", default="data/raw/dataset_with_lagged_rank_improvments.dta")
    parser.add_argument("--next-election", dest="next_election", default="data/raw/dataset_with_rank_improvments_next_election.dta")
    parser.add_argument("--output-dir", default="results/extensions")
    parser.add_argument(
        "--bandwidths",
        nargs="+",
        type=float,
        default=[5.0, 7.5, 10.0, 15.0],
        help="Bandwidths in percentage points for RD windows.",
    )
    parser.add_argument(
        "--subgroup-bandwidth",
        type=float,
        default=10.0,
        help="Bandwidth used for subgroup summaries and plots.",
    )
    return parser.parse_args()


def load_dataset(path_like: str | Path) -> pd.DataFrame:
    path = Path(path_like)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_stata(path, convert_categoricals=False)


def normalize_key(value: object) -> str:
    return re.sub(r"[^0-9]", "", str(value))


def normalize_party(value: object) -> str:
    party = str(value).strip().lower()
    party = party.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    party = re.sub(r"\s+", " ", party)
    return PARTY_ALIASES.get(party, party)


def add_common_keys(main: pd.DataFrame, party: pd.DataFrame) -> pd.DataFrame:
    main = main.copy()
    main["gkz_jahr_key"] = main["gkz_jahr"].map(normalize_key)
    main["party_std"] = main["party"].map(normalize_party)

    party = party.copy()
    party["gkz_jahr_key"] = party["gkz_jahr"].map(normalize_key)
    party["party_std"] = party["partei"].map(normalize_party)

    female_share_main = (
        main.groupby(["gkz_jahr_key", "party_std"], dropna=False)["female"]
        .mean()
        .mul(100.0)
        .reset_index(name="mean_frau_from_main")
    )

    merged = main.merge(
        female_share_main,
        on=["gkz_jahr_key", "party_std"],
        how="left",
    )
    merged = merged.merge(
        party[["gkz_jahr_key", "party_std", "voteshare", "mean_frau"]].drop_duplicates(),
        on=["gkz_jahr_key", "party_std"],
        how="left",
        suffixes=("", "_partyfile"),
    )
    merged["mean_frau_combined"] = merged["mean_frau"].fillna(merged["mean_frau_from_main"])
    return merged


def triangular_weights(margin: pd.Series, bandwidth: float) -> pd.Series:
    return (1.0 - margin.abs() / bandwidth).clip(lower=0.0)


def prepare_numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def fit_wls(df: pd.DataFrame, formula: str, weight_col: str, cluster_col: str) -> tuple[pd.DataFrame, sm.regression.linear_model.RegressionResultsWrapper]:
    y, X = patsy.dmatrices(formula, df, return_type="dataframe")
    working = df.loc[y.index].copy()
    keep = ~(y.isna().any(axis=1) | X.isna().any(axis=1) | working[weight_col].isna() | working[cluster_col].isna())
    y = y.loc[keep]
    X = X.loc[keep]
    working = working.loc[keep]
    result = sm.WLS(y, X, weights=working[weight_col]).fit(
        cov_type="cluster",
        cov_kwds={"groups": working[cluster_col]},
    )
    coef_table = pd.DataFrame(
        {
            "term": result.params.index,
            "coef": result.params.values,
            "std_err": result.bse.values,
            "t": result.tvalues.values,
            "p_value": result.pvalues.values,
            "ci_low": result.conf_int()[0].values,
            "ci_high": result.conf_int()[1].values,
            "n_obs": int(result.nobs),
            "n_clusters": int(pd.Series(working[cluster_col]).nunique()),
            "r_squared": float(result.rsquared),
        }
    )
    return coef_table, result


def extract_term_row(table: pd.DataFrame, term: str) -> pd.Series:
    row = table.loc[table["term"] == term]
    if row.empty:
        return pd.Series(dtype=float)
    return row.iloc[0]


def benchmark_cross_party(df: pd.DataFrame, bandwidths: list[float]) -> pd.DataFrame:
    results: list[pd.DataFrame] = []
    formulas = {
        "minimal": "gewinn_norm ~ female_mayor + margin_1 + inter_1 + margin_2 + inter_2 + listenplatz_norm",
        "rich": "gewinn_norm ~ female_mayor + margin_1 + inter_1 + margin_2 + inter_2 + listenplatz_norm + incumbent_council + age + wahlbet + log_bevoelkerung",
    }
    for bandwidth in bandwidths:
        sub = df[(df["rdd_sample"] == 1) & (df["female"] == 1) & (df["joint_party"] == 0) & (df["margin_1"].abs() <= bandwidth)].copy()
        sub["tri_w"] = triangular_weights(sub["margin_1"], bandwidth)
        sub = prepare_numeric(
            sub,
            [
                "gewinn_norm",
                "female_mayor",
                "margin_1",
                "inter_1",
                "margin_2",
                "inter_2",
                "listenplatz_norm",
                "incumbent_council",
                "age",
                "wahlbet",
                "log_bevoelkerung",
            ],
        )
        for model_name, formula in formulas.items():
            table, _ = fit_wls(sub, formula, "tri_w", "gkz")
            row = extract_term_row(table, "female_mayor")
            row = row.to_frame().T
            row.insert(0, "model", model_name)
            row.insert(0, "bandwidth", bandwidth)
            results.append(row)
    return pd.concat(results, ignore_index=True)


def interaction_all_women(df: pd.DataFrame, bandwidths: list[float]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for bandwidth in bandwidths:
        sub = df[(df["rdd_sample"] == 1) & (df["female"] == 1) & (df["margin_1"].abs() <= bandwidth)].copy()
        sub["other_party"] = 1.0 - pd.to_numeric(sub["joint_party"], errors="coerce")
        sub["tri_w"] = triangular_weights(sub["margin_1"], bandwidth)
        sub = prepare_numeric(
            sub,
            [
                "gewinn_norm",
                "female_mayor",
                "other_party",
                "margin_1",
                "inter_1",
                "margin_2",
                "inter_2",
                "listenplatz_norm",
            ],
        )
        formula = "gewinn_norm ~ female_mayor * other_party + margin_1 + inter_1 + margin_2 + inter_2 + listenplatz_norm"
        table, _ = fit_wls(sub, formula, "tri_w", "gkz")
        for term in ["female_mayor", "other_party", "female_mayor:other_party"]:
            row = extract_term_row(table, term).to_frame().T
            row.insert(0, "term_group", term)
            row.insert(0, "bandwidth", bandwidth)
            rows.append(row)
    return pd.concat(rows, ignore_index=True)


def dynamic_models(df: pd.DataFrame, bandwidths: list[float], outcome_name: str) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for bandwidth in bandwidths:
        sub = df[(df["female"] == 1) & (df["margin_1"].abs() <= bandwidth)].copy()
        sub["tri_w"] = triangular_weights(sub["margin_1"], bandwidth)
        sub = prepare_numeric(sub, [outcome_name, "female_mayor", "margin_1", "inter_1", "margin_2", "inter_2"])
        formula = f"{outcome_name} ~ female_mayor + margin_1 + inter_1 + margin_2 + inter_2"
        table, _ = fit_wls(sub, formula, "tri_w", "gkz")
        row = extract_term_row(table, "female_mayor").to_frame().T
        row.insert(0, "bandwidth", bandwidth)
        rows.append(row)
    return pd.concat(rows, ignore_index=True)


def subgroup_models(df: pd.DataFrame, bandwidth: float) -> pd.DataFrame:
    sub = df[(df["rdd_sample"] == 1) & (df["female"] == 1) & (df["joint_party"] == 0) & (df["margin_1"].abs() <= bandwidth)].copy()
    sub["tri_w"] = triangular_weights(sub["margin_1"], bandwidth)
    sub = prepare_numeric(
        sub,
        [
            "gewinn_norm",
            "female_mayor",
            "margin_1",
            "inter_1",
            "margin_2",
            "inter_2",
            "listenplatz_norm",
            "incumbent_council",
            "voteshare",
            "mean_frau_combined",
            "log_bevoelkerung",
        ],
    )

    formula = "gewinn_norm ~ female_mayor + margin_1 + inter_1 + margin_2 + inter_2 + listenplatz_norm"
    outputs: list[dict[str, object]] = []

    sub["incumbency_group"] = np.where(sub["incumbent_council"] == 1, "incumbent", "non_incumbent")
    sub["rank_third"] = pd.qcut(sub["listenplatz_norm"], 3, labels=["top_third", "middle_third", "bottom_third"], duplicates="drop")

    if sub["voteshare"].notna().sum() > 0:
        vote_med = sub["voteshare"].median(skipna=True)
        sub["voteshare_group"] = np.where(sub["voteshare"] >= vote_med, "high_vote_share", "low_vote_share")
    if sub["mean_frau_combined"].notna().sum() > 0:
        frau_med = sub["mean_frau_combined"].median(skipna=True)
        sub["mean_frau_group"] = np.where(sub["mean_frau_combined"] >= frau_med, "more_women_on_list", "fewer_women_on_list")
    if sub["log_bevoelkerung"].notna().sum() > 0:
        pop_med = sub["log_bevoelkerung"].median(skipna=True)
        sub["municipality_size_group"] = np.where(sub["log_bevoelkerung"] >= pop_med, "larger_municipality", "smaller_municipality")

    group_specs = [
        "incumbency_group",
        "rank_third",
        "voteshare_group",
        "mean_frau_group",
        "municipality_size_group",
    ]
    for group_var in group_specs:
        if group_var not in sub.columns:
            continue
        for level, level_df in sub.dropna(subset=[group_var]).groupby(group_var, observed=False):
            if len(level_df) < 30:
                continue
            table, _ = fit_wls(level_df, formula, "tri_w", "gkz")
            row = extract_term_row(table, "female_mayor")
            outputs.append(
                {
                    "subgroup": group_var,
                    "level": level,
                    "coef": float(row.get("coef", np.nan)),
                    "std_err": float(row.get("std_err", np.nan)),
                    "p_value": float(row.get("p_value", np.nan)),
                    "ci_low": float(row.get("ci_low", np.nan)),
                    "ci_high": float(row.get("ci_high", np.nan)),
                    "n_obs": int(row.get("n_obs", 0)),
                    "n_clusters": int(row.get("n_clusters", 0)),
                    "bandwidth": bandwidth,
                }
            )
    return pd.DataFrame(outputs)


def sample_diagnostics(df: pd.DataFrame, bandwidths: list[float]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for bandwidth in bandwidths:
        all_women = df[(df["rdd_sample"] == 1) & (df["female"] == 1) & (df["margin_1"].abs() <= bandwidth)]
        cross_party = all_women[all_women["joint_party"] == 0]
        copartisan = all_women[all_women["joint_party"] == 1]
        rows.append(
            {
                "bandwidth": bandwidth,
                "n_all_women": int(len(all_women)),
                "n_cross_party": int(len(cross_party)),
                "n_copartisan": int(len(copartisan)),
                "cross_party_share": float(len(cross_party) / len(all_women)) if len(all_women) else math.nan,
            }
        )
    return pd.DataFrame(rows)


def plot_subgroups(df: pd.DataFrame, output_path: Path) -> None:
    if df.empty:
        return
    plot_df = df.copy()
    plot_df["label"] = plot_df["subgroup"] + ": " + plot_df["level"].astype(str)
    plot_df = plot_df.sort_values(["subgroup", "coef"], ascending=[True, False]).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(plot_df))))
    y = np.arange(len(plot_df))
    ax.errorbar(plot_df["coef"], y, xerr=[plot_df["coef"] - plot_df["ci_low"], plot_df["ci_high"] - plot_df["coef"]], fmt="o")
    ax.axvline(0.0, linestyle="--")
    ax.set_yticks(y)
    ax.set_yticklabels(plot_df["label"])
    ax.set_xlabel("Estimated female_mayor effect")
    ax.set_title("Cross-party spillover heterogeneity by subgroup")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    outdir = Path(args.output_dir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    main_df = load_dataset(args.main)
    party_df = load_dataset(args.party)
    lagged_df = load_dataset(args.lagged)
    next_df = load_dataset(args.next_election)

    merged = add_common_keys(main_df, party_df)

    diagnostics = sample_diagnostics(merged, args.bandwidths)
    diagnostics.to_csv(outdir / "00_sample_diagnostics.csv", index=False)

    cross_party = benchmark_cross_party(merged, args.bandwidths)
    cross_party.to_csv(outdir / "01_benchmark_ols_cross_party.csv", index=False)

    interaction = interaction_all_women(merged, args.bandwidths)
    interaction.to_csv(outdir / "02_interaction_all_women.csv", index=False)

    lagged = dynamic_models(lagged_df, args.bandwidths, "gewinn_norm")
    lagged.to_csv(outdir / "03_lagged_placebo.csv", index=False)

    next_election = dynamic_models(next_df, args.bandwidths, "gewinn_norm")
    next_election.to_csv(outdir / "04_next_election.csv", index=False)

    subgroup = subgroup_models(merged, args.subgroup_bandwidth)
    subgroup.to_csv(outdir / "05_subgroup_effects.csv", index=False)
    plot_subgroups(subgroup, outdir / "05_subgroup_effects.png")

    summary = {
        "bandwidths": args.bandwidths,
        "subgroup_bandwidth": args.subgroup_bandwidth,
        "files": [
            "00_sample_diagnostics.csv",
            "01_benchmark_ols_cross_party.csv",
            "02_interaction_all_women.csv",
            "03_lagged_placebo.csv",
            "04_next_election.csv",
            "05_subgroup_effects.csv",
            "05_subgroup_effects.png",
        ],
        "notes": [
            "Bandwidths are interpreted in percentage points because margin_1 is stored on that scale.",
            "mean_frau_combined uses party-file values when available and falls back to candidate-level construction from main_dataset.",
            "Use the benchmark cross-party and interaction outputs as the identification anchor; treat subgroup patterns as exploratory but disciplined heterogeneity evidence.",
        ],
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote extension outputs to: {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
