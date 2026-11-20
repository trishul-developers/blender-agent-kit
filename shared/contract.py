"""Host-only resolved production contract discovery."""
from __future__ import annotations

import argparse

from shared.profile_loader import load_profiled_target


def _qa_contract(common: dict, rules: dict) -> dict:
    return {
        "transforms": {
            "require_applied_scale": bool(common.get("require_applied_scale", False)),
            "reject_negative_scale": bool(common.get("reject_negative_scale", False)),
        },
        "topology": {
            "reject_non_manifold_edges": bool(common.get("reject_non_manifold_edges", False)),
            "reject_inward_normals": bool(common.get("reject_inward_normals", False)),
            "reject_boundary_edges": bool(rules.get("reject_boundary_edges", False)),
        },
        "uv": {
            "require_uv0": bool(common.get("require_uv0", False)),
            "require_non_overlapping_uv1": bool(rules.get("require_non_overlapping_uv1", False)),
            "texel_density_px_per_m": common.get("texel_density_px_per_m"),
            "geometric_uv1_overlap_verified": False,
            "additional_checks": list(rules.get("uv_checks", [])),
        },
        "lod": {
            "max_tris": dict(rules.get("max_tris", {})),
            "require_monotonic_tris": bool(common.get("require_monotonic_lod_tris", False)),
            "max_lod_ratio": rules.get("max_lod_ratio", common.get("max_lod_ratio")),
            "exclude_patterns": list(rules.get("lod_exclude_patterns", common.get("lod_exclude_patterns", []))),
        },
        "materials": {
            "max_slots": rules.get("max_material_slots"),
            "max_slots_by_lod": dict(rules.get("max_material_slots_by_lod", {})),
        },
        "pivot": {
            "rule": rules.get("pivot_rule", "none"),
            "tolerance": rules.get("pivot_tolerance"),
        },
        "ground": {
            "axis": rules.get("ground_axis"),
            "target": rules.get("ground_target"),
            "tolerance": rules.get("ground_tolerance"),
        },
        "rigging": {
            "max_bone_weights_per_vertex": rules.get("max_bone_weights_per_vertex"),
        },
        "hierarchy": {
            "required_nodes": list(rules.get("required_nodes", [])),
            "required_parent_pairs": list(rules.get("required_parent_pairs", [])),
        },
        "damage": {
            "prefix": rules.get("damage_prefix", common.get("damage_prefix")),
            "allowed_lods": rules.get("damage_allowed_lods", common.get("damage_allowed_lods")),
        },
    }


def build_contract(
    target: str = "unity",
    texture_profile: str | None = None,
    project_profile: str | None = None,
    asset_class: str = "solid_prop",
    preset: str | None = None,
) -> dict:
    target_cfg, chosen_profile, _target_dir, project_data, _project_path = load_profiled_target(
        target,
        texture_profile=texture_profile,
        project_profile=project_profile,
    )
    common = target_cfg.get("qa", {}).get("common", {})
    classes = target_cfg.get("qa", {}).get("asset_classes", {})
    if asset_class not in classes:
        raise KeyError(f"Unknown asset_class '{asset_class}'. Available: {sorted(classes)}")
    rules = classes[asset_class]
    naming = target_cfg.get("naming", {})
    export = target_cfg.get("export", {})
    texture_cfg = target_cfg.get("textures", {}).get("profiles", {}).get(chosen_profile, {})
    review_presets = (project_data or {}).get("review_presets", {})
    selected_preset = None
    if preset is not None:
        if preset not in review_presets:
            raise KeyError(f"Unknown review preset '{preset}'. Available: {sorted(review_presets)}")
        selected_preset = review_presets[preset]

    return {
        "status": "ok",
        "target": {
            "name": target_cfg["name"],
            "version": target_cfg.get("version"),
            "units": dict(target_cfg.get("units", {})),
            "default_policy": target_cfg.get("default_policy"),
        },
        "project_profile": project_data["name"] if project_data else None,
        "asset_class": asset_class,
        "naming": {
            "lod_pattern": naming.get("lod_pattern"),
            "collider_patterns": list(naming.get("collider_patterns", [])) if not naming.get("collider_pattern") else [naming["collider_pattern"]],
            "texture_pattern": naming.get("texture_pattern"),
            "manifest_file": naming.get("manifest_file"),
            "directional_empty_patterns": list(export.get("prebake_directional_patterns", [])),
            "strip_lod_suffix_pattern": export.get("strip_lod_suffix_pattern"),
        },
        "qa": _qa_contract(common, rules),
        "textures": {
            "profile": chosen_profile,
            "shader": texture_cfg.get("shader"),
            "normal_convention": target_cfg.get("textures", {}).get("normal_convention"),
            "maps": texture_cfg.get("maps", {}),
        },
        "export": {
            "format": export.get("format"),
            "alt_static_format": export.get("alt_static_format"),
            "forward_axis": export.get("forward_axis"),
            "up_axis": export.get("up_axis"),
            "prebake_yup_hierarchy": bool(export.get("prebake_yup_hierarchy", False)),
            "object_types": list(export.get("object_types", [])),
            "lod_screen_transitions": dict(export.get("lod_screen_transitions", {})),
            "embed_textures": bool(export.get("embed_textures", False)),
            "roundtrip": {
                "enabled_by_default": True,
                "armature_scale_tolerance": common.get("roundtrip_armature_scale_tolerance"),
                "checks": [
                    "object_names",
                    "parent_hierarchy",
                    "mesh_armature_scale",
                    "child_local_transforms",
                    "triangle_count",
                    "embedded_image_headers",
                ],
            },
        },
        "review": {
            "available_presets": sorted(review_presets),
            "selected_preset": preset,
            "settings": selected_preset,
        },
        "known_limits": [
            "UV1 geometric island overlap is not verified; presence emits uv1_overlap_unverified when requested.",
            "Engine-side prefab/LODGroup construction is outside Blender round-trip verification.",
        ],
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser(description="Resolve one machine-readable Blender Agent Kit production contract.")
    p.add_argument("--target", default="unity")
    p.add_argument("--profile", default=None)
    p.add_argument("--project-profile", default=None)
    p.add_argument("--asset-class", default="solid_prop")
    p.add_argument("--preset", default=None)
    p.add_argument("--json", action="store_true", help="Compatibility flag; output is JSON by default.")
    ns = p.parse_args(argv)
    return build_contract(
        target=ns.target,
        texture_profile=ns.profile,
        project_profile=ns.project_profile,
        asset_class=ns.asset_class,
        preset=ns.preset,
    )
