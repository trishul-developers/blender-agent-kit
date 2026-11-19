"""Fail-closed generic asset QA driven by target config plus optional project profile overlays."""
from __future__ import annotations

import argparse
import fnmatch

from shared.profile_loader import load_profiled_target
from shared.scene_inspector import inspect_scene

_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def _error(errors: list[dict], code: str, message: str, object_name: str | None = None) -> None:
    item = {"code": code, "error": message}
    if object_name:
        item["object"] = object_name
    errors.append(item)


def _match_required_nodes(names: set[str], patterns: list[str]) -> list[str]:
    missing: list[str] = []
    for pattern in patterns:
        if not any(fnmatch.fnmatchcase(name, pattern) for name in names):
            missing.append(pattern)
    return missing


def run(
    target: str = "unity",
    asset_class: str = "solid_prop",
    project_profile: str | None = None,
) -> dict:
    target_cfg, _, _, project_data, _ = load_profiled_target(
        target, project_profile=project_profile
    )
    common = target_cfg["qa"]["common"]
    classes = target_cfg["qa"]["asset_classes"]
    if asset_class not in classes:
        raise KeyError(f"Unknown asset_class '{asset_class}'. Available: {sorted(classes.keys())}")
    rules = classes[asset_class]

    inventory = inspect_scene()
    errors: list[dict] = []
    warnings: list[dict] = []
    names = {o["name"] for o in inventory["objects"]}

    if inventory["mesh_count"] == 0:
        _error(errors, "no_meshes", "scene contains no mesh objects")

    for obj in inventory["objects"]:
        if obj["type"] != "MESH":
            continue
        scale = obj["scale"]
        if common.get("reject_negative_scale", True) and any(s < 0 for s in scale):
            _error(errors, "negative_scale", f"negative scale: {tuple(scale)}", obj["name"])
        if common.get("require_applied_scale", True) and any(abs(s - 1.0) > 1e-4 for s in scale):
            _error(errors, "unapplied_scale", f"scale must be (1,1,1), found {tuple(scale)}", obj["name"])

        if common.get("reject_non_manifold_edges", True) and obj["non_manifold_edges"] > 0:
            _error(errors, "non_manifold", f"non-manifold edges: {obj['non_manifold_edges']}", obj["name"])
        if rules.get("reject_boundary_edges", False) and obj["boundary_edges"] > 0:
            _error(errors, "boundary_edges", f"boundary edges: {obj['boundary_edges']}", obj["name"])
        if common.get("reject_inward_normals", True):
            volume = obj.get("signed_volume")
            if volume is not None and volume < -1e-9:
                _error(errors, "inward_normals", f"closed mesh has negative signed volume {volume}", obj["name"])

        uv_layers = obj.get("uv_layers", [])
        if common.get("require_uv0", True) and not uv_layers:
            _error(errors, "missing_uv0", "missing UV0", obj["name"])
        if rules.get("require_non_overlapping_uv1", False):
            if len(uv_layers) < 2:
                _error(errors, "missing_uv1", "asset class requires a second UV layer", obj["name"])
            else:
                warnings.append({
                    "object": obj["name"],
                    "warning": "uv1_overlap_not_geometrically_verified",
                    "code": "uv1_overlap_unverified",
                })

        max_weights = rules.get("max_bone_weights_per_vertex")
        if max_weights is not None and obj.get("max_vertex_group_influences", 0) > int(max_weights):
            _error(
                errors,
                "bone_weight_limit",
                f"vertex influences ({obj['max_vertex_group_influences']}) > max ({max_weights})",
                obj["name"],
            )

    lods = {int(k): v for k, v in inventory["lods"].items()}
    budgets = rules.get("max_tris", {})
    for lod_index, budget in budgets.items():
        index = int(str(lod_index).removeprefix("lod"))
        if index in lods and lods[index]["tri_count"] > int(budget):
            _error(
                errors,
                "triangle_budget",
                f"LOD{index} triangles ({lods[index]['tri_count']}) > max ({budget})",
            )

    material_by_lod = rules.get("max_material_slots_by_lod", {})
    scalar_material_limit = rules.get("max_material_slots")
    for index, data in lods.items():
        limit = material_by_lod.get(f"lod{index}", scalar_material_limit)
        if limit is not None and data["material_count"] > int(limit):
            _error(
                errors,
                "material_budget",
                f"LOD{index} unique materials ({data['material_count']}) > max ({limit})",
            )

    ordered = sorted(lods)
    if common.get("require_monotonic_lod_tris", True) and len(ordered) > 1:
        for prev, cur in zip(ordered, ordered[1:]):
            if lods[cur]["tri_count"] >= lods[prev]["tri_count"]:
                _error(
                    errors,
                    "non_monotonic_lod",
                    f"LOD{cur} triangles ({lods[cur]['tri_count']}) must be lower than LOD{prev} ({lods[prev]['tri_count']})",
                )

    max_ratio = rules.get("max_lod_ratio", common.get("max_lod_ratio"))
    if max_ratio is not None and len(ordered) > 1:
        for prev, cur in zip(ordered, ordered[1:]):
            prev_tris = lods[prev]["tri_count"]
            cur_tris = lods[cur]["tri_count"]
            if prev_tris and (cur_tris / prev_tris) > float(max_ratio) + 1e-9:
                _error(
                    errors,
                    "lod_reduction_ratio",
                    f"LOD{prev}->LOD{cur} ratio {cur_tris / prev_tris:.4f} > max {float(max_ratio):.4f}",
                )

    required_nodes = list(rules.get("required_nodes", []))
    missing = _match_required_nodes(names, required_nodes)
    for pattern in missing:
        _error(errors, "missing_required_node", f"required node/pattern not found: {pattern}")

    parent_map = {o["name"]: o["parent"] for o in inventory["objects"]}
    for relation in rules.get("required_parent_pairs", []):
        child = relation.get("child")
        parent = relation.get("parent")
        if child in parent_map and parent_map[child] != parent:
            _error(
                errors,
                "wrong_parent",
                f"{child} parent is {parent_map[child]!r}, expected {parent!r}",
                child,
            )
        elif child not in parent_map:
            _error(errors, "missing_required_node", f"required child node not found: {child}")

    if inventory["bounds"] and rules.get("ground_axis"):
        axis_name = str(rules["ground_axis"]).upper()
        if axis_name not in _AXIS_INDEX:
            _error(errors, "invalid_profile_rule", f"unknown ground_axis {axis_name}")
        else:
            idx = _AXIS_INDEX[axis_name]
            actual = inventory["bounds"]["min"][idx]
            target_ground = float(rules.get("ground_target", 0.0))
            tolerance = float(rules.get("ground_tolerance", 0.001))
            if abs(actual - target_ground) > tolerance:
                _error(
                    errors,
                    "ground_contact",
                    f"ground minimum on {axis_name} is {actual:.6f}; expected {target_ground:.6f} ± {tolerance:.6f}",
                )

    if rules.get("pivot_rule") == "bottom_center_z0" and inventory["bounds"]:
        if len(inventory["roots"]) != 1:
            _error(errors, "pivot_rule", "bottom_center_z0 requires exactly one selected scene root")
        else:
            root_name = inventory["roots"][0]
            root = next(o for o in inventory["objects"] if o["name"] == root_name)
            b = inventory["bounds"]
            expected = [b["center"][0], b["center"][1], b["min"][2]]
            # Root entry location is local for a root, therefore world-equivalent.
            tol = float(rules.get("pivot_tolerance", 1e-3))
            if any(abs(root["location"][i] - expected[i]) > tol for i in range(3)):
                _error(
                    errors,
                    "pivot_rule",
                    f"root origin {root['location']} is not bottom-center {expected} within {tol}",
                    root_name,
                )

    return {
        "status": "ok" if not errors else "error",
        "target": target_cfg["name"],
        "project_profile": project_data["name"] if project_data else None,
        "asset_class": asset_class,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "inventory": inventory,
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="unity")
    p.add_argument("--asset-class", default="solid_prop")
    p.add_argument("--project-profile", default=None)
    ns = p.parse_args(argv)
    return run(
        target=ns.target,
        asset_class=ns.asset_class,
        project_profile=ns.project_profile,
    )
