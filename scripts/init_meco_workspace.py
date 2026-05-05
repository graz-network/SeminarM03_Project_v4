#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize a runnable MECO M03 workspace from the bundled skill assets."
    )
    parser.add_argument(
        "output_dir",
        help="Target directory for the initialized workspace.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove the target directory first if it already exists.",
    )
    parser.add_argument(
        "--no-source-docs",
        action="store_true",
        help="Do not copy bundled PDFs and source documents into the workspace.",
    )
    return parser.parse_args()


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst)


def main() -> int:
    args = parse_args()
    skill_root = Path(__file__).resolve().parents[1]
    template_dir = skill_root / "assets" / "project-template"
    replication_zip = skill_root / "assets" / "replication-package" / "114710-V1.zip"
    reconstructed_dir = skill_root / "assets" / "reconstructed-data"
    source_docs_dir = skill_root / "assets" / "source-docs"

    outdir = Path(args.output_dir).expanduser().resolve()
    if outdir.exists():
        if not args.force:
            print(f"Target already exists: {outdir}", file=sys.stderr)
            print("Use --force to overwrite it.", file=sys.stderr)
            return 1
        shutil.rmtree(outdir)

    copy_tree(template_dir, outdir)

    stata_root = outdir / "stata_original"
    stata_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(replication_zip, "r") as zf:
        zf.extractall(stata_root)

    raw_dir = outdir / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    original_dataset_dir = stata_root / "data" / "datasets"
    for file_path in original_dataset_dir.glob("*"):
        if file_path.is_file():
            shutil.copy2(file_path, raw_dir / file_path.name)

    for file_path in reconstructed_dir.glob("*"):
        if file_path.is_file():
            shutil.copy2(file_path, raw_dir / file_path.name)

    if not args.no_source_docs and source_docs_dir.exists():
        docs_target = outdir / "source_docs"
        shutil.copytree(source_docs_dir, docs_target)

    manifest = {
        "workspace": str(outdir),
        "template_source": str(template_dir),
        "replication_zip": str(replication_zip),
        "copied_raw_files": sorted(p.name for p in raw_dir.glob("*")),
        "source_docs_copied": bool((outdir / "source_docs").exists()),
        "next_steps": [
            "cd <workspace>",
            "python -m pip install -r requirements.txt",
            "python generate_all_tables.py --smoke-test",
            "python run_replication.py",
            "python extensions/heterogeneous_cross_party_spillovers.py",
            "python reporting/create_report_scaffold.py",
        ],
    }
    (outdir / "workspace_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    ready_note = f"""# Workspace ready

The workspace has been initialized at:
`{outdir}`

## Suggested next steps
1. `cd {outdir}`
2. `python -m pip install -r requirements.txt`
3. `python generate_all_tables.py --smoke-test`
4. `python run_replication.py`
5. `python extensions/heterogeneous_cross_party_spillovers.py`
6. `python reporting/create_report_scaffold.py`

## Important note on Appendix A18
The workspace includes reconstructed `neighbor_females` files copied from ThePythonicProject. Treat any A18-style result as reconstructed unless you separately validate it against the original unavailable source.
"""
    (outdir / "WORKSPACE_READY.md").write_text(ready_note, encoding="utf-8")

    print(f"Initialized workspace at: {outdir}")
    print(f"Copied raw datasets into: {raw_dir}")
    if (outdir / "source_docs").exists():
        print(f"Copied source documents into: {outdir / 'source_docs'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
