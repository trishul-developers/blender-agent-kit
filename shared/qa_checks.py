"""Fail-closed generic asset QA driven by target config plus optional project profiles."""
from __future__ import annotations

import argparse
import fnmatch
from collections import defaultdict

from shared.profile_loader import load_profiled_target
from shared.scene_inspector import inspect_scene

_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def _error(errors: list[dict], code: str, message: str, object_name: str | None = None) -> None:
    item = {"code": code, "error": message}
    if object_name:
        item["object"] = object_name
    errors.append(item)


def _match_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _match_required_nodes(names: set[str], patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if not any(fnmatch.fnmatchcase(name, pattern) for name in names)]


def _axis_value(mapping: dict | float | int, axis: str, default: float) -> float:
    if isinstance(mapping, (int, float)):
        return float(mapping)
    if isinstance(mapping, dict):
        return float(mapping.get(axis, mapping.get(axis.lower(), default)))
    return default


def _bounds_for_entries(entries: list[dict]) -> dict | None:
    if not entries:
        return None
    mins = [min(e["bounds"]["min"][i] for e in entries) for i in range(3)]
    maxs = [max(e["bounds"]["max"][i] for e in entries) for i in range(3)]
    return {
        "min": mins,
        "max": maxs,
        "size": [maxs[i] - mins[i] for i in range(3)],
        "center": [(maxs[i] + mins[i]) * 0.5 for i in range(3)],
    }


def _descendant_names(inventory: dict, root_name: str) -> set[str]:
    children: dict[str, list[str]] = defaultdict(list)
    for obj in inventory["objects"]:
        if obj.get("parent"):
            children[obj["parent"]].append(obj["name"])
    result = {root_name}
    stack = [root_name]
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            if child not in result:
                result.add(child)
                stack.append(child)
    return result


def _subtree_metrics(inventory: dict, root_name: str) -> dict:
    names = _descendant_names(inventory, root_name)
    meshes = [o for o in inventory["objects"] if o["name"] in names and o["type"] == "MESH"]
    bounds = _bounds_for_entries(meshes)
    return {
        "tri_count": sum(int(o.get("tri_count", 0)) for o in meshes),
        "abs_signed_volume": sum(abs(float(o["signed_volume"])) for o in meshes if o.get("signed_volume") is not None),
        "bounds": bounds,
        "mesh_count": len(meshes),
    }


def _check_lod_metric(
    errors: list[dict],
    lods: dict[int, dict],
    ordered: list[int],
    metric: str,
    label: str,
    require_monotonic: bool,
    max_ratio: float | None,
) -> None:
    if len(ordered) <= 1:
        return
    for prev, cur in zip(ordered, ordered[1:]):
        prev_value = int(lods[prev].get(metric, 0))
        cur_value = int(lods[cur].get(metric, 0))
        if require_monotonic and cur_value >= prev_value and prev_value > 0:
            _error(
                errors,
                f"non_monotonic_lod_{label}",
                f"{label} LOD{cur} triangles ({cur_value}) must be lower than LOD{prev} ({prev_value})",
            )
        if max_ratio is not None and prev_value > 0:
            ratio = cur_value / prev_value
            if ratio > max_ratio + 1e-9:
                _error(
                    errors,
                    f"lod_reduction_ratio_{label}",
                    f"{label} LOD{prev}->LOD{cur} ratio {ratio:.4f} > max {max_ratio:.4f}",
                )


def _check_symmetry(errors: list[dict], inventory: dict, rule: dict) -> list[dict]:
    reports: list[dict] = []
    if not rule or rule.get("enabled", True) is False:
        return reports
    axis = str(rule.get("axis", "X")).upper()
    if axis not in _AXIS_INDEX:
        _error(errors, "invalid_symmetry_rule", f"unknown symmetry axis {axis}")
        return reports
    axis_idx = _AXIS_INDEX[axis]
    left_token = str(rule.get("left_token", "_L"))
    right_token = str(rule.get("right_token", "_R"))
    include = list(rule.get("include_patterns", ["*"]))
    exclude = list(rule.get("exclude_patterns", []))
    names = {o["name"] for o in inventory["objects"] if not o.get("excluded_from_lod")}
    left_names = sorted(
        name for name in names
        if left_token in name
        and _match_any(name, include)
        and (not exclude or not _match_any(name, exclude))
    )
    tri_tolerance = int(rule.get("tri_tolerance", 0))
    bounds_tolerance = float(rule.get("bounds_tolerance", 0.02))
    volume_rel_tolerance = float(rule.get("volume_relative_tolerance", 0.05))
    require_pairs = bool(rule.get("require_pairs", True))

    checked: set[tuple[str, str]] = set()
    for left_name in left_names:
        right_name = left_name.replace(left_token, right_token, 1)
        pair = (left_name, right_name)
        if pair in checked:
            continue
        checked.add(pair)
        if right_name not in names:
            if require_pairs:
                _error(errors, "symmetry_missing_pair", f"missing mirror pair for {left_name}: {right_name}", left_name)
            continue

        left = _subtree_metrics(inventory, left_name)
        right = _subtree_metrics(inventory, right_name)
        if abs(left["tri_count"] - right["tri_count"]) > tri_tolerance:
            _error(
                errors,
                "symmetry_tri_count",
                f"{left_name}/{right_name} triangle mismatch {left['tri_count']} vs {right['tri_count']}",
            )

        if left["bounds"] and right["bounds"]:
            lb = left["bounds"]
            rb = right["bounds"]
            for i in range(3):
                if i == axis_idx:
                    e1 = abs(lb["min"][i] + rb["max"][i])
                    e2 = abs(lb["max"][i] + rb["min"][i])
                else:
                    e1 = abs(lb["min"][i] - rb["min"][i])
                    e2 = abs(lb["max"][i] - rb["max"][i])
                if max(e1, e2) > bounds_tolerance:
                    _error(
                        errors,
                        "symmetry_bounds",
                        f"{left_name}/{right_name} mirrored {axis} bounds error {max(e1, e2):.6f} > {bounds_tolerance:.6f}",
                    )
                    break

        lv = left["abs_signed_volume"]
        rv = right["abs_signed_volume"]
        reports.append({
            "left": left_name,
            "right": right_name,
            "left_tri_count": left["tri_count"],
            "right_tri_count": right["tri_count"],
            "left_bounds": left["bounds"],
            "right_bounds": right["bounds"],
            "left_abs_signed_volume": lv,
            "right_abs_signed_volume": rv,
        })
        if lv > 0 and rv > 0:
            rel = abs(lv - rv) / max(lv, rv)
            if rel > volume_rel_tolerance:
                _error(
                    errors,
                    "symmetry_volume",
                    f"{left_name}/{right_name} signed-volume magnitude differs by {rel:.4f} > {volume_rel_tolerance:.4f}",
                )
    return reports


def _check_dimension_boxes(errors: list[dict], inventory: dict, rules: list[dict]) -> list[dict]:
    reports: list[dict] = []
    mesh_entries = [o for o in inventory["objects"] if o["type"] == "MESH"]
    for rule in rules:
        rid = str(rule.get("id", "dimension_box"))
        include = list(rule.get("include_patterns", []))
        exclude = list(rule.get("exclude_patterns", []))
        lods = {int(v) for v in rule.get("lods", [])}
        entries = [
            o for o in mesh_entries
            if (not include or _match_any(o["name"], include))
            and (not exclude or not _match_any(o["name"], exclude))
            and (not lods or int(o["lod"]) in lods)
        ]
        bounds = _bounds_for_entries(entries)
        if bounds is None:
            _error(errors, "dimension_box_missing", f"{rid}: no meshes matched selectors {include}")
            continue

        reports.append({
            "id": rid,
            "matched_objects": [o["name"] for o in entries],
            "lods": sorted(lods),
            "bounds": bounds,
            "expected_size": rule.get("expected_size", {}),
            "expected_min": rule.get("expected_min", {}),
            "expected_max": rule.get("expected_max", {}),
            "tolerance": rule.get("tolerance", 0.0),
        })
        tolerance = rule.get("tolerance", 0.0)
        for field, source_key in (("expected_size", "size"), ("expected_min", "min"), ("expected_max", "max")):
            expected = rule.get(field, {})
            for axis, target in expected.items():
                axis_name = str(axis).upper()
                if axis_name not in _AXIS_INDEX:
                    _error(errors, "invalid_dimension_rule", f"{rid}: unknown axis {axis_name}")
                    continue
                actual = float(bounds[source_key][_AXIS_INDEX[axis_name]])
                tol = _axis_value(tolerance, axis_name, 0.0)
                if abs(actual - float(target)) > tol:
                    _error(
                        errors,
                        "dimension_box",
                        f"{rid} {source_key}.{axis_name}={actual:.4f}, expected {float(target):.4f} ± {tol:.4f}",
                    )
    return reports


def _uv_layer_bounds(obj: dict, rule: dict) -> dict | None:
    bounds = list(obj.get("uv_bounds", []))
    if not bounds:
        return None
    if rule.get("uv_layer_name"):
        name = str(rule["uv_layer_name"])
        base = next((b for b in bounds if b["name"] == name), None)
    else:
        index = int(rule.get("uv_layer_index", 0))
        base = bounds[index] if 0 <= index < len(bounds) else None
    if base is None:
        return None
    if not any(k in rule for k in ("face_u_min_gte", "face_u_max_lte", "exclude_face_u_min_gte")):
        return base

    import bpy

    b_obj = bpy.data.objects.get(obj["name"])
    if b_obj is None or b_obj.type != "MESH":
        return base
    mesh = b_obj.data
    layer = mesh.uv_layers.get(base["name"])
    if layer is None or not layer.data:
        return None

    face_u_min_gte = rule.get("face_u_min_gte")
    face_u_max_lte = rule.get("face_u_max_lte")
    exclude_face_u_min_gte = rule.get("exclude_face_u_min_gte")

    us: list[float] = []
    vs: list[float] = []
    for poly in mesh.polygons:
        f_us = [float(layer.data[li].uv.x) for li in poly.loop_indices]
        f_vs = [float(layer.data[li].uv.y) for li in poly.loop_indices]
        if not f_us:
            continue
        f_u_min = min(f_us)
        f_u_max = max(f_us)
        if face_u_min_gte is not None and f_u_min < float(face_u_min_gte):
            continue
        if face_u_max_lte is not None and f_u_max > float(face_u_max_lte):
            continue
        if exclude_face_u_min_gte is not None and f_u_min >= float(exclude_face_u_min_gte):
            continue
        us.extend(f_us)
        vs.extend(f_vs)

    if not us:
        return None
    return {
        "name": base["name"],
        "u_min": min(us),
        "u_max": max(us),
        "u_span": max(us) - min(us),
        "v_min": min(vs),
        "v_max": max(vs),
        "v_span": max(vs) - min(vs),
    }


def _check_uv_rules(errors: list[dict], inventory: dict, rules: list[dict]) -> list[dict]:
    reports: list[dict] = []
    for rule in rules:
        rid = str(rule.get("id", "uv"))
        patterns = list(rule.get("patterns", []))
        exclude_patterns = list(rule.get("exclude_patterns", []))
        lods = {int(v) for v in rule.get("lods", [])}
        matches = [
            obj for obj in inventory["objects"]
            if obj["type"] == "MESH"
            and not obj.get("excluded_from_lod")
            and (not patterns or _match_any(obj["name"], patterns))
            and (not exclude_patterns or not _match_any(obj["name"], exclude_patterns))
            and (not lods or int(obj["lod"]) in lods)
        ]
        if not matches:
            if rule.get("required", True):
                _error(errors, "uv_rule_missing", f"{rid}: no mesh matched patterns={patterns} lods={sorted(lods)}")
            continue

        for obj in matches:
            uv = _uv_layer_bounds(obj, rule)
            if uv is None:
                _error(errors, "uv_rule_missing_layer", f"{rid}: requested UV layer missing", obj["name"])
                continue
            reports.append({"id": rid, "object": obj["name"], "lod": obj["lod"], "uv": uv})
            checks = [
                ("min_v_span", "v_span", lambda actual, target: actual >= target),
                ("min_u_span", "u_span", lambda actual, target: actual >= target),
                ("u_min_gte", "u_min", lambda actual, target: actual >= target),
                ("u_max_lte", "u_max", lambda actual, target: actual <= target),
                ("v_min_gte", "v_min", lambda actual, target: actual >= target),
                ("v_max_lte", "v_max", lambda actual, target: actual <= target),
            ]
            for rule_key, field, predicate in checks:
                if rule_key not in rule:
                    continue
                actual = float(uv[field])
                target = float(rule[rule_key])
                if not predicate(actual, target):
                    _error(
                        errors,
                        "uv_rule",
                        f"{rid}: {field}={actual:.4f} violates {rule_key}={target:.4f}",
                        obj["name"],
                    )
    return reports


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
    damage_prefix = rules.get("damage_prefix", common.get("damage_prefix"))
    lod_exclude_patterns = list(
        rules.get("lod_exclude_patterns", common.get("lod_exclude_patterns", []))
    )

    naming = target_cfg.get("naming", {})
    inventory = inspect_scene(
        damage_prefix=damage_prefix,
        lod_exclude_patterns=lod_exclude_patterns,
        lod_pattern=naming.get("lod_pattern"),
        collider_patterns=naming.get("collider_patterns") or naming.get("collider_pattern"),
    )
    errors: list[dict] = []
    warnings: list[dict] = []
    names = {o["name"] for o in inventory["objects"]}
    collider_set = set(inventory.get("colliders", []))

    if inventory["mesh_count"] == 0:
        _error(errors, "no_meshes", "scene contains no mesh objects")

    for obj in inventory["objects"]:
        if obj["type"] != "MESH":
            continue
        is_collider = obj["name"] in collider_set
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
        if not is_collider and common.get("require_uv0", True) and not uv_layers:
            _error(errors, "missing_uv0", "missing UV0", obj["name"])
        if not is_collider and rules.get("require_non_overlapping_uv1", False):
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
        if index not in lods:
            continue
        total = int(lods[index]["tri_count"])
        intact = int(lods[index].get("intact_tri_count", total))
        if total > int(budget):
            _error(errors, "triangle_budget_total", f"LOD{index} total triangles ({total}) > max ({budget})")
        if damage_prefix and intact > int(budget):
            _error(errors, "triangle_budget_intact", f"LOD{index} intact triangles ({intact}) > max ({budget})")

    if damage_prefix:
        allowed_damage_lods = set(int(v) for v in rules.get(
            "damage_allowed_lods",
            common.get("damage_allowed_lods", [0, 1]),
        ))
        for index, data in lods.items():
            if int(data.get("damage_tri_count", 0)) > 0 and index not in allowed_damage_lods:
                _error(
                    errors,
                    "damage_lod_leak",
                    f"LOD{index} contains damage geometry {data.get('damage_objects', [])}; allowed LODs: {sorted(allowed_damage_lods)}",
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
    require_monotonic = bool(common.get("require_monotonic_lod_tris", True))
    max_ratio_value = rules.get("max_lod_ratio", common.get("max_lod_ratio"))
    max_ratio = float(max_ratio_value) if max_ratio_value is not None else None
    _check_lod_metric(errors, lods, ordered, "tri_count", "total", require_monotonic, max_ratio)
    if damage_prefix:
        _check_lod_metric(errors, lods, ordered, "intact_tri_count", "intact", require_monotonic, max_ratio)

    for pattern in _match_required_nodes(names, list(rules.get("required_nodes", []))):
        _error(errors, "missing_required_node", f"required node/pattern not found: {pattern}")

    parent_map = {o["name"]: o["parent"] for o in inventory["objects"]}
    for relation in rules.get("required_parent_pairs", []):
        child = relation.get("child")
        parent = relation.get("parent")
        if child in parent_map and parent_map[child] != parent:
            _error(errors, "wrong_parent", f"{child} parent is {parent_map[child]!r}, expected {parent!r}", child)
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
            tol = float(rules.get("pivot_tolerance", 1e-3))
            if any(abs(root["location"][i] - expected[i]) > tol for i in range(3)):
                _error(errors, "pivot_rule", f"root origin {root['location']} is not bottom-center {expected} within {tol}", root_name)

    symmetry_report = _check_symmetry(errors, inventory, rules.get("mirror_symmetry", {}))
    dimension_report = _check_dimension_boxes(errors, inventory, list(rules.get("dimension_boxes", [])))
    uv_report = _check_uv_rules(errors, inventory, list(rules.get("uv_checks", [])))

    return {
        "status": "ok" if not errors else "error",
        "target": target_cfg["name"],
        "project_profile": project_data["name"] if project_data else None,
        "asset_class": asset_class,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "evidence": {
            "symmetry": symmetry_report,
            "dimensions": dimension_report,
            "uv": uv_report,
        },
        "inventory": inventory,
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="unity")
    p.add_argument("--asset-class", default="solid_prop")
    p.add_argument("--project-profile", default=None)
    ns = p.parse_args(argv)
    return run(target=ns.target, asset_class=ns.asset_class, project_profile=ns.project_profile)
