from __future__ import annotations

"""
generate_all_figures.py

Launcher script used to run all figure-generation scripts for the project.

"generate_all_figures.py" is the orchestration script that sequentially runs all figure-generation modules, resolves the correct datasets automatically, and ensures that child scripts inherit the correct project import paths.

Main responsibilities
---------------------
1. Detect the project root directory.
2. Resolve default input and output locations:
   - datasets: data/raw/
   - figures:  results/figures/
3. Add the local `src/` directory to Python's import path so that the
   internal package `meco_replication` can be imported without installing
   the project first.
4. Execute each figure script as a subprocess with the correct dataset.
5. Report which figure scripts completed successfully and which failed.

Typical usage
-------------
Run with default project structure:
    python generate_all_figures.py

Run with explicit paths:
    python generate_all_figures.py --datasets-dir data/raw --figures-root results/figures

Run with debug logging:
    python generate_all_figures.py --log-level DEBUG

"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------
# Bootstrapping local imports
# ---------------------------------------------------------------------
# The project stores reusable code in src/meco_replication/.
# To make imports work even if the package is not installed with pip,
# we add src/ manually to sys.path.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Local project helpers:
# - paths.py centralizes the project directory structure
# - runner_utils.py provides logging and child PYTHONPATH handling
from meco_replication.paths import data_raw_dir, find_project_root, results_figures_dir
from meco_replication.runner_utils import build_pythonpath_env, configure_logging

# ---------------------------------------------------------------------
# Figure job registry
# ---------------------------------------------------------------------
# Each tuple contains:
#   (figure subdirectory, python script name, dataset stem)
#
# Example:
#   ("Figure1", "figure1.py", "main_dataset")
#
# means:
#   - script path = results/figures/Figure1/figure1.py
#   - dataset path = data/raw/main_dataset.dta or data/raw/main_dataset.csv
FIGURE_JOBS = [
    ("Figure1", "figure1.py", "main_dataset"),
    ("Figure2", "figure2.py", "main_dataset"),
    ("Figure3", "figure3.py", "main_dataset"),
    ("FigureA1", "figureA1.py", "main_dataset"),
    ("FigureA2", "figureA2.py", "mayor_election_data"),
    ("FigureA3", "figureA3.py", "main_dataset"),
    ("FigureA4", "figureA4.py", "dataset_with_lagged_rank_improvments"),
    ("FigureA5", "figureA5_subfigure_a.py", "main_dataset"),
    ("FigureA5", "figureA5_subfigure_b.py", "main_dataset"),
    ("FigureA6", "figureA6.py", "main_dataset"),
    ("FigureA7", "figureA7.py", "main_dataset"),
    ("FigureA8", "figureA8_subfigure_a.py", "main_dataset"),
    ("FigureA8", "figureA8_subfigure_b.py", "main_dataset"),
    ("FigureA9", "figureA9.py", "main_dataset"),
    ("FigureA10", "figureA10.py", "neighbor_regressions_dataset"),
]


def resolve_dataset(datasets_dir: Path, stem: str) -> Path:
    """
    Resolve the dataset file corresponding to a dataset stem.

    The launcher accepts either:
    - <stem>.dta
    - <stem>.csv

    Priority order:
    1. .dta
    2. .csv

    Parameters
    ----------
    datasets_dir : Path
        Directory containing the raw datasets.
    stem : str
        Base filename without extension.

    Returns
    -------
    Path
        Full path to the dataset file.

    Raises
    ------
    FileNotFoundError
        If neither <stem>.dta nor <stem>.csv exists.
    """
    for candidate in (datasets_dir / f"{stem}.dta", datasets_dir / f"{stem}.csv"):
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Could not find dataset for '{stem}' in {datasets_dir}. "
        f"Expected {stem}.dta or {stem}.csv."
    )


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Default paths are inferred from the detected project root.

    Returns
    -------
    argparse.Namespace
        Parsed command-line options.
    """
    base_dir = find_project_root(Path(__file__).resolve().parent)

    parser = argparse.ArgumentParser(
        description="Run all translated figure-generation scripts."
    )
    parser.add_argument(
        "--datasets-dir",
        default=str(data_raw_dir(base_dir)),
        help="Directory containing input datasets (.dta or .csv).",
    )
    parser.add_argument(
        "--figures-root",
        default=str(results_figures_dir(base_dir)),
        help="Root directory containing figure subfolders and scripts.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Main entry point.

    Workflow
    --------
    1. Parse CLI arguments.
    2. Configure logger.
    3. Detect project root and resolve paths.
    4. Build a child environment with the correct PYTHONPATH.
    5. Loop over all registered figure jobs.
    6. Execute each figure script as a subprocess.
    7. Summarize successes and failures.

    Exit behavior
    -------------
    - exits normally if all jobs succeed
    - exits with status code 2 if at least one figure script fails
    """
    args = parse_args()
    logger = configure_logging(getattr(logging, args.log_level))

    # Resolve project-level paths
    base_dir = find_project_root(Path(__file__).resolve().parent)
    datasets_dir = Path(args.datasets_dir).resolve()
    figures_root = Path(args.figures_root).resolve()

    # Build environment for child scripts so they can also import local package code
    child_env = build_pythonpath_env(base_dir)

    completed: list[str] = []
    failed: list[str] = []

    # Process each figure job in order
    for figure_dir_name, script_name, dataset_stem in FIGURE_JOBS:
        # Expected location of the figure script
        script_path = figures_root / figure_dir_name / script_name
        if not script_path.exists():
            raise FileNotFoundError(f"Missing figure script: {script_path}")

        # Resolve the input dataset
        data_path = resolve_dataset(datasets_dir, dataset_stem)

        # Save outputs in the same subdirectory as the script
        output_dir = script_path.parent

        # Build subprocess command
        # Child script interface is assumed to be:
        #   python script.py <dataset_path> --output-dir <output_dir>
        cmd = [
            sys.executable,
            str(script_path),
            str(data_path),
            "--output-dir",
            str(output_dir),
        ]

        logger.info("Running %s", " ".join(cmd))

        # Execute the figure script without raising automatically on non-zero exit
        # so we can continue and collect all failures in one run.
        result = subprocess.run(
            cmd,
            cwd=str(base_dir),
            env=child_env,
            check=False,
        )

        label = f"{figure_dir_name}/{script_name}"
        if result.returncode == 0:
            completed.append(label)
        else:
            failed.append(label)

    # Final summary
    logger.info(
        "Completed %s figure scripts. Outputs are under: %s",
        len(completed),
        figures_root,
    )

    if failed:
        logger.error(
            "Failed %s figure scripts: %s",
            len(failed),
            ", ".join(failed),
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()