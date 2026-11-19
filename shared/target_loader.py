"""Target plugin discovery, loading, overlay merging, and lightweight stdlib validation."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from shared.paths import resolve_kit_root

REQUIRED_TOP_KEYS = (
    "name", "skill_name", "version", "default_profile",
    "units", "export", "naming", "textures", "qa",
)


def deep_merge_dict(base: dict, overlay: dict) -> dict:
    """Return a recursive copy of base with overlay values applied."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def list_targets(kit_root: Path | None = None) -> dict[str, Path]:
    root = kit_root or resolve_kit_root()
    targets_dir = root / "plugins" / "targets"
    found: dict[str, Path] = {}
    if not targets_dir.is_dir():
        return found
    for entry in sorted(targets_dir.iterdir()):
        cfg = entry / "target.json"
        if entry.is_dir() and cfg.is_file():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            found[data["name"]] = cfg
    return found


def validate_target_dict(data: dict, folder_name: str | None = None) -> list[str]:
    errors: list[str] = []
    for k in REQUIRED_TOP_KEYS:
        if k not in data:
            errors.append(f"Missing required top-level key: {k}")
    if errors:
        return errors

    expected_skill = f"blender-target-{data['name']}"
    if data["skill_name"] != expected_skill:
        errors.append(f"skill_name '{data['skill_name']}' must equal '{expected_skill}'")
    if folder_name and folder_name != data["skill_name"]:
        errors.append(f"Folder name '{folder_name}' must match skill_name '{data['skill_name']}'")

    exp = data["export"]
    if exp.get("format") not in ("fbx", "glb", "gltf"):
        errors.append(f"Unsupported export format: {exp.get('format')}")
    if exp.get("bake_anim_use_nla_strips") and exp.get("bake_anim_use_all_actions"):
        errors.append("export cannot set both bake_anim_use_nla_strips and bake_anim_use_all_actions to true (causes duplicate clips)")

    profiles = data["textures"].get("profiles", {})
    if data["default_profile"] not in profiles:
        errors.append(f"default_profile '{data['default_profile']}' not found in textures.profiles")

    for pname, pcfg in profiles.items():
        for mname, mcfg in pcfg.get("maps", {}).items():
            if mcfg.get("bit_depth") not in (8, 16):
                errors.append(f"Profile '{pname}' map '{mname}' bit_depth must be 8 or 16")
            if not isinstance(mcfg.get("srgb"), bool):
                errors.append(f"Profile '{pname}' map '{mname}' must specify boolean srgb")
            ch = mcfg.get("channels", [])
            if not (1 <= len(ch) <= 4):
                errors.append(f"Profile '{pname}' map '{mname}' must define 1-4 channels")
    return errors


def load_target(
    target_name: str,
    profile: str | None = None,
    kit_root: Path | None = None,
    overlay: dict | None = None,
) -> tuple[dict, str, Path]:
    """Load a target and optionally apply a project overlay before profile selection."""
    targets = list_targets(kit_root)
    short = target_name.removeprefix("blender-target-")
    if short not in targets:
        raise KeyError(f"Unknown target '{target_name}'. Available: {sorted(targets.keys())}")
    cfg_path = targets[short]
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    if overlay:
        data = deep_merge_dict(data, overlay)
    errs = validate_target_dict(data, folder_name=cfg_path.parent.name)
    if errs:
        raise ValueError(f"Invalid target config at {cfg_path}: " + "; ".join(errs))

    chosen_profile = profile or data["default_profile"]
    if chosen_profile not in data["textures"]["profiles"]:
        raise KeyError(
            f"Unknown profile '{chosen_profile}' for target '{short}'. "
            f"Available: {sorted(data['textures']['profiles'].keys())}"
        )
    return data, chosen_profile, cfg_path.parent
