"""
tests/test_outputs.py

Unit tests verifying that generated table outputs exist and contain
expected structural elements.

Purpose
-------
These tests ensure that:

1. Table-generation scripts produced the expected output files.
2. The files are not empty.
3. Key structural labels appear in the outputs.

These tests do not validate the econometric correctness of coefficients;
they verify that the pipeline executed correctly and produced usable tables.
"""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """
    Return the project root directory.

    This helper assumes the tests directory is located directly
    inside the repository root.
    """
    return Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    """
    Read a text file with UTF-8 encoding.

    Parameters
    ----------
    path : Path
        Path to the file.

    Returns
    -------
    str
        File content as a string.
    """
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------
# Table 1 tests
# ---------------------------------------------------------------------

def test_table1_parta_output_contains_expected_labels() -> None:
    """
    Verify that Table 1 Part A output exists and contains key labels.
    """
    path = project_root() / "results" / "tables" / "Table1" / "Table1_PartA.txt"

    assert path.exists(), f"Missing output file: {path}"

    content = read_text(path)

    assert "Age" in content
    assert "Rank change (normalized)" in content


# ---------------------------------------------------------------------
# Table 2 tests
# ---------------------------------------------------------------------

def test_table2_output_contains_expected_structure() -> None:
    """
    Verify that Table 2 output exists and contains core regression table
    elements expected from the RD specification.
    """
    path = project_root() / "results" / "tables" / "Table2" / "table2.txt"

    assert path.exists(), f"Missing output file: {path}"

    content = read_text(path)

    assert "female_mayor" in content
    assert "Bandwidth type" in content
    assert "Bandwidth size" in content
    assert "N" in content


# ---------------------------------------------------------------------
# Table 3 tests
# ---------------------------------------------------------------------

def test_table3_output_contains_expected_structure() -> None:
    """
    Verify that Table 3 output exists and contains RD table components.
    """
    path = project_root() / "results" / "tables" / "Table3" / "table3.txt"

    assert path.exists(), f"Missing output file: {path}"

    content = read_text(path)

    assert "female_mayor" in content
    assert "Bandwidth type" in content
    assert "Municipalities" in content


# ---------------------------------------------------------------------
# Sanity test: files are not empty
# ---------------------------------------------------------------------

def test_outputs_are_not_empty() -> None:
    """
    Ensure that key output files are non-empty.
    """
    files = [
        project_root() / "results" / "tables" / "Table1" / "Table1_PartA.txt",
        project_root() / "results" / "tables" / "Table2" / "table2.txt",
        project_root() / "results" / "tables" / "Table3" / "table3.txt",
    ]

    for file in files:
        assert file.exists(), f"Missing output file: {file}"
        assert file.stat().st_size > 0, f"Output file is empty: {file}"