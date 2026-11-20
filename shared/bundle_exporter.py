"""Semantic multi-part bundle exporter for compound game assets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared.exporter import compute_build_hash, export_selected, roundtrip_file
from shared.profile_loader import load_profiled_target
from shared.scene_inspector import collider_patterns_from_naming, inspect_objects
from shared.version import KIT_VERSION


def validate_bundle_spec(data: dict) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if not data.get("asset_id"):
        errors.append("asset_id is required")
    parts = data.get("parts")
    if not isinstance(parts, list) or not parts:
        errors.append("parts must be a non-empty array")
        return errors

    seen: set[str] = set()
    for index, part in enumerate(parts):
        pid = part.get("id")
        if not pid:
            errors.append(f"parts[{index}].id is required")
        elif pid in seen:
            errors.append(f"duplicate part id: {pid}")
        else:
            seen.add(pid)
        selectors = [key for key in ("collection", "root") if part.get(key)]
        if len(selectors) != 1:
            errors.append(f"part {pid or index} must define exactly one of collection or root")
        if "zero_root_location" in part and not isinstance(part["zero_root_location"], bool):
            errors.append(f"part {pid or index} zero_root_location must be boolean")
    return errors


def _collection_objects(collection) -> list:
    result = list(collection.objects)
    for child in collection.children:
        result.extend(_collection_objects(child))
    unique = {obj.name: obj for obj in result}
    return [unique[name] for name in sorted(unique)]


def _root_objects(root) -> list:
    result = [root]
    stack = list(root.children)
    while stack:
        obj = stack.pop()
        result.append(obj)
        stack.extend(obj.children)
    return sorted(result, key=lambda o: o.name)


def _resolve_part_objects(part: dict, allowed_types: set[str]) -> tuple[list, object | None]:
    import bpy

    explicit_root = None
    if part.get("collection"):
        collection = bpy.data.collections.get(part["collection"])
        if collection is None:
            raise KeyError(f"Bundle part '{part['id']}' collection not found: {part['collection']}")
        objects = _collection_objects(collection)
    else:
        explicit_root = bpy.data.objects.get(part["root"])
        if explicit_root is None:
            raise KeyError(f"Bundle part '{part['id']}' root not found: {part['root']}")
        objects = _root_objects(explicit_root)

    filtered = [o for o in objects if o.type in allowed_types]
    if not filtered:
        raise ValueError(f"Bundle part '{part['id']}' selected no exportable objects")

    selected_set = set(filtered)
    roots = [o for o in filtered if o.parent is None or o.parent not in selected_set]
    inferred_root = explicit_root or (roots[0] if len(roots) == 1 else None)
    return filtered, inferred_root


def _select(objects) -> None:
    import bpy

    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def _zero_root_default(part: dict, project_data: dict | None = None) -> bool:
    if "zero_root_location" in part:
        return bool(part["zero_root_location"])
    default_roles = set(
        (project_data or {})
        .get("bundle_defaults", {})
        .get("zero_root_location_roles", [])
    )
    return part.get("role") in default_roles


def run(
    spec_path: str,
    target: str = "unity",
    profile: str | None = None,
    project_profile: str | None = None,
    out_dir: str = "build",
    verify_roundtrip: bool = True,
) -> dict:
    import bpy

    spec_file = Path(spec_path).resolve()
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    errors = validate_bundle_spec(spec)
    if errors:
        raise ValueError("Invalid bundle spec: " + "; ".join(errors))

    target_cfg, chosen_profile, _, project_data, project_path = load_profiled_target(
        target,
        texture_profile=profile,
        project_profile=project_profile,
    )
    export_cfg = target_cfg["export"]
    naming = target_cfg.get("naming", {})
    damage_prefix = target_cfg["qa"]["common"].get("damage_prefix")
    allowed_types = set(export_cfg.get("object_types", ["MESH", "EMPTY", "ARMATURE"]))
    output = Path(out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    source_blend = bpy.data.filepath or ""
    exported_parts: list[dict] = []
    roundtrip_sources: list[tuple[Path, dict, dict, list[str]]] = []

    for part in spec["parts"]:
        objects, root_object = _resolve_part_objects(part, allowed_types)
        _select(objects)
        assembly_inventory = inspect_objects(
            objects,
            damage_prefix=damage_prefix,
            lod_pattern=naming.get("lod_pattern"),
            collider_patterns=collider_patterns_from_naming(naming),
        )
        fmt = str(part.get("format") or export_cfg["format"]).lower()
        filename = part.get("file") or f"{part['id']}.{fmt}"
        export_file = output / filename
        export_file.parent.mkdir(parents=True, exist_ok=True)
        is_rigged = any(o.type == "ARMATURE" for o in objects)

        zero_root = _zero_root_default(part, project_data=project_data)
        if zero_root and root_object is None:
            raise ValueError(
                f"Bundle part '{part['id']}' requests zero_root_location but does not resolve to one root"
            )

        export_inventory = export_selected(
            export_cfg,
            export_file,
            is_rigged=is_rigged,
            objects=objects,
            zero_root_object=root_object if zero_root else None,
            lod_pattern=naming.get("lod_pattern"),
            collider_patterns=collider_patterns_from_naming(naming),
        )
        export_inventory["damage_prefix"] = damage_prefix
        export_root_name = None
        if root_object is not None:
            export_root_name = export_inventory.get("export_name_map", {}).get(
                root_object.name, root_object.name
            )

        tri_count = sum(v["tri_count"] for v in assembly_inventory["lods"].values())
        intact_tri_count = sum(v["intact_tri_count"] for v in assembly_inventory["lods"].values())
        damage_tri_count = sum(v["damage_tri_count"] for v in assembly_inventory["lods"].values())
        materials = sorted({
            material
            for lod in assembly_inventory["lods"].values()
            for material in lod["materials"]
        })
        result = {
            "id": part["id"],
            "role": part.get("role", "primary"),
            "lod": part.get("lod"),
            "file": str(export_file.relative_to(output)).replace("\\", "/"),
            "zero_root_location": zero_root,
            "export_root": export_root_name,
            "tri_count": tri_count,
            "intact_tri_count": intact_tri_count,
            "damage_tri_count": damage_tri_count,
            "material_count": len(materials),
            "materials": materials,
            "roots": assembly_inventory["roots"],
            "object_count": assembly_inventory["object_count"],
            "assembly_inventory": assembly_inventory,
            "inventory": export_inventory,
            "roundtrip": {"checked": False},
        }
        exported_parts.append(result)
        required_zero = [export_root_name] if zero_root and export_root_name else []
        roundtrip_sources.append((export_file, export_inventory, result, required_zero))

    tolerance = float(target_cfg["qa"]["common"].get("roundtrip_armature_scale_tolerance", 0.001))
    if verify_roundtrip:
        for export_file, source_inventory, result, required_zero in roundtrip_sources:
            result["roundtrip"] = roundtrip_file(
                export_file,
                source_inventory,
                tolerance,
                require_zero_roots=required_zero,
            )

    build_inputs = [spec_file]
    if source_blend:
        build_inputs.append(Path(source_blend))
    if project_path:
        build_inputs.append(project_path)
    for extra in spec.get("build_inputs", []):
        build_inputs.append(Path(extra))

    build_hash = compute_build_hash(
        build_inputs,
        metadata={
            "kit_version": KIT_VERSION,
            "blender_version": bpy.app.version_string,
            "target": target_cfg,
            "texture_profile": chosen_profile,
            "project_profile": project_data["name"] if project_data else None,
            "bundle_spec": spec,
        },
    )

    manifest = {
        "schema_version": "1.0",
        "asset_id": spec["asset_id"],
        "source_blend": source_blend,
        "build_hash": build_hash,
        "blender_version": bpy.app.version_string,
        "kit_version": KIT_VERSION,
        "target": target_cfg["name"],
        "policy": target_cfg.get("default_policy"),
        "profile": chosen_profile,
        "project_profile": project_data["name"] if project_data else None,
        "parts": exported_parts,
    }
    manifest_path = output / f"{spec['asset_id']}.bundle.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    passed = all(
        (not verify_roundtrip) or part["roundtrip"].get("passed", False)
        for part in exported_parts
    )
    return {
        "status": "ok" if passed else "error",
        "asset_id": spec["asset_id"],
        "build_hash": build_hash,
        "target": target_cfg["name"],
        "policy": target_cfg.get("default_policy"),
        "profile": chosen_profile,
        "project_profile": project_data["name"] if project_data else None,
        "parts": exported_parts,
        "artifacts": {"manifest": str(manifest_path)},
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--spec", required=True)
    p.add_argument("--target", default="unity")
    p.add_argument("--profile", default=None)
    p.add_argument("--project-profile", default=None)
    p.add_argument("--out", default="build")
    p.add_argument("--no-roundtrip", action="store_true")
    ns = p.parse_args(argv)
    return run(
        spec_path=ns.spec,
        target=ns.target,
        profile=ns.profile,
        project_profile=ns.project_profile,
        out_dir=ns.out,
        verify_roundtrip=not ns.no_roundtrip,
    )
