from __future__ import annotations

"""
generate_all_tables.py

Main launcher for the replication table-generation pipeline.

Purpose
-------
This script orchestrates the execution of all translated Python table scripts.
It is designed to make the replication workflow more reproducible, testable,
and easier to diagnose.

Core responsibilities
---------------------
1. Locate the project root and canonical input/output directories.
2. Select which table-generation jobs to run.
3. Resolve required datasets for each job.
4. Execute table scripts as subprocesses.
5. Verify that expected output files were created successfully.
6. Persist per-job stdout/stderr logs.
7. Summarize completed, skipped, and failed jobs.

Typical usage
-------------
Run the full pipeline:
    python generate_all_tables.py

Run a reduced smoke test:
    python generate_all_tables.py --smoke-test

Run only one specific table:
    python generate_all_tables.py --jobs Table2/table2.py

Run multiple selected jobs:
    python generate_all_tables.py --jobs Table1/table1_partA.py Table2/table2.py

Stop immediately on first failure:
    python generate_all_tables.py --fail-fast
"""

import argparse
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------
# Local bootstrap for imports
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from meco_replication.paths import (
    data_raw_dir,
    find_project_root,
    resolve_table_dataset,
    results_tables_dir,
)
from meco_replication.runner_utils import (
    build_pythonpath_env,
    configure_logging,
)

# ---------------------------------------------------------------------
# Table job registry
# ---------------------------------------------------------------------
TABLE_JOBS: list[tuple[str, str, list[str]]] = [
    ("Table1", "table1_partA.py", ["main_dataset"]),
    ("Table1", "Table1_partB.py", ["main_dataset"]),
    ("Table2", "table2.py", ["main_dataset"]),
    ("Table3", "Table3.py", ["main_dataset"]),
    ("Table4", "table4_PanelA.py", ["main_dataset"]),
    ("Table4", "table4_PanelB.py", ["main_dataset"]),
    ("Table4", "table4_PanelC.py", ["main_dataset"]),
    ("Table5", "table5.py", ["main_dataset"]),
    ("Table6", "table6_PanelA.py", ["main_dataset"]),
    ("Table6", "table6_PanelB.py", ["main_dataset"]),
    ("Table7", "table7.py", ["main_dataset"]),
    ("Table8", "table8_PanelA.py", ["main_dataset"]),
    ("Table8", "table8_PanelB.py", ["main_dataset"]),
    ("Table9", "table9.py", ["neighbor_regressions_dataset"]),
    ("TableA1", "tableA1.py", ["mayor_election_data"]),
    ("TableA2", "tableA2.py", ["main_dataset"]),
    ("TableA3", "tableA3.py", ["main_dataset"]),
    ("TableA4", "tableA4_PanelA.py", ["mayor_election_data"]),
    ("TableA4", "tableA4_PanelB.py", ["mayor_election_data"]),
    ("TableA5", "tableA5.py", ["main_dataset"]),
    ("TableA6", "tableA6.py", ["mayor_election_data"]),
    ("TableA7", "tableA7.py", ["mayor_election_data"]),
    ("TableA8", "tableA8.py", ["main_dataset"]),
    ("TableA9", "tableA9.py", ["main_dataset"]),
    ("TableA10", "tableA10_PanelA.py", ["main_dataset"]),
    ("TableA10", "tableA10_PanelB.py", ["main_dataset"]),
    ("TableA11", "tableA11.py", ["main_dataset"]),
    ("TableA12", "tableA12.py", ["main_dataset"]),
    ("TableA13", "tableA13_PanelA.py", ["main_dataset"]),
    ("TableA13", "tableA13_PanelB.py", ["main_dataset"]),
    ("TableA13", "tableA13_PanelC.py", ["main_dataset"]),
    ("TableA14", "tableA14_PanelA.py", ["main_dataset"]),
    ("TableA14", "tableA14_PanelB.py", ["main_dataset"]),
    ("TableA14", "tableA14_PanelC.py", ["main_dataset"]),
    ("TableA15", "tableA15.py", ["characteristics_mixed_and_single_gender_municipalities"]),
    ("TableA16", "tableA16.py", ["main_dataset"]),
    ("TableA17", "tableA17_PanelA.py", ["main_dataset"]),
    ("TableA17", "tableA17_PanelB.py", ["main_dataset"]),
    ("TableA17", "tableA17_PanelC.py", ["main_dataset"]),
    #("TableA18", "tableA18.py", ["main_dataset", "neighbor_regressions_dataset"]),
    ("TableA19", "tableA19.py", ["dataset_for_party_level_results"]),
]

UNAVAILABLE_REPLICATION_JOBS = {
    ("TableA18", "tableA18.py"): (
        "Skipping TableA18/tableA18.py. "
        "Table A18 is not claimed as replicated because the original Stata workflow "
        "depends on neighbor_females.dta, which is not included in the public archive."
    ),
}

SMOKE_TEST_JOBS = [
    ("Table1", "table1_partA.py", ["main_dataset"]),
    ("Table2", "table2.py", ["main_dataset"]),
    ("Table3", "Table3.py", ["main_dataset"]),
    ("Table4", "table4_PanelA.py", ["main_dataset"]),
    ("Table9", "table9.py", ["neighbor_regressions_dataset"]),
    ("TableA1", "tableA1.py", ["mayor_election_data"]),
    ("TableA2", "tableA2.py", ["main_dataset"]),
    ("TableA19", "tableA19.py", ["dataset_for_party_level_results"]),
]

OPTIONAL_JOBS_BY_MISSING_STEM = {
    ("TableA18", "tableA18.py", "neighbor_females"): (
        "Skipping TableA18/tableA18.py because neighbor_females is missing."
    ),
}


@dataclass
class JobResult:
    """
    Structured execution record for one table-generation script.
    """

    label: str
    status: str
    duration_seconds: float
    return_code: int | None = None
    note: str = ""
    output_path: Path | None = None
    stdout_log_path: Path | None = None
    stderr_log_path: Path | None = None


def expected_output_path(script_path: Path) -> Path:
    """
    Infer the expected output file produced by a table script.
    """
    legacy_name_map = {
    "table1_partA": "Table1_PartA.txt",
    "Table1_partB": "Table1_PartB.txt",
    "Table3": "table3.txt",

    # observed legacy outputs
    "tableA4_PanelA": "TableA4_PanelA.txt",
    "tableA4_PanelB": "TableA4_PanelB.txt",
    "tableA15": "TableA15.txt",
}

    filename = legacy_name_map.get(script_path.stem, f"{script_path.stem}.txt")
    return script_path.parent / filename


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the launcher.
    """
    base_dir = find_project_root(Path(__file__).resolve().parent)

    parser = argparse.ArgumentParser(
        description="Run translated table-generation scripts."
    )
    parser.add_argument(
        "--datasets-dir",
        default=str(data_raw_dir(base_dir)),
        help="Directory containing input datasets (.dta or .csv).",
    )
    parser.add_argument(
        "--tables-root",
        default=str(results_tables_dir(base_dir)),
        help="Root directory containing table subfolders and scripts.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failed job.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run only a small representative subset of jobs.",
    )
    parser.add_argument(
        "--jobs",
        nargs="*",
        help=(
            "Optional subset of jobs to run, for example "
            "'Table2/table2.py' 'TableA2/tableA2.py'."
        ),
    )

    return parser.parse_args()


def validate_project_paths(datasets_dir: Path, tables_root: Path) -> None:
    """
    Validate that key project directories exist.
    """
    if not datasets_dir.exists():
        raise FileNotFoundError(f"Datasets directory not found: {datasets_dir}")

    if not tables_root.exists():
        raise FileNotFoundError(f"Tables root directory not found: {tables_root}")


def select_jobs(args: argparse.Namespace) -> list[tuple[str, str, list[str]]]:
    """
    Select the list of jobs to run based on CLI arguments.
    """
    jobs = SMOKE_TEST_JOBS if args.smoke_test else TABLE_JOBS

    if args.jobs:
        selected = set(args.jobs)
        jobs = [job for job in jobs if f"{job[0]}/{job[1]}" in selected]

    if not jobs:
        raise ValueError("No jobs selected. Check the values passed to --jobs.")

    return jobs


def sanitize_job_label_for_logfile(label: str) -> str:
    """
    Convert a job label like 'Table2/table2.py' into a filesystem-safe stem.
    """
    return label.replace("/", "__").replace("\\", "__").replace(".py", "")


def write_job_logs(
    *,
    tables_root: Path,
    label: str,
    stdout_text: str,
    stderr_text: str,
) -> tuple[Path, Path]:
    """
    Save per-job stdout/stderr logs under results/tables/_logs.
    """
    logs_dir = tables_root / "_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    stem = sanitize_job_label_for_logfile(label)
    stdout_log_path = logs_dir / f"{stem}.stdout.log"
    stderr_log_path = logs_dir / f"{stem}.stderr.log"

    stdout_log_path.write_text(stdout_text or "", encoding="utf-8")
    stderr_log_path.write_text(stderr_text or "", encoding="utf-8")

    return stdout_log_path, stderr_log_path


def run_subprocess_with_capture(
    *,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """
    Run a child Python script while capturing stdout and stderr.
    """
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_table_job(
    *,
    base_dir: Path,
    datasets_dir: Path,
    tables_root: Path,
    child_env: dict[str, str],
    logger: logging.Logger,
    table_dir_name: str,
    script_name: str,
    dataset_stems: list[str],
) -> JobResult:
    """
    Execute a single table-generation job.

    This function:
    1. Resolves required input datasets.
    2. Launches the target script as a subprocess.
    3. Prints and saves real stdout/stderr.
    4. Verifies that the expected output file exists and is non-empty.
    """
    label = f"{table_dir_name}/{script_name}"
    script_path = tables_root / table_dir_name / script_name

    if not script_path.exists():
        raise FileNotFoundError(f"Missing table script: {script_path}")

    start = time.perf_counter()

    data_paths: list[Path] = []
    for stem in dataset_stems:
        try:
            data_paths.append(resolve_table_dataset(datasets_dir, stem))
        except FileNotFoundError:
            key = (table_dir_name, script_name, stem)
            if key in OPTIONAL_JOBS_BY_MISSING_STEM:
                note = OPTIONAL_JOBS_BY_MISSING_STEM[key]
                logger.warning(note)
                return JobResult(
                    label=label,
                    status="skipped",
                    duration_seconds=time.perf_counter() - start,
                    note=note,
                )
            raise

    output_dir = script_path.parent

    cmd = [
        sys.executable,
        str(script_path),
        *[str(path) for path in data_paths],
        "--output-dir",
        str(output_dir),
    ]

    logger.info("Running %s", " ".join(cmd))
    result = run_subprocess_with_capture(cmd=cmd, cwd=base_dir, env=child_env)

    duration = time.perf_counter() - start
    output_path = expected_output_path(script_path)

    stdout_log_path, stderr_log_path = write_job_logs(
        tables_root=tables_root,
        label=label,
        stdout_text=result.stdout or "",
        stderr_text=result.stderr or "",
    )

    # Special output conventions used by some appendix scripts
    if script_path.stem == "tableA6":
        candidates = [
            script_path.parent / "MOV_100percent.txt",
            script_path.parent / "MOV_25percent.txt",
            script_path.parent / "MOV_10percent.txt",
        ]
        if any(p.exists() and p.stat().st_size > 0 for p in candidates):
            return JobResult(
                label=label,
                status="completed",
                duration_seconds=duration,
                return_code=result.returncode,
                output_path=candidates[0],
                stdout_log_path=stdout_log_path,
                stderr_log_path=stderr_log_path,
            )

    if script_path.stem == "tableA7":
        txt_candidates = list(script_path.parent.glob("*.txt"))
        if txt_candidates:
            return JobResult(
                label=label,
                status="completed",
                duration_seconds=duration,
                return_code=result.returncode,
                output_path=txt_candidates[0],
                stdout_log_path=stdout_log_path,
                stderr_log_path=stderr_log_path,
            )

    if result.stdout and result.stdout.strip():
        logger.info("STDOUT for %s:\n%s", label, result.stdout.strip())

    if result.stderr and result.stderr.strip():
        logger.error("STDERR for %s:\n%s", label, result.stderr.strip())

    if result.returncode != 0:
        return JobResult(
            label=label,
            status="failed",
            duration_seconds=duration,
            return_code=result.returncode,
            note=(
                f"Non-zero exit code: {result.returncode} | "
                f"stderr log: {stderr_log_path}"
            ),
            output_path=output_path,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
        )

    if not output_path.exists():
        return JobResult(
            label=label,
            status="failed",
            duration_seconds=duration,
            return_code=result.returncode,
            note=(
                f"Expected output file is missing: {output_path} | "
                f"stderr log: {stderr_log_path}"
            ),
            output_path=output_path,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
        )

    if output_path.stat().st_size == 0:
        return JobResult(
            label=label,
            status="failed",
            duration_seconds=duration,
            return_code=result.returncode,
            note=(
                f"Output file is empty: {output_path} | "
                f"stderr log: {stderr_log_path}"
            ),
            output_path=output_path,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
        )

    return JobResult(
        label=label,
        status="completed",
        duration_seconds=duration,
        return_code=result.returncode,
        output_path=output_path,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
    )


def summarize_results(
    logger: logging.Logger,
    results: list[JobResult],
    tables_root: Path,
) -> None:
    """
    Log a final summary of launcher execution.
    """
    completed = [r for r in results if r.status == "completed"]
    skipped = [r for r in results if r.status == "skipped"]
    failed = [r for r in results if r.status == "failed"]

    logger.info(
        "Completed %s table scripts. Outputs are under: %s",
        len(completed),
        tables_root,
    )

    if skipped:
        logger.warning("Skipped jobs: %s", ", ".join(r.label for r in skipped))

    if failed:
        logger.error("Failed jobs: %s", ", ".join(r.label for r in failed))
        for item in failed:
            logger.error(" - %s | %s", item.label, item.note)

    total_runtime = sum(r.duration_seconds for r in results)
    logger.info("Total runtime: %.2f seconds", total_runtime)


def main() -> None:
    """
    Main entry point of the launcher.

    Exit codes
    ----------
    0 : all selected jobs completed or were skipped
    2 : at least one selected job failed
    """
    args = parse_args()
    logger = configure_logging(getattr(logging, args.log_level))

    base_dir = find_project_root(Path(__file__).resolve().parent)
    datasets_dir = Path(args.datasets_dir).resolve()
    tables_root = Path(args.tables_root).resolve()

    validate_project_paths(datasets_dir, tables_root)
    child_env = build_pythonpath_env(base_dir)

    jobs = select_jobs(args)
    results: list[JobResult] = []

    for table_dir_name, script_name, dataset_stems in jobs:
        job_result = run_table_job(
            base_dir=base_dir,
            datasets_dir=datasets_dir,
            tables_root=tables_root,
            child_env=child_env,
            logger=logger,
            table_dir_name=table_dir_name,
            script_name=script_name,
            dataset_stems=dataset_stems,
        )
        results.append(job_result)

        if job_result.status == "failed" and args.fail_fast:
            logger.error(
                "Fail-fast enabled. Stopping after first failure: %s",
                job_result.label,
            )
            summarize_results(logger, results, tables_root)
            raise SystemExit(2)

    summarize_results(logger, results, tables_root)

    if any(r.status == "failed" for r in results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()