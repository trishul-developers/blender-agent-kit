"""Generic Blender scene inventory used by QA, export, and evidence generation."""
from __future__ import annotations

import argparse
import fnmatch
import re
from collections import defaultdict

_LOD_RE = re.compile(r"(?:^|[_\-.])LOD(?P<index>\d+)(?:$|[_\-.])", re.IGNORECASE)


def _as_list(values) -> list[float]:
    return [float(v) for v in values]


def _matrix_list(matrix) -> list[list[float]]:
    return [[float(v) for v in row] for row in matrix]


def _candidate_hierarchy_names(obj) -> list[str]:
    candidates = [obj.name]
    parent = obj.parent
    while parent is not None:
        candidates.append(parent.name)
        parent = parent.parent
    candidates.extend(c.name for c in getattr(obj, "users_collection", []))
    return candidates


def lod_index(obj) -> int:
    for name in _candidate_hierarchy_names(obj):
        match = _LOD_RE.search(name)
        if match:
            return int(match.group("index"))
    return 0


def _is_excluded_from_lod(obj, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    for candidate in _candidate_hierarchy_names(obj):
        if any(fnmatch.fnmatchcase(candidate, pat) for pat in patterns):
            return True
    return False


def _world_bounds(obj) -> tuple[list[float], list[float]]:
    from mathutils import Vector

    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        [min(p[i] for p in points) for i in range(3)],
        [max(p[i] for p in points) for i in range(3)],
    )


def _basis_vectors(obj) -> tuple[list[float], list[float]]:
    from mathutils import Vector

    basis = obj.matrix_world.to_3x3()
    up = (basis @ Vector((0.0, 1.0, 0.0))).normalized()
    forward = (basis @ Vector((0.0, 0.0, 1.0))).normalized()
    return _as_list(up), _as_list(forward)


def _uv_bounds(mesh) -> list[dict]:
    result: list[dict] = []
    for layer in mesh.uv_layers:
        if not layer.data:
            continue
        us = [float(loop.uv.x) for loop in layer.data]
        vs = [float(loop.uv.y) for loop in layer.data]
        result.append({
            "name": layer.name,
            "u_min": min(us),
            "u_max": max(us),
            "u_span": max(us) - min(us),
            "v_min": min(vs),
            "v_max": max(vs),
            "v_span": max(vs) - min(vs),
        })
    return result


def _is_damage_object(obj, damage_prefix: str | None) -> bool:
    if not damage_prefix:
        return False
    cur = obj
    while cur is not None:
        if cur.name.startswith(damage_prefix):
            return True
        cur = cur.parent
    return False


def inspect_objects(
    objects=None,
    damage_prefix: str | None = None,
    lod_exclude_patterns: list[str] | None = None,
) -> dict:
    import bmesh
    import bpy

    selected = list(objects) if objects is not None else list(bpy.context.scene.objects)
    selected_set = set(selected)
    object_entries: list[dict] = []
    lod_acc: dict[int, dict] = defaultdict(lambda: {
        "tri_count": 0,
        "intact_tri_count": 0,
        "damage_tri_count": 0,
        "mesh_count": 0,
        "damage_mesh_count": 0,
        "materials": set(),
        "objects": [],
        "damage_objects": [],
    })
    collider_names: list[str] = []
    bounds_min = [float("inf")] * 3
    bounds_max = [float("-inf")] * 3
    primary_mesh_count = 0
    mesh_count = 0

    for obj in sorted(selected, key=lambda o: o.name):
        plus_y, plus_z = _basis_vectors(obj)
        excluded_from_lod = _is_excluded_from_lod(obj, lod_exclude_patterns)
        entry = {
            "name": obj.name,
            "type": obj.type,
            "parent": obj.parent.name if obj.parent and obj.parent in selected_set else None,
            "location": _as_list(obj.location),
            "world_location": _as_list(obj.matrix_world.translation),
            "rotation_euler": _as_list(obj.rotation_euler),
            "scale": _as_list(obj.scale),
            "matrix_local": _matrix_list(obj.matrix_local),
            "plus_y_world": plus_y,
            "plus_z_world": plus_z,
            "lod": lod_index(obj),
            "is_damage": _is_damage_object(obj, damage_prefix),
            "excluded_from_lod": excluded_from_lod,
        }

        if obj.type == "MESH":
            mesh_count += 1
            mesh = obj.data
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.normal_update()
            non_manifold_edges = sum(1 for e in bm.edges if len(e.link_faces) > 2)
            boundary_edges = sum(1 for e in bm.edges if len(e.link_faces) == 1)
            tri_count = sum(max(0, len(f.verts) - 2) for f in bm.faces)
            signed_volume = None
            if boundary_edges == 0 and non_manifold_edges == 0 and bm.faces:
                try:
                    signed_volume = float(bm.calc_volume(signed=True))
                except ValueError:
                    signed_volume = None
            bm.free()

            material_names = sorted({
                slot.material.name for slot in obj.material_slots if slot.material is not None
            })
            max_weights = max((len(v.groups) for v in mesh.vertices), default=0)
            bmin, bmax = _world_bounds(obj)

            entry.update({
                "tri_count": int(tri_count),
                "uv_layers": [uv.name for uv in mesh.uv_layers],
                "uv_bounds": _uv_bounds(mesh),
                "material_names": material_names,
                "material_slots": len(obj.material_slots),
                "non_manifold_edges": non_manifold_edges,
                "boundary_edges": boundary_edges,
                "signed_volume": signed_volume,
                "max_vertex_group_influences": max_weights,
                "bounds": {"min": bmin, "max": bmax},
            })
            if not excluded_from_lod:
                primary_mesh_count += 1
                for i in range(3):
                    bounds_min[i] = min(bounds_min[i], bmin[i])
                    bounds_max[i] = max(bounds_max[i], bmax[i])
                lod = lod_acc[entry["lod"]]
                lod["tri_count"] += int(tri_count)
                if entry["is_damage"]:
                    lod["damage_tri_count"] += int(tri_count)
                    lod["damage_mesh_count"] += 1
                    lod["damage_objects"].append(obj.name)
                else:
                    lod["intact_tri_count"] += int(tri_count)
                lod["mesh_count"] += 1
                lod["materials"].update(material_names)
                lod["objects"].append(obj.name)

            upper_name = obj.name.upper()
            if "_COL_" in upper_name or upper_name.endswith("_COL") or upper_name.startswith("COLLISION_"):
                collider_names.append(obj.name)

        object_entries.append(entry)

    if primary_mesh_count:
        bounds = {
            "min": bounds_min,
            "max": bounds_max,
            "size": [bounds_max[i] - bounds_min[i] for i in range(3)],
            "center": [(bounds_max[i] + bounds_min[i]) * 0.5 for i in range(3)],
        }
    else:
        bounds = None

    lods = {
        str(index): {
            "tri_count": data["tri_count"],
            "intact_tri_count": data["intact_tri_count"],
            "damage_tri_count": data["damage_tri_count"],
            "mesh_count": data["mesh_count"],
            "damage_mesh_count": data["damage_mesh_count"],
            "material_count": len(data["materials"]),
            "materials": sorted(data["materials"]),
            "objects": sorted(data["objects"]),
            "damage_objects": sorted(data["damage_objects"]),
        }
        for index, data in sorted(lod_acc.items())
    }
    roots = sorted(
        o.name for o in selected
        if o.parent is None or o.parent not in selected_set
    )
    return {
        "object_count": len(selected),
        "mesh_count": mesh_count,
        "damage_prefix": damage_prefix,
        "roots": roots,
        "bounds": bounds,
        "lods": lods,
        "colliders": sorted(collider_names),
        "objects": object_entries,
    }


def inspect_scene(
    damage_prefix: str | None = None,
    lod_exclude_patterns: list[str] | None = None,
) -> dict:
    return inspect_objects(
        damage_prefix=damage_prefix,
        lod_exclude_patterns=lod_exclude_patterns,
    )


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--damage-prefix", default=None)
    ns = p.parse_args(argv)
    import bpy

    return {
        "status": "ok",
        "blender_version": bpy.app.version_string,
        "inventory": inspect_scene(damage_prefix=ns.damage_prefix),
    }
