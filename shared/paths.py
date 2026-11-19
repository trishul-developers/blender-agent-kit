"""Cross-platform kit-root and pointer manifest resolution (Python 3.10+ stdlib only)."""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path

ENV_KIT_ROOT = "BLENDER_AGENT_KIT_ROOT"
APP_DIR_NAME = "blender-agent-kit"
MANIFEST_FILENAME = "manifest.json"


def config_manifest_path() -> Path:
    """Return the cross-platform pointer manifest path."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / APP_DIR_NAME / MANIFEST_FILENAME


def write_pointer_manifest(kit_root: Path, installed_targets: list[str] | None = None,
                           manifest_path: Path | None = None) -> Path:
    """Write the lightweight kit-root pointer manifest."""
    dest = manifest_path or config_manifest_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kit_root": str(kit_root.resolve()),
        "targets": installed_targets or [],
    }
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def resolve_kit_root(explicit: str | Path | None = None,
                     manifest_path: Path | None = None) -> Path:
    """Resolve the blender-agent-kit root directory cleanly without relying on CWD or PYTHONPATH."""
    if explicit:
        p = Path(explicit).resolve()
        if (p / "shared").is_dir():
            return p
        raise FileNotFoundError(f"Explicit kit root lacks shared/: {p}")

    env_val = os.environ.get(ENV_KIT_ROOT)
    if env_val:
        p = Path(env_val).resolve()
        if (p / "shared").is_dir():
            return p
        raise FileNotFoundError(f"{ENV_KIT_ROOT} points to invalid kit root: {p}")

    # Walk upwards from this file in case we are running directly from a repo checkout.
    here = Path(__file__).resolve()
    for candidate in (here.parent.parent, *here.parents):
        if (candidate / "shared").is_dir() and (candidate / "schemas").is_dir():
            return candidate

    mp = manifest_path or config_manifest_path()
    if mp.is_file():
        data = json.loads(mp.read_text(encoding="utf-8"))
        p = Path(data["kit_root"]).resolve()
        if (p / "shared").is_dir():
            return p
        raise FileNotFoundError(f"Pointer manifest {mp} points to missing kit root: {p}")

    raise FileNotFoundError(
        f"Cannot locate blender-agent-kit root. Set {ENV_KIT_ROOT} or run tools/install.py."
    )
