"""Declarative exporter with hierarchy-safe FBX prebake and round-trip evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from contextlib import contextmanager
from pathlib import Path

from shared.profile_loader import load_profiled_target
from shared.scene_inspector import inspect_objects, inspect_scene
from shared.version import KIT_VERSION


def translate_fbx_kwargs(export_cfg: dict, filepath: str, is_rigged: bool = False) -> dict:
    prebake = bool(export_cfg.get("prebake_yup_hierarchy", False))
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
        "use_space_transform": False if prebake else bool(export_cfg.get("use_space_transform", True)),
        "bake_space_transform": False if prebake else apply_transform,
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


def compute_build_hash(paths: list[Path], metadata: dict | None = None) -> str:
    h = hashlib.sha256()
    for p in sorted((Path(x) for x in paths), key=lambda x: x.name):
        if p.is_file():
            h.update(b"file\0")
            h.update(p.name.encode("utf-8"))
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    if metadata is not None:
        h.update(b"metadata\0")
        h.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return "sha256:" + h.hexdigest()[:32]


def _select_objects(objects) -> None:
    import bpy

    bpy.ops.object.select_all(action="DESELECT")
    first = None
    for obj in objects:
        obj.select_set(True)
        if first is None:
            first = obj
    if first is not None:
        bpy.context.view_layer.objects.active = first


def _depth(obj) -> int:
    depth = 0
    cur = obj.parent
    while cur is not None:
        depth += 1
        cur = cur.parent
    return depth


@contextmanager
def _temporary_export_state(
    objects: list,
    export_cfg: dict,
    zero_root_object=None,
):
    """Temporarily normalize a static hierarchy for FBX without mutating the authoring scene.

    prebake_yup_hierarchy applies a coordinate-basis conversion:
      local' = C * local * C^-1
      mesh'  = C * mesh
    where C = Rx(-90deg). Identity roots therefore remain identity, while nested
    pivot/socket local axes are preserved in the converted Y-up/+Z-forward basis.
    """
    import bpy
    from mathutils import Matrix

    ordered = sorted(objects, key=_depth)
    saved_matrices = {obj: obj.matrix_local.copy() for obj in ordered}
    saved_data: dict = {}
    temporary_meshes: list = []

    try:
        if zero_root_object is not None:
            zero_root_object.location = (0.0, 0.0, 0.0)

        expected_inventory = inspect_objects(ordered)

        if export_cfg.get("prebake_yup_hierarchy", False):
            armatures = [obj.name for obj in ordered if obj.type == "ARMATURE"]
            if armatures:
                raise ValueError(
                    "prebake_yup_hierarchy currently supports static MESH/EMPTY hierarchies; "
                    f"armatures present: {armatures}"
                )
            conversion = Matrix.Rotation(math.radians(-90.0), 4, "X")
            inverse = conversion.inverted()
            current_matrices = {obj: obj.matrix_local.copy() for obj in ordered}

            for obj in ordered:
                if obj.type == "MESH":
                    saved_data[obj] = obj.data
                    temp = obj.data.copy()
                    temp.transform(conversion)
                    temp.update()
                    obj.data = temp
                    temporary_meshes.append(temp)

            for obj in ordered:
                obj.matrix_local = conversion @ current_matrices[obj] @ inverse

        yield expected_inventory
    finally:
        for obj, data in saved_data.items():
            obj.data = data
        for obj in ordered:
            obj.matrix_local = saved_matrices[obj]
        for mesh in temporary_meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def export_selected(
    export_cfg: dict,
    export_file: Path,
    is_rigged: bool,
    objects: list | None = None,
    zero_root_object=None,
) -> dict:
    import bpy

    selected = list(objects) if objects is not None else list(bpy.context.selected_objects)
    with _temporary_export_state(selected, export_cfg, zero_root_object=zero_root_object) as expected:
        fmt = export_file.suffix.lower().lstrip(".")
        if fmt == "fbx":
            bpy.ops.export_scene.fbx(
                **translate_fbx_kwargs(export_cfg, str(export_file), is_rigged=is_rigged)
            )
        elif fmt in ("glb", "gltf"):
            bpy.ops.export_scene.gltf(**translate_gltf_kwargs(export_cfg, str(export_file)))
        else:
            raise ValueError(f"Unsupported export format: {fmt}")
    return expected


def scan_embedded_images(path: Path) -> dict:
    if path.suffix.lower() != ".fbx":
        return {"checked": False, "png_headers": 0, "jpeg_headers": 0, "passed": True}
    data = path.read_bytes()
    png_count = data.count(b"\x89PNG\r\n\x1a\n")
    jpeg_count = data.count(b"\xff\xd8\xff")
    return {
        "checked": True,
        "png_headers": png_count,
        "jpeg_headers": jpeg_count,
        "passed": png_count == 0 and jpeg_count == 0,
    }


def _max_vec_error(a: list[float], b: list[float]) -> float:
    return max(abs(float(x) - float(y)) for x, y in zip(a, b))


def roundtrip_file(
    export_file: Path,
    source_inventory: dict,
    tolerance: float,
    require_zero_roots: list[str] | None = None,
) -> dict:
    import bpy

    binary_scan = scan_embedded_images(export_file)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    fmt = export_file.suffix.lower().lstrip(".")
    if fmt == "fbx":
        bpy.ops.import_scene.fbx(filepath=str(export_file))
    elif fmt in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=str(export_file))
    else:
        raise ValueError(f"Unsupported round-trip format: {fmt}")

    imported_inventory = inspect_scene(damage_prefix=source_inventory.get("damage_prefix"))
    expected_objects = {o["name"] for o in source_inventory["objects"]}
    imported_objects = {o["name"] for o in imported_inventory["objects"]}
    missing = sorted(expected_objects - imported_objects)

    source_by_name = {o["name"]: o for o in source_inventory["objects"]}
    imported_by_name = {o["name"]: o for o in imported_inventory["objects"]}
    source_parent = {name: obj["parent"] for name, obj in source_by_name.items()}
    imported_parent = {name: obj["parent"] for name, obj in imported_by_name.items()}
    parent_mismatches = [
        {"object": name, "expected": source_parent[name], "actual": imported_parent.get(name)}
        for name in sorted(expected_objects & imported_objects)
        if source_parent[name] != imported_parent.get(name)
    ]

    scale_errors = [
        {"object": o["name"], "scale": o["scale"]}
        for o in imported_inventory["objects"]
        if o["type"] in ("MESH", "ARMATURE")
        and any(abs(s - 1.0) > tolerance for s in o["scale"])
    ]

    transform_errors: list[dict] = []
    for name in sorted(expected_objects & imported_objects):
        expected = source_by_name[name]
        actual = imported_by_name[name]
        if expected["type"] != "EMPTY" and name not in source_inventory.get("roots", []):
            continue
        checks = {
            "world_location": _max_vec_error(expected["world_location"], actual["world_location"]),
            "plus_y_world": _max_vec_error(expected["plus_y_world"], actual["plus_y_world"]),
            "plus_z_world": _max_vec_error(expected["plus_z_world"], actual["plus_z_world"]),
        }
        bad = {k: v for k, v in checks.items() if v > max(tolerance, 1e-4)}
        if bad:
            transform_errors.append({"object": name, "errors": bad})

    zero_root_errors: list[dict] = []
    for name in require_zero_roots or []:
        obj = imported_by_name.get(name)
        if obj is None:
            zero_root_errors.append({"object": name, "error": "missing"})
            continue
        loc_error = max(abs(v) for v in obj["location"])
        rot_error = max(abs(v) for v in obj["rotation_euler"])
        scale_error = max(abs(v - 1.0) for v in obj["scale"])
        if loc_error > tolerance or rot_error > tolerance or scale_error > tolerance:
            zero_root_errors.append({
                "object": name,
                "location": obj["location"],
                "rotation_euler": obj["rotation_euler"],
                "scale": obj["scale"],
            })

    source_tris = sum(v["tri_count"] for v in source_inventory["lods"].values())
    imported_tris = sum(v["tri_count"] for v in imported_inventory["lods"].values())
    tri_match = source_tris == imported_tris

    passed = (
        imported_inventory["object_count"] > 0
        and not missing
        and not parent_mismatches
        and not scale_errors
        and not transform_errors
        and not zero_root_errors
        and tri_match
        and binary_scan["passed"]
    )
    return {
        "checked": True,
        "passed": passed,
        "missing_objects": missing,
        "parent_mismatches": parent_mismatches,
        "scale_errors": scale_errors,
        "transform_errors": transform_errors,
        "zero_root_errors": zero_root_errors,
        "source_tri_count": source_tris,
        "imported_tri_count": imported_tris,
        "tri_count_match": tri_match,
        "embedded_images": binary_scan,
        "imported_inventory": imported_inventory,
    }


def run(
    target: str = "unity",
    profile: str | None = None,
    project_profile: str | None = None,
    out_dir: str = "build",
    asset_id: str | None = None,
    category: str = "solid_prop",
    rig_type: str = "none",
    uv1_source: str = "blender",
    fmt_override: str | None = None,
    verify_roundtrip: bool = True,
    build_script: str | None = None,
) -> dict:
    import bpy

    target_cfg, chosen_profile, _, project_data, project_path = load_profiled_target(
        target,
        texture_profile=profile,
        project_profile=project_profile,
    )
    export_cfg = target_cfg["export"]
    damage_prefix = target_cfg["qa"]["common"].get("damage_prefix")
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    source_blend = bpy.data.filepath or ""
    aid = asset_id or (Path(source_blend).stem if source_blend else "untitled_asset")
    fmt = (fmt_override or export_cfg["format"]).lower()
    export_file = out_path / f"{aid}.{fmt}"

    allowed_types = set(export_cfg.get("object_types", ["MESH", "EMPTY", "ARMATURE"]))
    objs = [o for o in bpy.context.scene.objects if o.type in allowed_types]
    if not objs:
        raise ValueError("No exportable objects found in the active scene")
    is_rigged = rig_type != "none" or any(o.type == "ARMATURE" for o in objs)
    _select_objects(objs)
    source_inventory = inspect_objects(objs, damage_prefix=damage_prefix)
    expected_inventory = export_selected(
        export_cfg, export_file, is_rigged=is_rigged, objects=objs
    )
    expected_inventory["damage_prefix"] = damage_prefix

    build_inputs = []
    if source_blend:
        build_inputs.append(Path(source_blend))
    if build_script:
        build_inputs.append(Path(build_script))
    if project_path:
        build_inputs.append(project_path)
    build_metadata = {
        "kit_version": KIT_VERSION,
        "blender_version": bpy.app.version_string,
        "target": target_cfg,
        "texture_profile": chosen_profile,
        "project_profile": project_data["name"] if project_data else None,
    }
    build_hash = compute_build_hash(build_inputs or [export_file], metadata=build_metadata)

    lods = []
    default_transitions = {0: 0.50, 1: 0.20, 2: 0.05, 3: 0.01}
    for index_text, data in source_inventory["lods"].items():
        index = int(index_text)
        lods.append({
            "name": f"{aid}_LOD{index}",
            "tri_count": int(data["tri_count"]),
            "screen_relative_transition_height": default_transitions.get(index, 0.01),
        })

    colliders = [
        {"node_name": name, "shape": "convex_mesh", "strip_renderer": True}
        for name in source_inventory["colliders"]
    ]
    manifest = {
        "schema_version": "1.0",
        "asset_id": aid,
        "category": category,
        "source_blend": source_blend,
        "build_script": build_script,
        "build_hash": build_hash,
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
        tol = float(target_cfg["qa"]["common"].get("roundtrip_armature_scale_tolerance", 0.001))
        roundtrip = roundtrip_file(export_file, expected_inventory, tol)

    return {
        "status": "ok" if (not verify_roundtrip or roundtrip["passed"]) else "error",
        "blender_version": bpy.app.version_string,
        "kit_version": KIT_VERSION,
        "build_hash": build_hash,
        "target": target_cfg["name"],
        "profile": chosen_profile,
        "project_profile": project_data["name"] if project_data else None,
        "inventory": source_inventory,
        "artifacts": {"export": str(export_file), "manifest": str(manifest_path)},
        "roundtrip": roundtrip,
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="unity")
    p.add_argument("--profile", default=None)
    p.add_argument("--project-profile", default=None)
    p.add_argument("--out", default="build")
    p.add_argument("--asset-id", default=None)
    p.add_argument("--category", default="solid_prop")
    p.add_argument("--rig-type", default="none")
    p.add_argument("--uv1-source", default="blender")
    p.add_argument("--format", default=None)
    p.add_argument("--build-script", default=None)
    p.add_argument("--no-roundtrip", action="store_true")
    ns = p.parse_args(argv)
    return run(
        target=ns.target,
        profile=ns.profile,
        project_profile=ns.project_profile,
        out_dir=ns.out,
        asset_id=ns.asset_id,
        category=ns.category,
        rig_type=ns.rig_type,
        uv1_source=ns.uv1_source,
        fmt_override=ns.format,
        verify_roundtrip=not ns.no_roundtrip,
        build_script=ns.build_script,
    )
