#!/usr/bin/env python3
"""
run_full_replication_v4_research_auditor.py
===========================================

Research-grade replication runner and auditor for `ThePythonicProject`.

This script executes the Python replication pipeline, compares the generated
Python outputs against the original STATA replication package, and produces a
comprehensive audit report suitable for research workflows.

Core capabilities
-----------------
1. Run all detected Python table scripts or the project-level table launcher.
2. Run all detected Python figure scripts or the project-level figure launcher.
3. Run the project's test suite with pytest.
4. Compare Python table outputs against STATA reference outputs.
5. Compute a global Replication Index (%).
6. Compute interpretable sub-scores:
   - execution score
   - test score
   - table text similarity
   - table numeric fidelity
   - table coverage
7. Produce structured reports:
   - Markdown executive report
   - JSON machine-readable report
   - CSV detailed table comparison
   - CSV figure diagnostic inventory
   - CSV coefficient-level comparison
   - manifest.json
   - full logs for every executed step

Important methodological rule
-----------------------------
Figures are treated as supplementary diagnostics only.
They are NOT used as one-to-one replication targets and they do NOT contribute
to the Replication Index. This is intentional: figure files can differ across
platforms, renderers, formats, fonts, metadata, and export pipelines without
changing the substantive econometric conclusions.

Therefore, the replication judgment in this script is based on:
- successful execution,
- automated tests,
- table text similarity,
- numerical fidelity,
- table coverage.

Important limitation
--------------------
This script is an automation and audit tool. It does NOT prove econometric
equivalence on its own. A strong score suggests the Python pipeline is close to
the STATA package, but final validation still requires methodological review.

Typical usage
-------------
From the project root:

    python run_full_replication_v4_research_auditor.py

Or:

    python run_full_replication_v4_research_auditor.py --project-root .

Useful options:

    --numeric-tolerance 1e-4
    --skip-tests
    --skip-figures
    --skip-tables
    --strict

Outputs
-------
By default, the script writes to:

    analysis/full_run_report_v4/

Contents:
    replication_report.md
    replication_report.json
    table_comparison_details.csv
    figure_diagnostic_details.csv
    coefficient_comparison_details.csv
    manifest.json
    logs/

Replication index interpretation
--------------------------------
Default weights:
- 25% execution success
- 15% test suite success
- 25% table text similarity
- 25% table numeric fidelity
- 10% coverage of comparable tables

Suggested reading:
- 90-100: very strong technical replication
- 75-89 : solid replication with remaining differences
- 50-74 : partial replication
- below 50: fragile or incomplete replication
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    """Store execution results for one pipeline step."""
    name: str
    command: List[str]
    returncode: int
    success: bool
    stdout_log: str
    stderr_log: str
    duration_seconds: float


@dataclass
class TableComparison:
    """Detailed comparison between one Python table and one STATA table."""
    python_file: str
    stata_file: str
    paired_by: str
    exact_text_match: bool
    text_similarity: float
    python_number_count: int
    stata_number_count: int
    common_number_count: int
    max_abs_diff: Optional[float]
    mean_abs_diff: Optional[float]
    median_abs_diff: Optional[float]
    rmse: Optional[float]
    within_tolerance_ratio: Optional[float]
    fully_within_tolerance: bool
    signed_bias: Optional[float]
    notes: str


@dataclass
class FigureExecutionRecord:
    """
    Diagnostic-only record describing figure availability and execution context.

    Why this exists:
    ----------------
    In this replication framework, figures are treated as supplementary outputs.
    They are useful for documenting what the Python project generated and what
    exists in the original STATA package, but they are not reliable objects for
    one-to-one replication scoring.

    Why figures are excluded from strict replication scoring:
    ---------------------------------------------------------
    Figure files often differ for reasons that are not econometrically
    meaningful:
    - file format changes (PNG vs PDF vs SVG),
    - rendering backend differences,
    - metadata differences,
    - font substitution,
    - platform-dependent export behavior,
    - image compression and timestamp differences.

    Therefore, figure comparison should not influence the core replication
    assessment. The substantive replication judgment should be based on:
    - successful execution,
    - automated tests,
    - table content,
    - numerical agreement,
    - table coverage.

    Fields:
    -------
    python_figure_count:
        Number of figure files detected in the Python project outputs.

    stata_figure_count:
        Number of figure files detected in the original STATA package.

    python_figure_files:
        Inventory of detected Python-side figure files.

    stata_figure_files:
        Inventory of detected STATA-side figure files.

    notes:
        Human-readable explanation of how figure outputs are treated in the
        analysis.
    """
    python_figure_count: int
    stata_figure_count: int
    python_figure_files: List[str]
    stata_figure_files: List[str]
    notes: str


@dataclass
class CoefficientRow:
    """Coefficient-style row comparison from extracted numeric sequences."""
    table_name: str
    position: int
    python_value: Optional[float]
    stata_value: Optional[float]
    abs_diff: Optional[float]
    within_tolerance: Optional[bool]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

NUMBER_PATTERN = re.compile(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?')


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_text_safely(path: Path) -> str:
    encodings = ('utf-8', 'latin-1', 'cp1252')
    for enc in encodings:
        try:
            return path.read_text(encoding=enc, errors='strict')
        except Exception:
            continue
    return path.read_text(encoding='utf-8', errors='ignore')


def extract_numbers(text: str) -> List[float]:
    values: List[float] = []
    for m in NUMBER_PATTERN.finditer(text):
        try:
            v = float(m.group(0))
            if math.isfinite(v):
                values.append(v)
        except Exception:
            pass
    return values


def sequence_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def safe_mean(values: Sequence[float]) -> Optional[float]:
    return statistics.mean(values) if values else None


def safe_median(values: Sequence[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def safe_rmse(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return math.sqrt(sum(v * v for v in values) / len(values))


def normalize_stem(path: Path) -> str:
    stem = path.stem.lower()
    stem = stem.replace('parta', 'parta').replace('partb', 'partb')
    stem = stem.replace('_original', '')
    stem = re.sub(r'[^a-z0-9]+', '', stem)
    return stem


def table_family_name(path: Path) -> str:
    parts = [p.lower() for p in path.parts]
    for p in parts:
        if re.fullmatch(r'table[a-z0-9]+', p):
            return p
    return normalize_stem(path)


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def relativize(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def run_command(
    command: List[str],
    cwd: Path,
    env: Dict[str, str],
    log_dir: Path,
    name: str,
) -> StepResult:
    """
    Run a subprocess while streaming stdout/stderr live to the console and
    simultaneously saving both streams to log files.

    Why this patched version is needed
    ----------------------------------
    The previous implementation used:

        subprocess.run(..., capture_output=True)

    which buffers all child-process output until the subprocess finishes.
    For long-running steps such as:

    - generate_all_tables.py
    - generate_all_figures.py
    - pytest

    this makes the auditor appear frozen.

    This version instead:
    - prints a clear [RUNNING] banner,
    - streams stdout live,
    - streams stderr live,
    - writes both streams to logs,
    - prints a final [DONE] summary with return code and duration.

    Notes on implementation
    -----------------------
    Two reader threads are used so stdout and stderr can be consumed safely on
    Windows without blocking one another.
    """
    import time
    from threading import Thread

    ensure_dir(log_dir)

    stdout_log = log_dir / f"{name}.stdout.log"
    stderr_log = log_dir / f"{name}.stderr.log"

    start = time.time()

    print("\n" + "-" * 100, flush=True)
    print(f"[RUNNING] {name}", flush=True)
    print(f"Command: {' '.join(command)}", flush=True)
    print(f"Working directory: {cwd}", flush=True)
    print("-" * 100, flush=True)

    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    def _stream_reader(pipe, file_handle, is_stderr: bool = False) -> None:
        """
        Read one subprocess stream line by line, print it live, and write it
        to the corresponding log file.
        """
        try:
            for line in iter(pipe.readline, ""):
                if not line:
                    break
                if is_stderr:
                    print(line, end="", file=sys.stderr, flush=True)
                else:
                    print(line, end="", flush=True)
                file_handle.write(line)
                file_handle.flush()
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    with stdout_log.open("w", encoding="utf-8") as out_f, stderr_log.open("w", encoding="utf-8") as err_f:
        stdout_thread = Thread(
            target=_stream_reader,
            args=(proc.stdout, out_f, False),
            daemon=True,
        )
        stderr_thread = Thread(
            target=_stream_reader,
            args=(proc.stderr, err_f, True),
            daemon=True,
        )

        stdout_thread.start()
        stderr_thread.start()

        returncode = proc.wait()

        stdout_thread.join()
        stderr_thread.join()

    duration = time.time() - start

    print("-" * 100, flush=True)
    print(
        f"[DONE] {name} | return code={returncode} | duration={duration:.2f}s",
        flush=True,
    )
    print("-" * 100 + "\n", flush=True)

    return StepResult(
        name=name,
        command=command,
        returncode=returncode,
        success=(returncode == 0),
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
        duration_seconds=duration,
    )

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_python_scripts(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    scripts = []
    for p in folder.rglob("*.py"):
        if p.name.startswith("__"):
            continue
        scripts.append(p)
    return sorted(scripts)


def discover_table_scripts(project_root: Path) -> List[Path]:
    preferred = project_root / "results" / "tables"
    scripts = discover_python_scripts(preferred)
    scripts = [p for p in scripts if p.name.lower() not in {"__init__.py"}]
    scripts = [p for p in scripts if "test" not in p.name.lower()]
    return scripts


def discover_figure_scripts(project_root: Path) -> List[Path]:
    candidates = [
        project_root / "results" / "figures",
        project_root / "figures",
    ]
    out: List[Path] = []
    for c in candidates:
        out.extend(discover_python_scripts(c))
    unique = sorted(set(out))
    unique = [p for p in unique if "test" not in p.name.lower()]
    return unique


def discover_python_table_outputs(project_root: Path) -> List[Path]:
    root = project_root / "results" / "tables"
    if not root.exists():
        return []
    allowed = {".txt", ".csv", ".tsv", ".tex", ".md", ".xlsx", ".xls"}
    return sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed])


def discover_python_figure_outputs(project_root: Path) -> List[Path]:
    roots = [project_root / "results" / "figures", project_root / "figures"]
    allowed = {".png", ".pdf", ".jpg", ".jpeg", ".svg"}
    out: List[Path] = []
    for root in roots:
        if root.exists():
            out.extend([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed])
    return sorted(set(out))


def discover_stata_table_outputs(project_root: Path) -> List[Path]:
    root = project_root / "stata_original" / "data" / "results_tables"
    if not root.exists():
        return []
    allowed = {".txt", ".csv", ".tsv", ".tex", ".md", ".xlsx", ".xls"}
    return sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed])


def discover_stata_figure_outputs(project_root: Path) -> List[Path]:
    root = project_root / "stata_original" / "data" / "results_figures"
    if not root.exists():
        return []
    allowed = {".png", ".pdf", ".jpg", ".jpeg", ".svg"}
    return sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed])


# ---------------------------------------------------------------------------
# Pairing heuristics
# ---------------------------------------------------------------------------

def pair_table_files(python_files: List[Path], stata_files: List[Path]) -> List[Tuple[Path, Path, str]]:
    """
    Pair Python and STATA table files for comparison.

    Important scope restriction:
    This function is intentionally table-specific. It must not be used for
    figures, because the replication framework no longer performs one-to-one
    figure matching.
    """
    pairs: List[Tuple[Path, Path, str]] = []
    used_stata: set[Path] = set()

    stata_by_family: Dict[str, List[Path]] = {}
    for s in stata_files:
        stata_by_family.setdefault(table_family_name(s), []).append(s)

    for py in python_files:
        py_family = table_family_name(py)
        py_norm = normalize_stem(py)

        candidates = [s for s in stata_by_family.get(py_family, []) if s not in used_stata]
        chosen = None
        paired_by = ""

        # 1) exact normalized stem inside same family
        for s in candidates:
            if normalize_stem(s) == py_norm:
                chosen = s
                paired_by = "family+normalized_stem"
                break

        # 2) same suffix / name similarity inside family
        if chosen is None and candidates:
            scored = sorted(
                ((sequence_similarity(py.name.lower(), s.name.lower()), s) for s in candidates),
                key=lambda x: x[0],
                reverse=True,
            )
            if scored and scored[0][0] >= 0.45:
                chosen = scored[0][1]
                paired_by = "family+filename_similarity"

        # 3) global fallback by stem similarity
        if chosen is None:
            remaining = [s for s in stata_files if s not in used_stata]
            scored = sorted(
                ((sequence_similarity(py_norm, normalize_stem(s)), s) for s in remaining),
                key=lambda x: x[0],
                reverse=True,
            )
            if scored and scored[0][0] >= 0.55:
                chosen = scored[0][1]
                paired_by = "global_normalized_stem_similarity"

        if chosen is not None:
            used_stata.add(chosen)
            pairs.append((py, chosen, paired_by))

    return pairs


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------

def compare_table_files(py: Path, st: Path, paired_by: str, tolerance: float) -> Tuple[TableComparison, List[CoefficientRow]]:
    py_text = read_text_safely(py)
    st_text = read_text_safely(st)

    exact_text_match = py_text == st_text
    text_similarity = sequence_similarity(py_text, st_text)

    py_nums = extract_numbers(py_text)
    st_nums = extract_numbers(st_text)

    common_n = min(len(py_nums), len(st_nums))
    diffs: List[float] = []
    signed: List[float] = []
    coeff_rows: List[CoefficientRow] = []

    for i in range(max(len(py_nums), len(st_nums))):
        py_v = py_nums[i] if i < len(py_nums) else None
        st_v = st_nums[i] if i < len(st_nums) else None
        abs_diff = abs(py_v - st_v) if py_v is not None and st_v is not None else None
        within_tol = (abs_diff <= tolerance) if abs_diff is not None else None
        if abs_diff is not None:
            diffs.append(abs_diff)
            signed.append(py_v - st_v)
        coeff_rows.append(
            CoefficientRow(
                table_name=py.parent.name,
                position=i + 1,
                python_value=py_v,
                stata_value=st_v,
                abs_diff=abs_diff,
                within_tolerance=within_tol,
            )
        )

    within_ratio = None
    fully_within_tolerance = False
    if diffs:
        within_ratio = sum(d <= tolerance for d in diffs) / len(diffs)
        fully_within_tolerance = all(d <= tolerance for d in diffs)

    comparison = TableComparison(
        python_file=str(py),
        stata_file=str(st),
        paired_by=paired_by,
        exact_text_match=exact_text_match,
        text_similarity=text_similarity,
        python_number_count=len(py_nums),
        stata_number_count=len(st_nums),
        common_number_count=common_n,
        max_abs_diff=max(diffs) if diffs else None,
        mean_abs_diff=safe_mean(diffs),
        median_abs_diff=safe_median(diffs),
        rmse=safe_rmse(diffs),
        within_tolerance_ratio=within_ratio,
        fully_within_tolerance=fully_within_tolerance,
        signed_bias=safe_mean(signed),
        notes="" if common_n > 0 else "No comparable numeric content extracted.",
    )
    return comparison, coeff_rows


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_execution(step_results: List[StepResult]) -> float:
    if not step_results:
        return 0.0
    return sum(1.0 for s in step_results if s.success) / len(step_results)


def score_tests(pytest_result: Optional[StepResult]) -> float:
    if pytest_result is None:
        return 0.0
    return 1.0 if pytest_result.success else 0.0


def score_text_similarity(comparisons: List[TableComparison]) -> float:
    vals = [c.text_similarity for c in comparisons]
    return safe_mean(vals) or 0.0


def score_numeric_fidelity(comparisons: List[TableComparison], tolerance: float) -> float:
    vals = []
    for c in comparisons:
        if c.within_tolerance_ratio is not None:
            vals.append(c.within_tolerance_ratio)
        elif c.max_abs_diff is None:
            vals.append(0.0)
        else:
            # Smooth fallback if only aggregate data exist
            vals.append(max(0.0, 1.0 - (c.max_abs_diff / max(tolerance, 1e-12))))
    return safe_mean(vals) or 0.0


def score_table_coverage(python_count: int, stata_count: int, paired_count: int) -> float:
    """
    Compute table coverage for the replication assessment.

    Coverage measures how many table outputs could be paired between the Python
    project and the original STATA package, relative to the larger of the two
    inventories. Figures are intentionally excluded from this logic.
    """
    denom = max(python_count, stata_count, 1)
    return paired_count / denom


def compute_replication_index(
    execution_score: float,
    test_score: float,
    text_score: float,
    numeric_score: float,
    coverage_score: float,
) -> Dict[str, float]:
    """
    Compute the core replication index.

    Figures are explicitly excluded because exact visual or binary matching is
    not required for a valid econometric replication.
    """
    weights = {
        "execution": 0.25,
        "tests": 0.15,
        "text": 0.25,
        "numeric": 0.25,
        "coverage": 0.10,
    }
    total = (
        execution_score * weights["execution"] +
        test_score * weights["tests"] +
        text_score * weights["text"] +
        numeric_score * weights["numeric"] +
        coverage_score * weights["coverage"]
    )
    return {
        "execution_score": execution_score,
        "test_score": test_score,
        "text_score": text_score,
        "numeric_score": numeric_score,
        "coverage_score": coverage_score,
        "replication_index_raw": total,
        "replication_index_percent": total * 100.0,
        "figures_included_in_index": False,
    }


def interpret_score(score_percent: float) -> str:
    if score_percent >= 90:
        return "Very strong technical replication"
    if score_percent >= 75:
        return "Strong replication with remaining differences"
    if score_percent >= 50:
        return "Partial replication"
    if score_percent >= 25:
        return "Weak replication"
    return "Replication failure / highly incomplete replication"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    ensure_dir(path.parent)
    if not rows:
        path.write_text("", encoding='utf-8')
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_markdown_report(
    report_dir: Path,
    project_root: Path,
    table_comparisons: List[TableComparison],
    figure_execution: FigureExecutionRecord,
    coeff_rows: List[CoefficientRow],
    step_results: List[StepResult],
    pytest_result: Optional[StepResult],
    score: Dict[str, float],
    python_tables: List[Path],
    stata_tables: List[Path],
    python_figures: List[Path],
    stata_figures: List[Path],
    tolerance: float,
) -> str:
    paired_tables = len(table_comparisons)
    exact_table_matches = sum(c.exact_text_match for c in table_comparisons)
    full_tol_tables = sum(c.fully_within_tolerance for c in table_comparisons)
    avg_text = safe_mean([c.text_similarity for c in table_comparisons]) or 0.0
    avg_num = safe_mean([c.within_tolerance_ratio for c in table_comparisons if c.within_tolerance_ratio is not None]) or 0.0
    interpretation = interpret_score(score["replication_index_percent"])

    lines: List[str] = []
    lines.append("# Replication Audit Report (v4)")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Replication Index:** {score['replication_index_percent']:.2f}%")
    lines.append(f"- **Interpretation:** {interpretation}")
    lines.append(f"- **Execution score:** {score['execution_score']:.3f}")
    lines.append(f"- **Test score:** {score['test_score']:.3f}")
    lines.append(f"- **Table text similarity score:** {score['text_score']:.3f}")
    lines.append(f"- **Table numeric fidelity score:** {score['numeric_score']:.3f}")
    lines.append(f"- **Coverage score:** {score['coverage_score']:.3f}")
    lines.append("- **Figures included in replication score:** No")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("This audit runs the Python replication pipeline, captures execution outcomes,")
    lines.append("and compares generated Python outputs to reference outputs from the original")
    lines.append("STATA replication package bundled in `stata_original/`.")
    lines.append("")
    lines.append("For tables, the report uses two comparison layers:")
    lines.append("")
    lines.append("1. **Text similarity** using sequence matching on full file contents.")
    lines.append("2. **Numeric fidelity** using extracted numeric sequences matched by position.")
    lines.append("")
    lines.append(f"The numeric tolerance used in this run was **{tolerance:g}**.")
    lines.append("")
    lines.append("Figures are **not part of the replication score** and are **not evaluated via")
    lines.append("one-for-one matching**. They are tracked only as supplementary execution and")
    lines.append("inventory diagnostics.")
    lines.append("")
    lines.append("## Pipeline Execution")
    lines.append("")
    for s in step_results:
        status = "PASS" if s.success else "FAIL"
        lines.append(f"- **{s.name}:** {status} (return code {s.returncode}, {s.duration_seconds:.2f}s)")
    if pytest_result is not None:
        status = "PASS" if pytest_result.success else "FAIL"
        lines.append(f"- **pytest:** {status} (return code {pytest_result.returncode}, {pytest_result.duration_seconds:.2f}s)")
    lines.append("")
    lines.append("## Coverage Summary")
    lines.append("")
    lines.append(f"- Python tables detected: **{len(python_tables)}**")
    lines.append(f"- STATA tables detected: **{len(stata_tables)}**")
    lines.append(f"- Paired table files: **{paired_tables}**")
    lines.append(f"- Python figures detected: **{len(python_figures)}**")
    lines.append(f"- STATA figures detected: **{len(stata_figures)}**")
    lines.append("- Paired figure files: **not applicable**")
    lines.append("")
    lines.append("## Table Comparison Summary")
    lines.append("")
    lines.append(f"- Exact text matches: **{exact_table_matches} / {paired_tables}**")
    lines.append(f"- Full numeric matches within tolerance: **{full_tol_tables} / {paired_tables}**")
    lines.append(f"- Average text similarity: **{avg_text:.3f}**")
    lines.append(f"- Average within-tolerance ratio: **{avg_num:.3f}**")
    lines.append("")
    lines.append("| Python table | STATA table | Text sim. | Max abs diff | Mean abs diff | Within tol. ratio |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for c in table_comparisons[:50]:
        lines.append(
            f"| `{Path(c.python_file).name}` | `{Path(c.stata_file).name}` | "
            f"{c.text_similarity:.3f} | "
            f"{'' if c.max_abs_diff is None else f'{c.max_abs_diff:.6g}'} | "
            f"{'' if c.mean_abs_diff is None else f'{c.mean_abs_diff:.6g}'} | "
            f"{'' if c.within_tolerance_ratio is None else f'{c.within_tolerance_ratio:.3f}'} |"
        )
    lines.append("")
    lines.append("## Coefficient-Level Diagnostic")
    lines.append("")
    coeff_diffs = [r.abs_diff for r in coeff_rows if r.abs_diff is not None]
    coeff_within = [r.within_tolerance for r in coeff_rows if r.within_tolerance is not None]
    if coeff_diffs:
        lines.append(f"- Comparable numeric positions: **{len(coeff_diffs)}**")
        lines.append(f"- Mean coefficient absolute difference: **{safe_mean(coeff_diffs):.6g}**")
        lines.append(f"- Median coefficient absolute difference: **{safe_median(coeff_diffs):.6g}**")
        lines.append(f"- Max coefficient absolute difference: **{max(coeff_diffs):.6g}**")
        lines.append(f"- Share within tolerance: **{sum(bool(x) for x in coeff_within) / len(coeff_within):.3f}**")
    else:
        lines.append("No coefficient-style comparable numeric sequence was extracted.")
    lines.append("")
    lines.append("## Figure Diagnostic")
    lines.append("")
    lines.append(f"- Python figures detected: **{figure_execution.python_figure_count}**")
    lines.append(f"- STATA figures detected: **{figure_execution.stata_figure_count}**")
    lines.append(f"- Notes: {figure_execution.notes}")
    lines.append("")
    lines.append("## Diagnostics")
    lines.append("")
    if not step_results and pytest_result is None:
        lines.append("- No executable Python pipeline step was detected.")
    else:
        failed = [s.name for s in step_results if not s.success]
        if pytest_result is not None and not pytest_result.success:
            failed.append("pytest")
        if failed:
            lines.append(f"- Failed steps detected: {', '.join(failed)}.")
        else:
            lines.append("- No failing process step was detected.")
    if table_comparisons:
        weak = [c for c in table_comparisons if (c.within_tolerance_ratio or 0.0) < 0.5]
        if weak:
            lines.append(f"- {len(weak)} table pair(s) show weak numerical agreement (< 50% within tolerance).")
        else:
            lines.append("- Table-level numerical agreement is at least moderate across all paired tables.")
    else:
        lines.append("- No paired table comparison could be produced.")
    lines.append("")
    lines.append("## Recommended Next Steps")
    lines.append("")
    lines.append("1. Inspect low-scoring tables in `table_comparison_details.csv`.")
    lines.append("2. Review coefficient-level discrepancies in `coefficient_comparison_details.csv`.")
    lines.append("3. Check log files under `logs/` for failing steps.")
    lines.append("4. If numerical gaps remain large, compare the Python specification against the original STATA `.do` files.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Run and audit the full replication pipeline.")
    parser.add_argument("--project-root", default=".", help="Project root directory.")
    parser.add_argument("--numeric-tolerance", type=float, default=1e-4, help="Tolerance for numeric comparison.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest execution.")
    parser.add_argument("--skip-figures", action="store_true", help="Skip figure script execution and figure comparison.")
    parser.add_argument("--skip-tables", action="store_true", help="Skip table script execution and table comparison.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero if any pipeline step fails.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    report_dir = project_root / "analysis" / "full_run_report_v4"
    log_dir = report_dir / "logs"
    ensure_dir(report_dir)
    ensure_dir(log_dir)

    env = os.environ.copy()
    src_dir = project_root / "src"
    if src_dir.exists():
        current = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(src_dir) + (os.pathsep + current if current else "")

        step_results: List[StepResult] = []

    print("\n" + "=" * 100, flush=True)
    print("FULL REPLICATION AUDIT (v4) - LIVE EXECUTION", flush=True)
    print("=" * 100, flush=True)
    print(f"Project root: {project_root}", flush=True)
    print(f"Report directory: {report_dir}", flush=True)
    print(f"Numeric tolerance: {args.numeric_tolerance:g}", flush=True)
    print(f"Skip tables: {args.skip_tables}", flush=True)
    print(f"Skip figures: {args.skip_figures}", flush=True)
    print(f"Skip tests: {args.skip_tests}", flush=True)
    print("=" * 100 + "\n", flush=True)

    # ------------------------------------------------------------------
    # STEP 1 - TABLE GENERATION
    # ------------------------------------------------------------------
    print("=" * 100, flush=True)
    print("STEP 1 - TABLE GENERATION", flush=True)
    print("=" * 100, flush=True)

    if not args.skip_tables:
        master = project_root / "generate_all_tables.py"
        if master.exists():
            step_results.append(
                run_command(
                    [sys.executable, str(master)],
                    cwd=project_root,
                    env=env,
                    log_dir=log_dir,
                    name="generate_all_tables",
                )
            )
        else:
            table_scripts = discover_table_scripts(project_root)
            print(f"[INFO] Discovered {len(table_scripts)} table script(s).", flush=True)
            for i, script in enumerate(table_scripts, start=1):
                print(
                    f"[INFO] Launching table script {i}/{len(table_scripts)}: "
                    f"{relativize(script, project_root)}",
                    flush=True,
                )
                step_results.append(
                    run_command(
                        [sys.executable, str(script)],
                        cwd=project_root,
                        env=env,
                        log_dir=log_dir,
                        name=f"table_{script.parent.name}_{script.stem}",
                    )
                )
    else:
        print("[SKIP] Table generation skipped by user option.", flush=True)

    # ------------------------------------------------------------------
    # STEP 2 - FIGURE GENERATION
    # ------------------------------------------------------------------
    print("\n" + "=" * 100, flush=True)
    print("STEP 2 - FIGURE GENERATION", flush=True)
    print("=" * 100, flush=True)

    if not args.skip_figures:
        master_figures = project_root / "generate_all_figures.py"
        if master_figures.exists():
            step_results.append(
                run_command(
                    [sys.executable, str(master_figures)],
                    cwd=project_root,
                    env=env,
                    log_dir=log_dir,
                    name="generate_all_figures",
                )
            )
        else:
            figure_scripts = discover_figure_scripts(project_root)
            print(f"[INFO] Discovered {len(figure_scripts)} figure script(s).", flush=True)
            for i, script in enumerate(figure_scripts, start=1):
                print(
                    f"[INFO] Launching figure script {i}/{len(figure_scripts)}: "
                    f"{relativize(script, project_root)}",
                    flush=True,
                )
                step_results.append(
                    run_command(
                        [sys.executable, str(script)],
                        cwd=project_root,
                        env=env,
                        log_dir=log_dir,
                        name=f"figure_{script.parent.name}_{script.stem}",
                    )
                )
    else:
        print("[SKIP] Figure generation skipped by user option.", flush=True)

    # ------------------------------------------------------------------
    # STEP 3 - TEST SUITE
    # ------------------------------------------------------------------
    print("\n" + "=" * 100, flush=True)
    print("STEP 3 - TEST SUITE", flush=True)
    print("=" * 100, flush=True)

    pytest_result: Optional[StepResult] = None
    if not args.skip_tests:
        pytest_result = run_command(
            [sys.executable, "-m", "pytest"],
            cwd=project_root,
            env=env,
            log_dir=log_dir,
            name="pytest",
        )
    else:
        print("[SKIP] Pytest skipped by user option.", flush=True)

    # ------------------------------------------------------------------
    # STEP 4 - DISCOVER GENERATED OUTPUTS
    # ------------------------------------------------------------------
    print("\n" + "=" * 100, flush=True)
    print("STEP 4 - DISCOVER GENERATED OUTPUTS", flush=True)
    print("=" * 100, flush=True)

    python_tables = [] if args.skip_tables else discover_python_table_outputs(project_root)
    stata_tables = [] if args.skip_tables else discover_stata_table_outputs(project_root)
    python_figures = [] if args.skip_figures else discover_python_figure_outputs(project_root)
    stata_figures = [] if args.skip_figures else discover_stata_figure_outputs(project_root)

    print(f"[INFO] Python tables detected: {len(python_tables)}", flush=True)
    print(f"[INFO] STATA tables detected: {len(stata_tables)}", flush=True)
    print(f"[INFO] Python figures detected: {len(python_figures)}", flush=True)
    print(f"[INFO] STATA figures detected: {len(stata_figures)}", flush=True)

    # ------------------------------------------------------------------
    # STEP 5 - TABLE PAIRING AND COMPARISON
    # ------------------------------------------------------------------
    print("\n" + "=" * 100, flush=True)
    print("STEP 5 - TABLE PAIRING AND COMPARISON", flush=True)
    print("=" * 100, flush=True)

    table_pairs = pair_table_files(python_tables, stata_tables)
    print(f"[INFO] Paired tables: {len(table_pairs)}", flush=True)

    table_comparisons: List[TableComparison] = []
    coeff_rows: List[CoefficientRow] = []
    for idx, (py, st, paired_by) in enumerate(table_pairs, start=1):
        print(
            f"[INFO] Comparing table pair {idx}/{len(table_pairs)}: "
            f"{Path(py).name}  <->  {Path(st).name}  [{paired_by}]",
            flush=True,
        )
        cmp_obj, coeffs = compare_table_files(py, st, paired_by, args.numeric_tolerance)
        table_comparisons.append(cmp_obj)
        coeff_rows.extend(coeffs)
        
    table_comparisons: List[TableComparison] = []
    coeff_rows: List[CoefficientRow] = []
    for py, st, paired_by in table_pairs:
        cmp_obj, coeffs = compare_table_files(py, st, paired_by, args.numeric_tolerance)
        table_comparisons.append(cmp_obj)
        coeff_rows.extend(coeffs)

    # Figures are tracked as diagnostics only.
    figure_execution = FigureExecutionRecord(
        python_figure_count=len(python_figures),
        stata_figure_count=len(stata_figures),
        python_figure_files=[str(p) for p in python_figures],
        stata_figure_files=[str(p) for p in stata_figures],
        notes=(
            "Inventory only. Figures are excluded from the replication score "
            "and from one-to-one matching."
        ),
    )

    # ------------------------------------------------------------------
    # STEP 6 - SCORING
    # ------------------------------------------------------------------
    print("\n" + "=" * 100, flush=True)
    print("STEP 6 - SCORING", flush=True)
    print("=" * 100, flush=True)

    score = compute_replication_index(
        execution_score=score_execution(step_results),
        test_score=score_tests(pytest_result),
        text_score=score_text_similarity(table_comparisons),
        numeric_score=score_numeric_fidelity(table_comparisons, args.numeric_tolerance),
        coverage_score=score_table_coverage(len(python_tables), len(stata_tables), len(table_pairs)),
    )

        # ------------------------------------------------------------------
    # STEP 7 - WRITING REPORT FILES
    # ------------------------------------------------------------------
    print("\n" + "=" * 100, flush=True)
    print("STEP 7 - WRITING REPORT FILES", flush=True)
    print("=" * 100, flush=True)

    table_rows = [asdict(c) for c in table_comparisons]
    coeff_detail_rows = [asdict(r) for r in coeff_rows]
    write_csv(report_dir / "table_comparison_details.csv", table_rows)
    write_csv(report_dir / "figure_diagnostic_details.csv", [asdict(figure_execution)])
    write_csv(report_dir / "coefficient_comparison_details.csv", coeff_detail_rows)

    # Save manifest / JSON report
    manifest = {
        "project_root": str(project_root),
        "report_dir": str(report_dir),
        "python_tables_detected": len(python_tables),
        "stata_tables_detected": len(stata_tables),
        "paired_tables": len(table_pairs),
        "python_figures_detected": len(python_figures),
        "stata_figures_detected": len(stata_figures),
        "numeric_tolerance": args.numeric_tolerance,
        "figures_included_in_replication_index": False,
        "figure_matching_mode": "disabled",
    }
    write_json(report_dir / "manifest.json", manifest)

    report_json = {
        "manifest": manifest,
        "scores": score,
        "score_interpretation": interpret_score(score["replication_index_percent"]),
        "step_results": [asdict(s) for s in step_results],
        "pytest_result": asdict(pytest_result) if pytest_result is not None else None,
        "table_comparisons": table_rows,
        "figure_diagnostic": asdict(figure_execution),
        "coefficient_comparisons_summary": {
            "count": len([r for r in coeff_rows if r.abs_diff is not None]),
            "mean_abs_diff": safe_mean([r.abs_diff for r in coeff_rows if r.abs_diff is not None]),
            "median_abs_diff": safe_median([r.abs_diff for r in coeff_rows if r.abs_diff is not None]),
            "max_abs_diff": max([r.abs_diff for r in coeff_rows if r.abs_diff is not None], default=None),
            "share_within_tolerance": (
                sum(bool(r.within_tolerance) for r in coeff_rows if r.within_tolerance is not None) /
                max(1, len([r for r in coeff_rows if r.within_tolerance is not None]))
            ),
        },
    }
    write_json(report_dir / "replication_report.json", report_json)

    # Markdown report
    report_md = build_markdown_report(
        report_dir=report_dir,
        project_root=project_root,
        table_comparisons=table_comparisons,
        figure_execution=figure_execution,
        coeff_rows=coeff_rows,
        step_results=step_results,
        pytest_result=pytest_result,
        score=score,
        python_tables=python_tables,
        stata_tables=stata_tables,
        python_figures=python_figures,
        stata_figures=stata_figures,
        tolerance=args.numeric_tolerance,
    )
    (report_dir / "replication_report.md").write_text(report_md, encoding='utf-8')

    # Console summary
    print("\n" + "=" * 100, flush=True)
    print(f"[INFO] Logs written under: {log_dir}", flush=True)
    print(f"[INFO] Markdown report: {report_dir / 'replication_report.md'}", flush=True)
    print(f"[INFO] JSON report: {report_dir / 'replication_report.json'}", flush=True)
    print("=" * 100, flush=True)

    # Console summary
    print("=" * 60)
    print("FULL REPLICATION AUDIT (v4)")
    print("=" * 60)
    print(f"Project root: {project_root}")
    print(f"Replication Index: {score['replication_index_percent']:.2f}%")
    print(f"Interpretation: {interpret_score(score['replication_index_percent'])}")
    print(f"Table pairs: {len(table_pairs)} / max({len(python_tables)}, {len(stata_tables)})")
    print(f"Figure inventory: Python={len(python_figures)}, STATA={len(stata_figures)}")
    print("Figures excluded from replication score: Yes")
    print(f"Report directory: {report_dir}")
    print("=" * 60)

    if args.strict:
        any_failed = any(not s.success for s in step_results) or (pytest_result is not None and not pytest_result.success)
        return 1 if any_failed else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
