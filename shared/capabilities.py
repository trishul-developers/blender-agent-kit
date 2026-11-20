"""Host-only machine-readable capability discovery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared.command_registry import COMMANDS
from shared.paths import resolve_kit_root
from shared.policy_loader import list_policies
from shared.profile_loader import list_project_profiles
from shared.target_loader import list_targets
from shared.version import KIT_VERSION


def _frontmatter_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return path.parent.name
    end = text.find("\n---\n", 4)
    if end < 0:
        return path.parent.name
    for line in text[4:end].splitlines():
        if line.strip().startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return path.parent.name


def _skill_inventory(root: Path, target_names: list[str], profile_names: list[str]) -> list[dict]:
    command_owners: dict[str, list[str]] = {}
    for command, spec in COMMANDS.items():
        command_owners.setdefault(spec["skill"], []).append(command)

    result: list[dict] = []
    files = sorted(root.glob("skills/**/SKILL.md")) + sorted(root.glob("plugins/targets/*/SKILL.md")) + sorted(root.glob("plugins/profiles/*/SKILL.md"))
    for path in files:
        name = _frontmatter_name(path)
        commands = sorted(command_owners.get(name, []))
        if name.startswith("blender-target-"):
            target = name.removeprefix("blender-target-")
            execution = "executable-config" if target in target_names else "configuration"
        elif name.startswith("blender-profile-"):
            profile = name.removeprefix("blender-profile-")
            execution = "configuration" if profile in profile_names else "guidance-only"
        elif commands:
            execution = "executable"
        else:
            execution = "guidance-only"
        result.append({
            "name": name,
            "execution": execution,
            "commands": commands,
        })
    return result


def build_capabilities(kit_root: Path | None = None) -> dict:
    root = (kit_root or resolve_kit_root()).resolve()
    targets = list_targets(root)
    policies = list_policies(root)
    profiles = list_project_profiles(root)
    commands = [
        {
            "name": name,
            "mode": spec["mode"],
            "skill": spec["skill"],
            "purpose": spec["purpose"],
            "evidence": list(spec["evidence"]),
        }
        for name, spec in sorted(COMMANDS.items())
    ]
    target_rows = []
    for name, path in sorted(targets.items()):
        data = json.loads(path.read_text(encoding="utf-8"))
        target_rows.append({
            "name": name,
            "version": data.get("version"),
            "default_policy": data.get("default_policy"),
            "texture_profiles": sorted(data.get("textures", {}).get("profiles", {}).keys()),
        })
    policy_rows = []
    for name, path in sorted(policies.items()):
        data = json.loads(path.read_text(encoding="utf-8"))
        policy_rows.append({"name": name, "version": data.get("version")})
    profile_rows = []
    for name, path in sorted(profiles.items()):
        data = json.loads(path.read_text(encoding="utf-8"))
        profile_rows.append({
            "name": name,
            "version": data.get("version"),
            "targets": sorted(data.get("target_overrides", {}).keys()),
            "review_presets": sorted(data.get("review_presets", {}).keys()),
        })
    return {
        "status": "ok",
        "kit_version": KIT_VERSION,
        "runtime": {
            "host_python": ">=3.10",
            "blender": ">=5.2",
            "headless_first": True,
        },
        "commands": commands,
        "targets": target_rows,
        "policies": policy_rows,
        "project_profiles": profile_rows,
        "skills": _skill_inventory(root, sorted(targets), sorted(profiles)),
        "notes": {
            "batch": "guidance-only until a batch command is implemented",
            "asset_creation": "agent-authored Blender/Python; no one-shot neural text-to-3D command",
        },
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser(description="Discover Blender Agent Kit executable/guidance capabilities.")
    p.add_argument("--json", action="store_true", help="Compatibility flag; output is JSON by default.")
    p.parse_args(argv)
    return build_capabilities()
