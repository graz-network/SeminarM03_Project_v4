# Datasets and variable map

## Bundled replication package
The skill bundles the official replication archive `114710-V1.zip` and uses it as the authoritative source for the original Stata datasets and reference outputs.

## Workspace dataset layout after initialization
The workspace initializer extracts the archive under `stata_original/` and copies the original Stata datasets into `data/raw/` so the Python pipeline can run against them.

Expected core files in `data/raw/`:
- `main_dataset.dta`
- `characteristics_mixed_and_single_gender_municipalities.dta`
- `dataset_for_party_level_results.dta`
- `dataset_with_lagged_rank_improvments.dta`
- `dataset_with_rank_improvments_next_election.dta`
- `mayor_election_data.dta`
- `municipality_characteristics_data.dta`
- `neighbor_regressions_dataset.dta`

The initializer also copies reconstructed files from ThePythonicProject:
- `neighbor_females.dta` and `.csv`
- `neighbor_pairs.dta` and `.csv`

## Key variables from `main_dataset`
- `gkz`: municipality identifier.
- `jahr`: local council election year.
- `gkz_jahr`: municipality-year key.
- `rdd_sample`: indicator for municipalities whose previous mayor was elected in a mixed-gender race.
- `female`: candidate is a woman.
- `elected`: candidate wins a council seat.
- `gewinn_norm`: normalized rank improvement.
- `gewinn`: non-normalized rank improvement.
- `gewinn_dummy`: indicator for positive rank improvement.
- `listenplatz_norm`: normalized initial list rank.
- `joint_party`: candidate and mayor belong to the same party.
- `incumbent_council`: candidate served on previous council.
- `female_mayor`: female winner in mixed-gender mayor race.
- `margin_1`: margin of victory of the top female mayoral candidate.
- `inter_1`: `female_mayor * margin_1`.
- `margin_2`: squared running variable.
- `inter_2`: `female_mayor * margin_2`.
- municipality controls: population, area, debt, tax revenue, employment, female labor-force shares.

## Important implementation notes
- In the datasets, `margin_1` is expressed in percentage points, not in proportions. Typical narrow-band windows are therefore 5, 7.5, 10, or 15 rather than 0.05, 0.075, 0.10, 0.15.
- `gkz_jahr` is not formatted consistently across all files. In the main dataset it is often a pure digit string like `4110002001`, while the party-level dataset often uses `411000_2001`. Normalize it before merging.
- Party labels are not perfectly standardized across files. Use careful normalization and document any alias mapping.

## Official replication package limitation
The public archive does not contain the original `neighbor_females.dta` used for one appendix workflow. The skill bundles reconstructed versions from ThePythonicProject, but any use of them should be labeled as reconstructed rather than treated as the original public input.
