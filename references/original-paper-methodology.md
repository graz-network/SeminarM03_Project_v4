# Original paper: methodology and empirical map

## Paper identity
- Title: Does the Election of a Female Leader Clear the Way for More Women in Politics?
- Core question: does electing a female mayor improve the electoral performance of female candidates in subsequent open-list local council elections?

## Institutional setting
- Location: municipalities in Hesse, Germany.
- Mayor elections: direct elections every six years, not synchronized statewide.
- Council elections: statewide every five years under an open-list system.
- Key identification advantage: voters can reshuffle candidate rankings through preferential votes, so the change between initial and final rank isolates voter-side behavior better than seat outcomes alone.

## Main data structure
- Candidate-level council-election data for 2001, 2006, 2011, 2016.
- Original paper sample: 109,017 candidates, including gender, party, initial list rank, final rank, elected status, and several personal covariates.
- Mayor-election data cover all municipalities from 1993 onward.

## Main outcome
The primary dependent variable is normalized rank improvement:

rank improvement = ((initial rank - final rank) / council size) * 100

Interpretation:
- positive value: voters moved the candidate up relative to the party's initial placement;
- negative value: voters moved the candidate down.

## Main treatment
- female_mayor = 1 when the woman wins the prior mixed-gender mayor race.
- running variable: margin of victory of the top female mayoral candidate.
- treatment is identified around close mixed-gender mayoral elections.

## Baseline design
The paper uses sharp RD specifications with local linear and local quadratic fits, bandwidths based on CCT and IK rules, and municipality-clustered robust standard errors.

Baseline interpretation target:
- effect of a female mayor on female candidates' subsequent normalized rank improvement.

## Main findings to remember
- female mayors increase female candidates' normalized rank improvement;
- the paper reports roughly a 3.7-point gain per 100 council seats in the preferred baseline;
- effects on representation are positive but noisier;
- nonincumbent women benefit more strongly;
- spillovers reach neighboring municipalities;
- observed mechanisms are more consistent with changing voter perceptions than with systematic changes in initial list placement.

## Mechanism checks already in the paper
The original paper examines:
- initial list placements;
- number of women on lists;
- observable candidate composition;
- turnout;
- placebo using previous election outcomes.

## Extension anchor for this skill
Any extension should stay tied to the paper's logic:
- the main behavioral outcome is rank improvement, not only election to council;
- the identifying variation is still the close mixed-gender mayor race;
- claims should remain strongest when supported by transparent RD-style benchmarks.
