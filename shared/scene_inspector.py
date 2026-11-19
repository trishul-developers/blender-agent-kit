"""Generic Blender scene inventory used by QA, bundle export, and evidence generation."""
from __future__ import annotations

import argparse
import re
from collections import defaultdict

_LOD_RE = re.compile(r"(?:^|[_\-.])LOD(?P<index>\d+)(?:$|[_\-.])", re.IGNORECASE)


def _as_list(values) -> list[float]:
    return [float(v) for v in values]


def _lod_index(obj) -> int:
    candidates = [obj.name]
    parent = obj.parent
    while parent is not None:
        candidates.append(parent.name)
        parent = parent.parent
    candidates.extend(c.name for c in getattr(obj, "users_collection", []))
    for name in candidates:
        match = _LOD_RE.search(name)
        if match:
            return int(match.group("index"))
    return 0


def _world_bounds(obj) -> tuple[list[float], list[float]]:
    from mathutils import Vector

    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        [min(p[i] for p in points) for i in range(3)],
        [max(p[i] for p in points) for i in range(3)],
    )


def inspect_objects(objects=None) -> dict:
    import bmesh
    import bpy

    selected = list(objects) if objects is not None else list(bpy.context.scene.objects)
    selected_set = set(selected)
    object_entries: list[dict] = []
    lod_acc: dict[int, dict] = defaultdict(lambda: {
        "tri_count": 0,
        "mesh_count": 0,
        "materials": set(),
        "objects": [],
    })
    collider_names: list[str] = []
    bounds_min = [float("inf")] * 3
    bounds_max = [float("-inf")] * 3
    mesh_count = 0

    for obj in sorted(selected, key=lambda o: o.name):
        entry = {
            "name": obj.name,
            "type": obj.type,
            "parent": obj.parent.name if obj.parent and obj.parent in selected_set else None,
            "location": _as_list(obj.location),
            "rotation_euler": _as_list(obj.rotation_euler),
            "scale": _as_list(obj.scale),
            "lod": _lod_index(obj),
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
            for i in range(3):
                bounds_min[i] = min(bounds_min[i], bmin[i])
                bounds_max[i] = max(bounds_max[i], bmax[i])

            entry.update({
                "tri_count": int(tri_count),
                "uv_layers": [uv.name for uv in mesh.uv_layers],
                "material_names": material_names,
                "material_slots": len(obj.material_slots),
                "non_manifold_edges": non_manifold_edges,
                "boundary_edges": boundary_edges,
                "signed_volume": signed_volume,
                "max_vertex_group_influences": max_weights,
                "bounds": {"min": bmin, "max": bmax},
            })
            lod = lod_acc[entry["lod"]]
            lod["tri_count"] += int(tri_count)
            lod["mesh_count"] += 1
            lod["materials"].update(material_names)
            lod["objects"].append(obj.name)

            upper_name = obj.name.upper()
            if "_COL_" in upper_name or upper_name.endswith("_COL") or upper_name.startswith("COLLISION_"):
                collider_names.append(obj.name)

        object_entries.append(entry)

    if mesh_count:
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
            "mesh_count": data["mesh_count"],
            "material_count": len(data["materials"]),
            "materials": sorted(data["materials"]),
            "objects": sorted(data["objects"]),
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
        "roots": roots,
        "bounds": bounds,
        "lods": lods,
        "colliders": sorted(collider_names),
        "objects": object_entries,
    }


def inspect_scene() -> dict:
    return inspect_objects()


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.parse_args(argv)
    import bpy

    return {
        "status": "ok",
        "blender_version": bpy.app.version_string,
        "inventory": inspect_scene(),
    }
