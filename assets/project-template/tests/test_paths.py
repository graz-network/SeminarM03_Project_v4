from __future__ import annotations

"""
tests/test_paths.py

Unit tests for the path utility functions used in the replication project.

Purpose
-------
These tests ensure that the path resolution utilities correctly identify:

1. The project root directory.
2. The canonical raw data directory.
3. The canonical table results directory.
4. Dataset resolution rules (.dta preferred over .csv).

These tests guarantee that all launcher scripts and table scripts rely on
a consistent project directory structure.
"""

from pathlib import Path

import pytest

from meco_replication.paths import (
    data_raw_dir,
    find_project_root,
    resolve_table_dataset,
    results_tables_dir,
)


# ---------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------

def project_root() -> Path:
    """
    Return the repository root directory.

    This helper assumes that the `tests/` directory is located directly
    under the project root.
    """
    return Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------
# Project root detection tests
# ---------------------------------------------------------------------

def test_find_project_root_from_repo_root() -> None:
    """
    When the resolver is called from the project root,
    it should return the same directory.
    """
    root = project_root()
    resolved = find_project_root(root)

    assert resolved == root


def test_find_project_root_from_nested_directory() -> None:
    """
    The project root resolver should correctly walk upward
    from deeply nested directories.
    """
    nested = project_root() / "results" / "tables" / "Table2"

    resolved = find_project_root(nested)

    assert resolved == project_root()


# ---------------------------------------------------------------------
# Canonical directory resolution tests
# ---------------------------------------------------------------------

def test_data_raw_dir_points_to_existing_data_folder() -> None:
    """
    data_raw_dir() should resolve to the project's canonical raw data folder.
    """
    root = project_root()
    raw_dir = data_raw_dir(root)

    assert raw_dir == root / "data" / "raw"
    assert raw_dir.exists()
    assert raw_dir.is_dir()


def test_results_tables_dir_points_to_existing_tables_folder() -> None:
    """
    results_tables_dir() should resolve to the canonical tables output folder.
    """
    root = project_root()
    tables_dir = results_tables_dir(root)

    assert tables_dir == root / "results" / "tables"
    assert tables_dir.exists()
    assert tables_dir.is_dir()


# ---------------------------------------------------------------------
# Dataset resolution tests
# ---------------------------------------------------------------------

def test_resolve_table_dataset_prefers_dta_over_csv(tmp_path: Path) -> None:
    """
    If both .dta and .csv versions of a dataset exist,
    the resolver should prefer the .dta file.

    This ensures compatibility with original Stata replication packages.
    """
    dta_path = tmp_path / "main_dataset.dta"
    csv_path = tmp_path / "main_dataset.csv"

    dta_path.write_text("fake dta placeholder", encoding="utf-8")
    csv_path.write_text("fake csv placeholder", encoding="utf-8")

    resolved = resolve_table_dataset(tmp_path, "main_dataset")

    assert resolved == dta_path


def test_resolve_table_dataset_uses_csv_if_dta_missing(tmp_path: Path) -> None:
    """
    If a .dta file is missing but a .csv file exists,
    the resolver should fall back to the .csv file.
    """
    csv_path = tmp_path / "main_dataset.csv"
    csv_path.write_text("fake csv placeholder", encoding="utf-8")

    resolved = resolve_table_dataset(tmp_path, "main_dataset")

    assert resolved == csv_path


def test_resolve_table_dataset_raises_clear_error_if_missing(tmp_path: Path) -> None:
    """
    If neither .dta nor .csv exists, the resolver should raise a clear error.
    """
    with pytest.raises(FileNotFoundError, match="main_dataset"):
        resolve_table_dataset(tmp_path, "main_dataset")


# ---------------------------------------------------------------------
# Real dataset resolution test
# ---------------------------------------------------------------------

def test_resolve_real_main_dataset_from_repo_data_dir() -> None:
    """
    Verify that the resolver correctly finds the real dataset in the project.

    The test accepts either `.dta` or `.csv`, depending on which format
    is present in the repository.
    """
    raw_dir = data_raw_dir(project_root())

    resolved = resolve_table_dataset(raw_dir, "main_dataset")

    assert resolved.exists()
    assert resolved.stem == "main_dataset"
    assert resolved.suffix.lower() in {".dta", ".csv"}