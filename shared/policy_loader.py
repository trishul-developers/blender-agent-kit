"""Reusable production-policy discovery layered between engine targets and project profiles."""
from __future__ import annotations

import json
from pathlib import Path

from shared.paths import resolve_kit_root
from shared.target_loader import deep_merge_dict


def list_policies(kit_root: Path | None = None) -> dict[str, Path]:
    root = kit_root or resolve_kit_root()
    policies_dir = root / "plugins" / "policies"
    found: dict[str, Path] = {}
    if not policies_dir.is_dir():
        return found
    for entry in sorted(policies_dir.iterdir()):
        cfg = entry / "policy.json"
        if not cfg.is_file():
            continue
        data = json.loads(cfg.read_text(encoding="utf-8"))
        found[data["name"]] = cfg
    return found


def validate_policy_dict(data: dict) -> list[str]:
    errors: list[str] = []
    for key in ("name", "version", "target_defaults"):
        if key not in data:
            errors.append(f"Missing required policy key: {key}")
    if "target_defaults" in data and not isinstance(data["target_defaults"], dict):
        errors.append("target_defaults must be an object")
    if "target_overrides" in data and not isinstance(data["target_overrides"], dict):
        errors.append("target_overrides must be an object")
    return errors


def load_policy(
    identifier: str | Path | None,
    kit_root: Path | None = None,
) -> tuple[dict | None, Path | None]:
    if identifier is None:
        return None, None

    candidate = Path(identifier)
    if candidate.is_file():
        path = candidate.resolve()
    else:
        policies = list_policies(kit_root)
        key = str(identifier).removeprefix("blender-policy-")
        if key not in policies:
            raise KeyError(f"Unknown policy '{identifier}'. Available: {sorted(policies.keys())}")
        path = policies[key]

    data = json.loads(path.read_text(encoding="utf-8"))
    errs = validate_policy_dict(data)
    if errs:
        raise ValueError(f"Invalid policy {path}: " + "; ".join(errs))
    return data, path


def policy_overlay_for_target(policy_data: dict | None, target_name: str) -> dict | None:
    if not policy_data:
        return None
    overlay = dict(policy_data.get("target_defaults", {}))
    short = target_name.removeprefix("blender-target-")
    specific = policy_data.get("target_overrides", {}).get(short)
    if specific:
        overlay = deep_merge_dict(overlay, specific)
    return overlay
