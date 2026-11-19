#!/usr/bin/env python3
"""Scaffold a new 2-file data-driven target plugin (target.json + SKILL.md)."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def scaffold_target(name: str, fmt: str = "glb", normal_conv: str = "opengl", kit_root: Path = KIT_ROOT) -> Path:
    if not NAME_RE.match(name):
        raise ValueError(f"Invalid target name '{name}'. Use lowercase alphanumeric + hyphens.")
    if fmt not in ("fbx", "glb", "gltf"):
        raise ValueError(f"Unsupported scaffold export format '{fmt}'. Supported: fbx, glb, gltf")
    skill_name = f"blender-target-{name}"
    dest = kit_root / "plugins" / "targets" / skill_name
    if dest.exists():
        raise FileExistsError(f"Target plugin already exists: {dest}")
    dest.mkdir(parents=True)

    target_json = {
        "name": name,
        "skill_name": skill_name,
        "version": "0.1.0",
        "default_profile": "standard",
        "units": {"system": "METRIC", "scale": 1.0},
        "export": {
            "format": fmt,
            "use_selection": True,
            "object_types": ["MESH", "EMPTY", "ARMATURE"],
            "forward_axis": "-Z",
            "up_axis": "Y",
            "apply_scalings": "FBX_SCALE_ALL",
            "apply_unit_scale": True,
            "apply_transform_static": True,
            "apply_transform_rigged": False,
            "apply_modifiers": True,
            "use_triangles": True,
            "use_tspace": True,
            "mesh_smooth_type": "FACE",
            "only_deform_bones": True,
            "add_leaf_bones": False,
            "bake_anim": True,
            "bake_anim_use_nla_strips": True,
            "bake_anim_use_all_actions": False,
            "bake_anim_simplify_factor": 0.0,
            "embed_textures": False,
        },
        "naming": {
            "lod_pattern": "{name}_LOD{index}",
            "collider_pattern": "{name}_COL_{index:02d}",
            "texture_pattern": "textures/{asset_id}__{material_name}__{map}.png",
            "manifest_file": "{name}.asset.manifest.json",
        },
        "textures": {
            "normal_convention": normal_conv,
            "fallback_constants": {"ao": 1.0, "alpha": 1.0, "metallic": 0.0, "roughness": 0.5},
            "profiles": {
                "standard": {
                    "shader": "StandardPBR",
                    "maps": {
                        "albedo": {"slot": "base_color", "channels": ["base_color.r", "base_color.g", "base_color.b", "alpha"], "srgb": True, "bit_depth": 8},
                        "orm": {"slot": "orm", "channels": ["ao", "roughness", "metallic"], "srgb": False, "bit_depth": 8},
                        "normal": {"slot": "normal", "channels": ["normal.r", "normal.g", "normal.b"], "srgb": False, "bit_depth": 16},
                    },
                }
            },
        },
        "qa": {
            "common": {
                "require_applied_scale": True,
                "reject_negative_scale": True,
                "reject_non_manifold_edges": True,
                "reject_inward_normals": True,
                "require_uv0": True,
                "require_monotonic_lod_tris": True,
                "roundtrip_armature_scale_tolerance": 0.001,
            },
            "asset_classes": {
                "solid_prop": {"reject_boundary_edges": True, "max_tris": {"lod0": 15000}, "max_material_slots": 2},
                "open_sheet": {"reject_boundary_edges": False, "max_tris": {"lod0": 10000}, "max_material_slots": 2},
            },
        },
    }
    (dest / "target.json").write_text(json.dumps(target_json, indent=2) + "\n", encoding="utf-8")

    skill_md = f"""---
name: {skill_name}
description: Use this skill when preparing, packing textures for, validating, or exporting Blender assets for {name.title()}. Loads the declarative {name} target profile and runs headless export + round-trip verification.
---

# Blender Target: {name.title()}

Use `blender-core`'s single entrypoint with `--target {name}`:

```bash
python <blender-core>/scripts/run.py qa --blend in.blend --target {name} --asset-class solid_prop
python <blender-core>/scripts/run.py export --blend in.blend --target {name} --out build/
```

## Target Rules
- Configuration lives in `target.json` (`format: {fmt}`, `normal_convention: {normal_conv}`).
- Do not edit shared core scripts for {name}-specific tweaks; update `target.json` or add a project profile.
"""
    (dest / "SKILL.md").write_text(skill_md, encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scaffold a new 2-file target plugin.")
    p.add_argument("name", help="Short engine name (e.g. godot, unreal)")
    p.add_argument("--format", choices=["fbx", "glb", "gltf"], default="glb")
    p.add_argument("--normal", choices=["opengl", "directx"], default="opengl")
    ns = p.parse_args(argv)
    dest = scaffold_target(ns.name, fmt=ns.format, normal_conv=ns.normal)
    print(f"Created 2-file target plugin at {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
