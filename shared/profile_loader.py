"""Optional project-profile discovery and target overlay resolution."""
from __future__ import annotations

import json
from pathlib import Path

from shared.paths import resolve_kit_root
from shared.policy_loader import load_policy, policy_overlay_for_target
from shared.target_loader import deep_merge_dict, load_target


def list_project_profiles(kit_root: Path | None = None) -> dict[str, Path]:
    root = kit_root or resolve_kit_root()
    profiles_dir = root / "plugins" / "profiles"
    found: dict[str, Path] = {}
    if not profiles_dir.is_dir():
        return found
    for entry in sorted(profiles_dir.iterdir()):
        cfg = entry / "profile.json"
        if not cfg.is_file():
            continue
        data = json.loads(cfg.read_text(encoding="utf-8"))
        found[data["name"]] = cfg
    return found


def validate_project_profile_dict(data: dict) -> list[str]:
    errors: list[str] = []
    for key in ("name", "version", "target_overrides"):
        if key not in data:
            errors.append(f"Missing required project-profile key: {key}")
    if "target_overrides" in data and not isinstance(data["target_overrides"], dict):
        errors.append("target_overrides must be an object")
    return errors


def load_project_profile(
    identifier: str | Path | None,
    kit_root: Path | None = None,
) -> tuple[dict | None, Path | None]:
    if identifier is None:
        return None, None

    candidate = Path(identifier)
    if candidate.is_file():
        path = candidate.resolve()
    else:
        profiles = list_project_profiles(kit_root)
        key = str(identifier).removeprefix("blender-profile-")
        if key not in profiles:
            raise KeyError(f"Unknown project profile '{identifier}'. Available: {sorted(profiles.keys())}")
        path = profiles[key]

    data = json.loads(path.read_text(encoding="utf-8"))
    errs = validate_project_profile_dict(data)
    if errs:
        raise ValueError(f"Invalid project profile {path}: " + "; ".join(errs))
    return data, path


def load_profiled_target(
    target_name: str,
    texture_profile: str | None = None,
    project_profile: str | Path | None = None,
    kit_root: Path | None = None,
    policy: str | Path | None = None,
) -> tuple[dict, str, Path, dict | None, Path | None]:
    """Resolve engine target -> reusable production policy -> project overlay.

    The target owns engine semantics. A target may name a default production
    policy (for example realtime-default), and a project profile is then merged
    on top. Supplying policy explicitly is primarily for tests/migrations.
    """
    base_cfg, _, _ = load_target(target_name, kit_root=kit_root)
    policy_id = policy if policy is not None else base_cfg.get("default_policy")
    policy_data, _ = load_policy(policy_id, kit_root=kit_root)
    overlay = policy_overlay_for_target(policy_data, target_name)

    project_data, project_path = load_project_profile(project_profile, kit_root=kit_root)
    short = target_name.removeprefix("blender-target-")
    if project_data:
        project_overlay = project_data.get("target_overrides", {}).get(short)
        if project_overlay:
            overlay = deep_merge_dict(overlay or {}, project_overlay)

    target_cfg, chosen_profile, target_dir = load_target(
        target_name,
        profile=texture_profile,
        kit_root=kit_root,
        overlay=overlay,
    )
    return target_cfg, chosen_profile, target_dir, project_data, project_path
