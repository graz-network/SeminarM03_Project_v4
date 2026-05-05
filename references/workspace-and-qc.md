# Workspace initialization and quality control

## Recommended execution order
1. Initialize a fresh workspace with `scripts/init_meco_workspace.py`.
2. Install dependencies from the workspace `requirements.txt`.
3. Run a smoke test of the Python replication pipeline.
4. Run the full table and figure pipelines if needed.
5. Run `run_replication.py` to compare Python outputs against the bundled Stata reference outputs.
6. Run the extension script.
7. Generate the report scaffold.
8. Draft the report using the generated outputs and the report references.

## Why the skill uses a workspace clone
Never run directly inside the skill directory. The skill bundles a reusable project template and source assets. The workspace clone prevents accidental edits to the skill bundle itself and makes the final project exportable.

## Quality-control conventions
- Keep raw Stata datasets untouched under `data/raw/`.
- Put generated tables in `results/tables/` and figures in `results/figures/`.
- Keep extension outputs in `results/extensions/`.
- Keep report drafts in `report/`.
- Write a short methods note whenever you deviate from the original specification.

## Appendix A18 rule
The bundled workspace includes reconstructed neighbor files from ThePythonicProject, but the public archive did not include the original `neighbor_females.dta`. Treat any A18-style analysis as reconstructed or supplemental unless you separately validate the reconstruction.

## Minimum reproducibility package expected at the end
- code directory with all scripts actually used;
- raw-data manifest;
- generated tables and figures;
- extension outputs;
- final report source and final PDF;
- short README explaining run order.
