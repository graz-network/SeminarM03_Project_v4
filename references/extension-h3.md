# Extension design: heterogeneous cross-party spillovers

## Main extension question
Do female mayors generate cross-party spillovers in the electoral performance of female candidates, and are these spillovers heterogeneous across candidates, parties, municipalities, and election timing?

## Why this extension is coherent
The original paper's main outcome is normalized rank improvement, which captures how voters revise party-imposed rankings under open lists. If the core mechanism is reduced anti-female voter bias after exposure to female leadership, the effect could spill beyond the mayor's own party.

## Recommended nested claims
- H3a: contemporary cross-party spillover in the same council election.
- H3b: contrast between copartisan and non-copartisan women.
- H3c: temporal validation using lagged placebo and next-election outcomes.
- H3d: heterogeneity across candidate, party, and municipality contexts.

## Preferred samples
### Strict cross-party sample
- `rdd_sample == 1`
- `female == 1`
- `joint_party == 0`
- `abs(margin_1) <= h`

### All-women comparison sample
- `rdd_sample == 1`
- `female == 1`
- `abs(margin_1) <= h`
- create `other_party = 1 - joint_party`

## Outcomes
Primary:
- `gewinn_norm`

Secondary:
- `gewinn_dummy`
- `elected`

## Baseline extension specification
Within a chosen RD window, estimate a weighted benchmark such as:

Y_i = alpha + tau D_i + beta1 margin_i + beta2 D_i * margin_i + beta3 margin_i^2 + beta4 D_i * margin_i^2 + gamma X_i + epsilon_i

where:
- `D_i = female_mayor`
- cluster standard errors at `gkz`
- use triangular kernel weights inside the window.

## Comparison model on all women
Estimate:

Y_i = alpha + tau female_mayor_i + delta other_party_i + rho female_mayor_i * other_party_i + f(margin_i) + gamma X_i + epsilon_i

Interpretation:
- `tau`: effect for copartisan women;
- `rho`: additional effect for women from other parties.

## Dynamic validation
Use the dedicated lagged and next-election datasets to test:
- placebo: current female mayor should not explain previous election outcomes;
- persistence or delayed diffusion: positive effects may appear in the next election.

## Heterogeneity dimensions recommended by the project materials
- incumbency (`incumbent_council`)
- initial list position (`listenplatz_norm`)
- party vote share (`voteshare`)
- female share on the party list (`mean_frau`)
- municipality size (`log_bevoelkerung`)

## Interpretation guardrails
- Strongest claim: transparent RD-style benchmarks.
- Weaker claim: heterogeneous patterns when subgroup cells are smaller or party-level merge quality is imperfect.
- If rich controls induce sample loss, report both a minimal benchmark and a richer sensitivity version.
- Do not claim a universal cross-party effect unless the average effect is stable across reasonable windows/specifications.
