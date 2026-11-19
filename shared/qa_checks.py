"""Asset-class QA checks driven by target.json (runs inside headless Blender)."""
from __future__ import annotations

import argparse
from shared.target_loader import load_target


def run(target: str = "unity", asset_class: str = "solid_prop") -> dict:
    """Audit active Blender scene meshes/armatures against target.json QA rules."""
    import bmesh
    import bpy

    target_cfg, _, _ = load_target(target)
    common = target_cfg["qa"]["common"]
    classes = target_cfg["qa"]["asset_classes"]
    if asset_class not in classes:
        raise KeyError(f"Unknown asset_class '{asset_class}'. Available: {sorted(classes.keys())}")
    cls_rules = classes[asset_class]

    errors: list[dict] = []
    warnings: list[dict] = []
    per_object: dict[str, dict] = {}

    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        obj_errors: list[str] = []
        sx, sy, sz = obj.scale
        if common.get("reject_negative_scale", True) and (sx < 0 or sy < 0 or sz < 0):
            obj_errors.append(f"negative_scale: {tuple(obj.scale)}")
        if common.get("require_applied_scale", True) and any(abs(s - 1.0) > 1e-4 for s in obj.scale):
            obj_errors.append(f"unapplied_scale: {tuple(obj.scale)}")

        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        non_manifold_edges = sum(1 for e in bm.edges if len(e.link_faces) > 2)
        boundary_edges = sum(1 for e in bm.edges if len(e.link_faces) == 1)
        tri_count = sum(len(f.verts) - 2 for f in bm.faces)
        bm.free()

        if common.get("reject_non_manifold_edges", True) and non_manifold_edges > 0:
            obj_errors.append(f"non_manifold_edges: {non_manifold_edges}")
        if cls_rules.get("reject_boundary_edges", False) and boundary_edges > 0:
            obj_errors.append(f"boundary_edges: {boundary_edges}")

        uv_layers = len(mesh.uv_layers)
        if common.get("require_uv0", True) and uv_layers < 1:
            obj_errors.append("missing_uv0")
        if cls_rules.get("require_non_overlapping_uv1", False) and uv_layers < 2:
            warnings.append({"object": obj.name, "warning": "missing_uv1_lightmap"})

        max_mats = cls_rules.get("max_material_slots")
        if max_mats is not None and len(obj.material_slots) > int(max_mats):
            obj_errors.append(f"material_slots ({len(obj.material_slots)}) > max ({max_mats})")

        max_lod0 = cls_rules.get("max_tris", {}).get("lod0")
        if max_lod0 is not None and tri_count > int(max_lod0):
            obj_errors.append(f"tri_count ({tri_count}) > max_lod0 ({max_lod0})")

        per_object[obj.name] = {
            "tris": tri_count,
            "uv_layers": uv_layers,
            "material_slots": len(obj.material_slots),
            "non_manifold_edges": non_manifold_edges,
            "boundary_edges": boundary_edges,
            "errors": obj_errors,
        }
        for e in obj_errors:
            errors.append({"object": obj.name, "error": e})

    return {
        "status": "ok" if not errors else "error",
        "blender_version": bpy.app.version_string,
        "target": target_cfg["name"],
        "asset_class": asset_class,
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "per_object": per_object,
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="unity")
    p.add_argument("--asset-class", default="solid_prop")
    ns = p.parse_args(argv)
    return run(target=ns.target, asset_class=ns.asset_class)
