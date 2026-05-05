---
name: meco-m03-female-leadership-research
description: initialize and run a reusable meco m03 applied-econometrics workflow for the paper on female mayors and women in politics. use when chatgpt must (1) set up a reproducible python workspace from the bundled official replication archive, (2) reproduce the paper's tables, figures, and audit comparisons against the original stata outputs, (3) run the cross-party spillover extension on female candidates from other parties, or (4) scaffold a seminar report that follows the meco m03 report template, grading criteria, and reproducibility expectations.
---

# MECO M03 Female Leadership Research

## Overview
Use this skill to turn the bundled research materials into a clean, reproducible project workspace. The skill combines three assets:
1. a stripped-down code snapshot of ThePythonicProject;
2. the official replication archive `114710-V1.zip`;
3. MECO M03 reporting and grading guidance.

Work in a cloned workspace, not inside the skill directory.

## Workflow

### 1. Decide the user's goal
Route the request into one or more of these paths:
- **Initialize workspace**: create a runnable project folder.
- **Replicate the paper**: run the Python tables, figures, and audit scripts.
- **Run the extension**: estimate cross-party spillovers and heterogeneity.
- **Draft the report**: create the seminar-paper scaffold and map outputs into the report structure.
- **Full pipeline**: do all four in order.

### 2. Initialize a clean workspace first
Run the bundled initializer from the skill folder:

```bash
python scripts/init_meco_workspace.py /mnt/data/meco_m03_workspace --force
```

This script:
- copies the project template into the workspace;
- extracts the official replication archive into `stata_original/`;
- copies original Stata datasets into `data/raw/`;
- copies reconstructed `neighbor_females` and `neighbor_pairs` files into `data/raw/`;
- optionally copies the bundled source PDFs and prompt note into `source_docs/`.

After initialization, work from the workspace root.

### 3. Install dependencies in the workspace
From the workspace root, install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

If the user only wants the extension script, still install the workspace requirements before running it.

### 4. Replicate the original paper
Use the workspace commands below.

#### Smoke test first
```bash
python generate_all_tables.py --smoke-test
```

#### Full table pipeline
```bash
python generate_all_tables.py
```

#### Full figure pipeline
```bash
python generate_all_figures.py
```

#### Audit Python outputs against the original Stata outputs
```bash
python run_replication.py
```

Use the generated audit outputs in `analysis/` to describe where the Python replication matches cleanly and where differences remain.

### 5. Run the extension
The project template includes a dedicated extension module:

```bash
python extensions/heterogeneous_cross_party_spillovers.py
```

Default outputs go to `results/extensions/` and include:
- sample counts by RD window;
- benchmark cross-party RD-style estimates;
- all-women interaction estimates comparing copartisan and non-copartisan women;
- lagged placebo estimates;
- next-election dynamic estimates;
- subgroup heterogeneity summaries and a subgroup plot.

Important implementation rule: interpret bandwidths in **percentage points**, because `margin_1` is stored on that scale in the datasets.

### 6. Scaffold the seminar report
After replication and extension outputs exist, create a report skeleton inside the workspace:

```bash
python reporting/create_report_scaffold.py
```

This writes a report structure aligned with the MECO M03 template and a submission checklist.

## Analytical guardrails

### Anchor all claims to the original identification logic
Keep the original paper's design at the center of the workflow:
- use close mixed-gender mayoral races as the identifying variation;
- treat normalized rank improvement as the primary behavioral outcome;
- use weighted RD-style benchmarks and municipality-clustered standard errors as the main empirical anchor.

### Separate strong claims from exploratory claims
- **Strongest claims**: original-paper replication outputs and transparent RD-style extension benchmarks.
- **Weaker claims**: subgroup heterogeneity patterns, especially when party-level merges are incomplete or rich controls reduce sample size.
- Always report when a result depends on a specific bandwidth or reduced sample.

### Treat Appendix A18 conservatively
The official public archive did not include the original `neighbor_females.dta`. The skill bundles reconstructed replacements from ThePythonicProject, but any A18-style result should be labeled as **reconstructed** or **supplemental** unless separately validated.

## Resource map

### scripts/
- `scripts/init_meco_workspace.py`: initialize the runnable workspace from the bundled assets.

### references/
Use these files when writing or interpreting the project:
- `references/meco-course-brief.md`
- `references/original-paper-methodology.md`
- `references/datasets-and-variables.md`
- `references/report-structure.md`
- `references/grading-checklist.md`
- `references/extension-h3.md`
- `references/workspace-and-qc.md`
- `references/writing-support.md`

### assets/
- `assets/project-template/`: bundled code snapshot of ThePythonicProject plus the extension and report scaffolding modules.
- `assets/replication-package/114710-V1.zip`: official replication archive used as the authoritative original package.
- `assets/reconstructed-data/`: reconstructed neighbor files copied into the workspace for optional supplemental work.
- `assets/source-docs/`: original PDFs and prompt note bundled for completeness.

## Output expectations
When using this skill successfully, leave behind a workspace that contains:
- `data/raw/` with original Stata datasets;
- `results/tables/` and `results/figures/` with generated replication outputs;
- `analysis/` with replication audit outputs;
- `results/extensions/` with the cross-party spillover outputs;
- `report/` with the scaffold and later the paper source/PDF.

Keep the run order explicit and preserve reproducibility at every step.
