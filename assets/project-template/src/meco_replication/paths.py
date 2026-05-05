from __future__ import annotations

"""
paths.py

Path utilities for the MECO replication project.

Purpose
-------
This module centralizes path resolution logic for the entire replication
pipeline. Instead of each script reconstructing directory paths manually,
all components rely on these utilities.

Responsibilities
----------------
1. Detect the project root directory.
2. Provide canonical access to project subdirectories.
3. Resolve dataset files (.dta or .csv).

This design ensures consistent behaviour across:

- launcher scripts
- table scripts
- test suite
"""

from pathlib import Path


# ---------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------

def find_project_root(start: Path | None = None) -> Path:
    """
    Detect the project root by walking upward in the directory tree.

    Parameters
    ----------
    start : Path | None
        Starting location for the search. If omitted, the current working
        directory is used.

    Returns
    -------
    Path
        The project root directory.

    Raises
    ------
    FileNotFoundError
        If no valid project root is found.

    Notes
    -----
    A valid root directory must contain:

    - src/
    - data/
    - results/
    """
    current = (start or Path.cwd()).resolve()

    if current.is_file():
        current = current.parent

    for candidate in [current, *current.parents]:
        if (
            (candidate / "src").exists()
            and (candidate / "data").exists()
            and (candidate / "results").exists()
        ):
            return candidate

    raise FileNotFoundError(
        f"Could not determine the project root starting from: {current}"
    )


# ---------------------------------------------------------------------
# Canonical project directories
# ---------------------------------------------------------------------

def src_dir(base_dir: Path | None = None) -> Path:
    """
    Return the project source-code directory.
    """
    root = find_project_root(base_dir)
    return root / "src"


def data_dir(base_dir: Path | None = None) -> Path:
    """
    Return the project data directory.
    """
    root = find_project_root(base_dir)
    return root / "data"


def data_raw_dir(base_dir: Path | None = None) -> Path:
    """
    Return the raw-data directory.

    This is the directory expected to contain datasets such as:
    - main_dataset.dta
    - mayor_election_data.dta
    """
    root = find_project_root(base_dir)
    return root / "data" / "raw"


def results_dir(base_dir: Path | None = None) -> Path:
    """
    Return the main results directory.
    """
    root = find_project_root(base_dir)
    return root / "results"


def results_tables_dir(base_dir: Path | None = None) -> Path:
    """
    Return the directory containing all table outputs.
    """
    root = find_project_root(base_dir)
    return root / "results" / "tables"


def results_figures_dir(base_dir: Path | None = None) -> Path:
    """
    Return the directory containing all figure outputs and figure scripts.
    """
    root = find_project_root(base_dir)
    return root / "results" / "figures"


def tests_dir(base_dir: Path | None = None) -> Path:
    """
    Return the project test directory.
    """
    root = find_project_root(base_dir)
    return root / "tests"


# ---------------------------------------------------------------------
# Dataset resolution
# ---------------------------------------------------------------------

def resolve_table_dataset(datasets_dir: Path, stem: str) -> Path:
    """
    Resolve a dataset stem to an existing dataset file.

    Parameters
    ----------
    datasets_dir : Path
        Directory containing dataset files.

    stem : str
        Dataset name without extension.

    Returns
    -------
    Path
        Path to the resolved dataset file.

    Raises
    ------
    FileNotFoundError
        If neither `.dta` nor `.csv` exists.

    Resolution priority
    -------------------
    1. `<stem>.dta`
    2. `<stem>.csv`

    Rationale
    ---------
    Stata `.dta` files are preferred because they correspond to the
    original replication data used in the paper.
    """
    datasets_dir = Path(datasets_dir)

    dta = datasets_dir / f"{stem}.dta"
    csv = datasets_dir / f"{stem}.csv"

    if dta.exists():
        return dta

    if csv.exists():
        return csv

    raise FileNotFoundError(
        f"Could not find dataset '{stem}' in {datasets_dir}. "
        f"Expected one of: {stem}.dta or {stem}.csv"
    )


# ---------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------

def ensure_within_project(path: Path, base_dir: Path | None = None) -> Path:
    """
    Ensure that a path belongs to the project directory tree.

    Parameters
    ----------
    path : Path
        Path to validate.

    base_dir : Path | None
        Path used to determine the project root.

    Returns
    -------
    Path
        The resolved path if it belongs to the project.

    Raises
    ------
    ValueError
        If the path is outside the project root.

    Notes
    -----
    This function helps protect the pipeline from accidental writes
    outside the repository structure.
    """
    root = find_project_root(base_dir).resolve()
    resolved = Path(path).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Path is outside the project root: {resolved} (root: {root})"
        ) from exc

    return resolved