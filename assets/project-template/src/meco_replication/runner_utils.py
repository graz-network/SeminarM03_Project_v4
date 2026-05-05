from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(level=level, format='%(asctime)s | %(levelname)s | %(message)s')
    return logging.getLogger('meco_replication')


def build_pythonpath_env(project_root: Path) -> dict[str, str]:
    """Build an environment that exposes both project root and src/."""
    env = os.environ.copy()
    src_dir = project_root / 'src'
    parts = [str(src_dir), str(project_root)]
    existing = env.get('PYTHONPATH', '')
    if existing:
        parts.append(existing)
    env['PYTHONPATH'] = os.pathsep.join(parts)
    return env


def run_subprocess(*, cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
