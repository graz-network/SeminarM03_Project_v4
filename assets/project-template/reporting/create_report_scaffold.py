#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a report scaffold aligned with the MECO M03 report template and grading criteria."
    )
    parser.add_argument(
        "--output-dir",
        default="report",
        help="Directory where the scaffold should be written.",
    )
    parser.add_argument(
        "--title",
        default="Replication and Extension Report",
        help="Report title.",
    )
    parser.add_argument(
        "--authors",
        default="[Add author names]",
        help="Author line for the scaffold.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outdir = Path(args.output_dir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    scaffold = f"""# {args.title}

**Authors:** {args.authors}

> Final target: PDF report, max. 15 pages. Keep the replication and extension clearly separated while using tables and figures as the main evidence base.

## Abstract (150-250 words)
- Background and motivation
- Replication objectives
- Extension objectives
- Methods and data
- Key findings
- Conclusion and implications

## 1. Introduction
- State that this is a replication study.
- Explain why replicating this paper matters.
- Summarize the original paper's main contribution.
- State your replication and extension contributions.
- Preview the structure of the report.

## 2. Literature Review
- Position the original paper in the literature.
- Cover related work on women in politics, voter bias, open-list elections, and spillovers.
- Explain what your replication and extension add.

## 3. Replication Study Design
### 3.1 Replication scope
### 3.2 Data and sample
### 3.3 Empirical approach
### 3.4 Expectations and potential issues

## 4. Replication Results
### 4.1 Main reproduced findings
### 4.2 Comparison to the original study
### 4.3 Robustness and implementation differences

## 5. Extension Results
### 5.1 Motivation for the extension
### 5.2 Research question and hypotheses
### 5.3 Data construction for cross-party spillovers
### 5.4 Benchmark RD-style estimates
### 5.5 Dynamic validation: placebo and next election
### 5.6 Heterogeneity across candidates, parties, and municipalities
### 5.7 Robustness checks

## 6. Discussion and Implications
- What survived replication?
- What changed under the extension?
- What are the main limitations?
- What policy or research implications follow?

## 7. Conclusion
- Were the original results replicable?
- What did the extension show?
- What remains open for future work?

## References
- Use one consistent citation style.

## Appendix: reproducibility checklist
- [ ] Raw datasets documented
- [ ] Code run order documented
- [ ] Output folders reproduced from scripts
- [ ] Report tables and figures linked to actual generated files
- [ ] Any deviations from the original paper explicitly stated
"""
    (outdir / "report_scaffold.md").write_text(scaffold, encoding="utf-8")

    checklist = """# Submission checklist

## Research design
- [ ] Replication question clearly stated
- [ ] Extension question clearly stated
- [ ] Variables and samples justified

## Reproducibility
- [ ] Workspace initializes cleanly
- [ ] Scripts run from documented paths
- [ ] Outputs are saved in stable locations

## Econometrics
- [ ] RD assumptions and limitations discussed
- [ ] Robustness checks reported
- [ ] Interpretation avoids overclaiming

## Writing quality
- [ ] Figures and tables are referenced in the text
- [ ] Report fits within 15 pages
- [ ] Abstract reflects actual findings
"""
    (outdir / "submission_checklist.md").write_text(checklist, encoding="utf-8")

    print(f"Wrote report scaffold to: {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
