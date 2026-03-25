"""Test bootstrap helpers for the standalone mfiutil plugin repository."""

import os
import sys

from pathlib import Path
from typing import List


def _candidate_paths() -> List[Path]:
    """Return possible AASd host roots used for importing public APIs."""
    repo_root = Path(__file__).resolve().parents[1]
    out: List[Path] = []
    env_root = os.environ.get("AASD_ROOT")
    if env_root:
        out.append(Path(env_root))
    out.extend(
        [
            repo_root.parent / "AASd",
            repo_root.parent.parent / "AASd",
            repo_root.parent.parent.parent / "AASd",
        ]
    )
    return out


for candidate in _candidate_paths():
    if (candidate / "aasd.py").exists() and (candidate / "libs").is_dir():
        sys.path.insert(0, str(candidate))
        break
