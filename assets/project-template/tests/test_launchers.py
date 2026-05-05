from __future__ import annotations

"""
tests/test_launchers.py

Integration tests for the main pipeline launcher.

Purpose
-------
These tests verify that the replication pipeline can be invoked through
its main entry point (`generate_all_tables.py`) and that the launcher
responds correctly to different command-line arguments.

The tests do NOT re-estimate econometric models. Instead they ensure:

1. The launcher starts successfully.
2. The smoke-test mode works.
3. Individual job execution works.
4. The process exits cleanly.

These tests protect the reproducibility infrastructure of the project.
"""

import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    """
    Return the repository root directory.
    """
    return Path(__file__).resolve().parents[1]


def launcher_script() -> Path:
    """
    Return the path to the main launcher script.
    """
    return project_root() / "generate_all_tables.py"


# ---------------------------------------------------------------------
# Basic launcher execution
# ---------------------------------------------------------------------

def test_launcher_script_exists() -> None:
    """
    Ensure that the main launcher script exists.
    """
    path = launcher_script()

    assert path.exists()
    assert path.is_file()


# ---------------------------------------------------------------------
# Smoke test execution
# ---------------------------------------------------------------------

def test_launcher_smoke_test_runs() -> None:
    """
    Run the launcher in smoke-test mode.

    This mode runs a minimal subset of tables and should finish quickly.
    """
    result = subprocess.run(
        [
            sys.executable,
            str(launcher_script()),
            "--smoke-test",
        ],
        cwd=project_root(),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0


# ---------------------------------------------------------------------
# Single job execution
# ---------------------------------------------------------------------

def test_launcher_single_job_execution() -> None:
    """
    Run the launcher for a single job.

    This ensures that the `--jobs` option works correctly.
    """
    result = subprocess.run(
        [
            sys.executable,
            str(launcher_script()),
            "--jobs",
            "Table2/table2.py",
        ],
        cwd=project_root(),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0


# ---------------------------------------------------------------------
# Fail-fast behaviour
# ---------------------------------------------------------------------

def test_launcher_fail_fast_option() -> None:
    """
    Verify that the launcher accepts the --fail-fast argument.

    This test does not force a failure but ensures the flag
    is accepted and does not crash the program.
    """
    result = subprocess.run(
        [
            sys.executable,
            str(launcher_script()),
            "--smoke-test",
            "--fail-fast",
        ],
        cwd=project_root(),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0