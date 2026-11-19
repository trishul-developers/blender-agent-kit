"""Declarative per-format exporter with strict schema-to-RNA translation and round-trip check."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shared.target_loader import load_target


def translate_fbx_kwargs(export_cfg: dict, filepath: str, is_rigged: bool = False) -> dict:
    """Translate format-agnostic target.json['export'] keys to bpy.ops.export_scene.fbx kwargs."""
    apply_transform = (
        bool(export_cfg.get("apply_transform_rigged", False))
        if is_rigged
        else bool(export_cfg.get("apply_transform_static", True))
    )
    return {
        "filepath": filepath,
        "use_selection": bool(export_cfg.get("use_selection", True)),
        "object_types": set(export_cfg.get("object_types", ["MESH", "EMPTY", "ARMATURE"])),
        "axis_forward": export_cfg.get("forward_axis", "-Z"),
        "axis_up": export_cfg.get("up_axis", "Y"),
        "global_scale": 1.0,
        "apply_unit_scale": bool(export_cfg.get("apply_unit_scale", True)),
        "apply_scale_options": export_cfg.get("apply_scalings", "FBX_SCALE_ALL"),
        "bake_space_transform": apply_transform,
        "use_mesh_modifiers": bool(export_cfg.get("apply_modifiers", True)),
        "use_triangles": bool(export_cfg.get("use_triangles", True)),
        "use_tspace": bool(export_cfg.get("use_tspace", True)),
        "mesh_smooth_type": export_cfg.get("mesh_smooth_type", "FACE"),
        "use_armature_deform_only": bool(export_cfg.get("only_deform_bones", True)),
        "add_leaf_bones": bool(export_cfg.get("add_leaf_bones", False)),
        "bake_anim": bool(export_cfg.get("bake_anim", True)),
        "bake_anim_use_nla_strips": bool(export_cfg.get("bake_anim_use_nla_strips", True)),
        "bake_anim_use_all_actions": bool(export_cfg.get("bake_anim_use_all_actions", False)),
        "bake_anim_simplify_factor": float(export_cfg.get("bake_anim_simplify_factor", 0.0)),
        "path_mode": "COPY" if export_cfg.get("embed_textures", False) else "AUTO",
        "embed_textures": bool(export_cfg.get("embed_textures", False)),
    }


def translate_gltf_kwargs(export_cfg: dict, filepath: str) -> dict:
    """Translate format-agnostic target.json['export'] keys to bpy.ops.export_scene.gltf kwargs."""
    fmt = "GLB" if filepath.lower().endswith(".glb") else "GLTF_SEPARATE"
    return {
        "filepath": filepath,
        "export_format": fmt,
        "use_selection": bool(export_cfg.get("use_selection", True)),
        "export_yup": export_cfg.get("up_axis", "Y") == "Y",
        "export_apply": bool(export_cfg.get("apply_modifiers", True)),
        "export_tangents": bool(export_cfg.get("use_tspace", True)),
        "export_def_bones": bool(export_cfg.get("only_deform_bones", True)),
        "export_animations": bool(export_cfg.get("bake_anim", True)),
    }


def compute_build_hash(paths: list[Path]) -> str:
    """Compute a deterministic SHA-256 hash over input files for incremental blender-batch rebuilds."""
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.is_file():
            h.update(p.name.encode("utf-8"))
            h.update(p.read_bytes())
    return "sha256:" + h.hexdigest()[:32]


def run(
    target: str = "unity",
    profile: str | None = None,
    out_dir: str = "build",
    asset_id: str | None = None,
    category: str = "solid_prop",
    rig_type: str = "none",
    uv1_source: str = "blender",
    fmt_override: str | None = None,
    verify_roundtrip: bool = True,
) -> dict:
    """Export current Blender scene according to target.json and emit *.asset.manifest.json."""
    import bpy  # Imported inside run() so schema-to-RNA translators are unit-testable without Blender

    target_cfg, chosen_profile, _ = load_target(target, profile)
    export_cfg = target_cfg["export"]
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    source_blend = bpy.data.filepath or ""
    aid = asset_id or (Path(source_blend).stem if source_blend else "untitled_asset")
    fmt = (fmt_override or export_cfg["format"]).lower()
    export_file = out_path / f"{aid}.{fmt}"

    allowed_types = set(export_cfg.get("object_types", ["MESH", "EMPTY", "ARMATURE"]))
    objs = [o for o in bpy.context.scene.objects if o.type in allowed_types]
    is_rigged = rig_type != "none" or any(o.type == "ARMATURE" for o in objs)

    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)

    if fmt == "fbx":
        kwargs = translate_fbx_kwargs(export_cfg, str(export_file), is_rigged=is_rigged)
        bpy.ops.export_scene.fbx(**kwargs)
    elif fmt in ("glb", "gltf"):
        kwargs = translate_gltf_kwargs(export_cfg, str(export_file))
        bpy.ops.export_scene.gltf(**kwargs)
    else:
        raise ValueError(f"Unsupported export format: {fmt}")

    # Gather LODs and colliders for manifest
    lods = []
    colliders = []
    for o in sorted(objs, key=lambda x: x.name):
        if "_COL_" in o.name or o.name.endswith("_COL"):
            colliders.append({"node_name": o.name, "shape": "convex_mesh", "strip_renderer": True})
        elif o.type == "MESH":
            tri_count = sum(len(p.vertices) - 2 for p in o.data.polygons)
            lods.append({"name": o.name, "tri_count": int(tri_count), "screen_relative_transition_height": 0.25})

    manifest = {
        "schema_version": "1.0",
        "asset_id": aid,
        "category": category,
        "source_blend": source_blend,
        "build_script": None,
        "build_hash": compute_build_hash([Path(source_blend)] if source_blend else [export_file]),
        "blender_version": bpy.app.version_string,
        "target": target_cfg["name"],
        "profile": chosen_profile,
        "rig_type": rig_type,
        "uv1_source": uv1_source,
        "export_file": export_file.name,
        "disable_unity_auto_mesh_lod": len(lods) > 1,
        "lods": lods,
        "colliders": colliders,
        "materials": [],
        "textures": [],
    }
    manifest_name = target_cfg["naming"]["manifest_file"].format(name=aid)
    manifest_path = out_path / manifest_name
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    roundtrip = {"checked": False}
    if verify_roundtrip:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if fmt == "fbx":
            bpy.ops.import_scene.fbx(filepath=str(export_file))
        else:
            bpy.ops.import_scene.gltf(filepath=str(export_file))
        imported = list(bpy.context.scene.objects)
        tol = float(target_cfg["qa"]["common"].get("roundtrip_armature_scale_tolerance", 0.001))
        scale_errors = []
        for obj in imported:
            if obj.type in ("MESH", "ARMATURE"):
                if any(abs(s - 1.0) > tol for s in obj.scale):
                    scale_errors.append({"object": obj.name, "scale": list(obj.scale)})
        roundtrip = {
            "checked": True,
            "imported_count": len(imported),
            "scale_errors": scale_errors,
            "passed": len(imported) > 0 and len(scale_errors) == 0,
        }

    return {
        "status": "ok" if (not verify_roundtrip or roundtrip["passed"]) else "error",
        "blender_version": bpy.app.version_string,
        "build_hash": manifest["build_hash"],
        "target": target_cfg["name"],
        "profile": chosen_profile,
        "artifacts": {
            "export": str(export_file),
            "manifest": str(manifest_path),
        },
        "roundtrip": roundtrip,
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="unity")
    p.add_argument("--profile", default=None)
    p.add_argument("--out", default="build")
    p.add_argument("--asset-id", default=None)
    p.add_argument("--category", default="solid_prop")
    p.add_argument("--rig-type", default="none")
    p.add_argument("--uv1-source", default="blender")
    p.add_argument("--format", default=None)
    p.add_argument("--no-roundtrip", action="store_true")
    ns = p.parse_args(argv)
    return run(
        target=ns.target,
        profile=ns.profile,
        out_dir=ns.out,
        asset_id=ns.asset_id,
        category=ns.category,
        rig_type=ns.rig_type,
        uv1_source=ns.uv1_source,
        fmt_override=ns.format,
        verify_roundtrip=not ns.no_roundtrip,
    )
