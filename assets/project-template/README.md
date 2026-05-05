# ThePythonicProject

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#requirements)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](#tests)
[![Status](https://img.shields.io/badge/status-replication%20workflow-informational.svg)](#project-overview)

Python replication pipeline for the paper:

**Does the election of a female leader clear the way for more women in politics?**

This repository reorganizes the original replication package into a cleaner, Python-first project structure. It is designed for academic replication work: reproducing tables and figures, validating outputs against original Stata results, and documenting where Python and Stata results coincide or diverge.

---

## Project overview

The goal of this project is to provide a more maintainable and transparent replication workflow for the original study by:

- reproducing tables and figures in Python
- preserving the original Stata outputs for validation
- separating data, results, reusable code, and tests
- making the replication package easier to inspect, extend, and audit

This version is especially useful for:
- applied econometrics coursework
- reproducibility checks
- method replication assignments
- side-by-side Stata vs Python validation

---

## Current replication scope and limitations

This repository does **not** claim a full exact replication of every table in the original Stata package.

In particular:

- **Table A18 is not claimed as replicated.**
- The original Stata workflow for Table A18 depends on `neighbor_females.dta`.
- That file is not included in the public replication archive.
- The closest available file, `neighbor_regressions_dataset.dta`, is not treated here as a validated one-to-one substitute for the original A18 input.

Accordingly, Table A18 is excluded from the default Python replication pipeline and from any “replicated tables” summary unless its missing source is reconstructed and validated.

---

## Repository structure

```text
ThePythonicProject/
├── analysis/                       # Replication analysis reports
├── data/
│   └── raw/                        # Input datasets (.dta / .csv)
│   └── convert_dta_to_csv.py       # Launcher to convert dta files to csv
│   └── check_dta_csv_integrity.py  # Launcher to check the csv data integrity
├── notebooks/                      # Jupiter Notebooks files
├── results/
│   ├── figures/                    # Generated figure outputs
│   └── tables/                     # Generated table outputs
├── src/
│   └── meco_replication/           # Reusable Python package
│       ├── __init__.py
│       ├── paths.py
│       ├── runner_utils.py
│       ├── table_helpers.py
│       └── stata_helpers.py
├── stata_original/                 # originals datasets and results 
├── tests/                          # Automated tests
├── run replication.py              # Execute the replication and make reports
├── generate_all_tables.py          # Launcher for all table scripts
├── generate_all_figures.py         # Launcher for all figure scripts
├── pyproject.toml                  # Project metadata and dependencies
├── requirements.txt                # Project libraries required 
└── README.md