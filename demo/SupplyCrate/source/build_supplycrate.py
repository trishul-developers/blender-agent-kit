#!/usr/bin/env python3
"""Deterministic Blender 5.2+ procedural builder for SupplyCrate (Independent Trial).

Builds from scratch:
  - SupplyCrate_LOD0 (full detail: recessed planks, timber frame, diagonal braces,
    bottom skids, 8 steel corner brackets, tension straps, front draw latches,
    rear barrel hinges, recessed side handles, hex fasteners)
  - SupplyCrate_LOD1 (moderate reduction: removes small fasteners/bevels, keeps core silhouette)
  - SupplyCrate_LOD2 (aggressive reduction: simplified crate hull, corner caps, skids)
  - SupplyCrate_COL_01 (simplified closed convex collision proxy, 12 tris)

Dimensions (Metric, 1 BU = 1 m):
  Width  (X): 1.10 m
  Depth  (Y): 0.80 m
  Height (Z): 0.72 m
  Pivot: bottom_center_z0 at (0, 0, 0), Z in [0.0, 0.72]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector


# Atlas UV regions: (u_min, v_min, u_max, v_max) with inner margin to prevent bleeding
UV_WOOD_PLANKS = (0.02, 0.52, 0.48, 0.98)
UV_WOOD_STENCIL = (0.52, 0.52, 0.98, 0.98)
UV_STEEL = (0.02, 0.02, 0.48, 0.48)
UV_WOOD_FRAME = (0.52, 0.16, 0.98, 0.48)
UV_FASTENER = (0.89, 0.02, 0.98, 0.11)


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def _assign_box_uvs(bm: bmesh.types.BMesh, faces: list, uv_layer, region: tuple[float, float, float, float], scale: float = 1.0, fit_planar_axis: str | None = None, planar_bounds: tuple[float, float, float, float] | None = None) -> None:
    u0, v0, u1, v1 = region
    du, dv = u1 - u0, v1 - v0

    if fit_planar_axis in ("X", "Y", "Z"):
        coords = []
        for f in faces:
            for loop in f.loops:
                co = loop.vert.co
                if fit_planar_axis == "Y":
                    coords.append((co.x, co.z))
                elif fit_planar_axis == "X":
                    coords.append((co.y, co.z))
                else:
                    coords.append((co.x, co.y))
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        if planar_bounds is not None:
            xmin, xmax, ymin, ymax = planar_bounds
        else:
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
        dx = max(xmax - xmin, 1e-5)
        dy = max(ymax - ymin, 1e-5)
        for f in faces:
            for loop in f.loops:
                co = loop.vert.co
                if fit_planar_axis == "Y":
                    a, b = co.x, co.z
                elif fit_planar_axis == "X":
                    a, b = co.y, co.z
                else:
                    a, b = co.x, co.y
                lu = u0 + ((a - xmin) / dx) * du
                lv = v0 + ((b - ymin) / dy) * dv
                loop[uv_layer].uv = (lu, lv)
        return

    for f in faces:
        n = f.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        # Compute local face bounds for clean normalized projection
        proj = []
        for loop in f.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                proj.append((co.x, co.y))
            elif ax >= ay and ax >= az:
                proj.append((co.y, co.z))
            else:
                proj.append((co.x, co.z))
        xs = [p[0] for p in proj]
        ys = [p[1] for p in proj]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        span_x = max(xmax - xmin, 1e-4)
        span_y = max(ymax - ymin, 1e-4)
        # Scale proportionally within region while staying strictly inside [u0, u1] x [v0, v1]
        for loop, (px, py) in zip(f.loops, proj):
            nx = (px - xmin) / max(span_x, 1.0 / scale) if scale > 0 else (px - xmin) / span_x
            ny = (py - ymin) / max(span_y, 1.0 / scale) if scale > 0 else (py - ymin) / span_y
            lu = u0 + max(0.0, min(1.0, nx)) * du
            lv = v0 + max(0.0, min(1.0, ny)) * dv
            loop[uv_layer].uv = (lu, lv)


def add_box(
    bm: bmesh.types.BMesh,
    uv_layer,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    region: tuple[float, float, float, float],
    bevel: float = 0.0,
    bevel_segments: int = 1,
    rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
    fit_planar_axis: str | None = None,
    planar_bounds: tuple[float, float, float, float] | None = None,
) -> None:
    """Create a closed manifold box (optionally beveled) and assign UVs in `region`."""
    mat = (
        Matrix.Translation(Vector(center))
        @ Matrix.Rotation(rot_euler[2], 4, "Z")
        @ Matrix.Rotation(rot_euler[1], 4, "Y")
        @ Matrix.Rotation(rot_euler[0], 4, "X")
        @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    )
    ret = bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
    verts = ret["verts"]
    vert_set = set(verts)
    edges = [e for e in bm.edges if e.verts[0] in vert_set and e.verts[1] in vert_set]
    faces = [f for f in bm.faces if all(v in vert_set for v in f.verts)]

    if bevel > 0.0:
        b_ret = bmesh.ops.bevel(
            bm,
            geom=edges,
            offset=bevel,
            segments=bevel_segments,
            profile=0.5,
            affect="EDGES",
            clamp_overlap=True,
        )
        faces = list(set(faces) | set(b_ret.get("faces", [])))
        # Ensure all newly created faces touching beveled verts are included
        new_verts = set(b_ret.get("verts", [])) | vert_set
        faces = [f for f in bm.faces if all(v in new_verts for v in f.verts)]

    bm.faces.ensure_lookup_table()
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    _assign_box_uvs(bm, faces, uv_layer, region, scale=1.0, fit_planar_axis=fit_planar_axis, planar_bounds=planar_bounds)


def add_cylinder(
    bm: bmesh.types.BMesh,
    uv_layer,
    center: tuple[float, float, float],
    radius: float,
    depth: float,
    segments: int,
    region: tuple[float, float, float, float],
    rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    mat = (
        Matrix.Translation(Vector(center))
        @ Matrix.Rotation(rot_euler[2], 4, "Z")
        @ Matrix.Rotation(rot_euler[1], 4, "Y")
        @ Matrix.Rotation(rot_euler[0], 4, "X")
    )
    ret = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=depth,
        matrix=mat,
    )
    vert_set = set(ret["verts"])
    faces = [f for f in bm.faces if all(v in vert_set for v in f.verts)]
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    _assign_box_uvs(bm, faces, uv_layer, region, scale=4.0)


def build_crate_mesh(name: str, lod: int, material: bpy.types.Material) -> bpy.types.Object:
    """Build SupplyCrate mesh at LOD 0, 1, or 2."""
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")

    # Overall dimensions
    W = 1.10   # X: -0.55 .. +0.55
    D = 0.80   # Y: -0.40 .. +0.40
    H = 0.72   # Z: 0.00 .. 0.72
    skid_h = 0.065
    body_z0 = skid_h
    lid_h = 0.095
    body_z1 = H - lid_h
    body_h = body_z1 - body_z0
    body_zc = 0.5 * (body_z0 + body_z1)
    lid_zc = body_z1 + 0.5 * lid_h

    if lod == 2:
        # LOD2: clean aggressive silhouette (skids + main body + overhanging lid + 8 simplified corner caps)
        for sx in (-0.36, 0.36):
            add_box(bm, uv_layer, (sx, 0.0, skid_h * 0.5), (0.14, D - 0.04, skid_h), UV_WOOD_FRAME, bevel=0.0)
        # Main body core
        add_box(bm, uv_layer, (0.0, 0.0, body_zc), (W - 0.02, D - 0.02, body_h), UV_WOOD_STENCIL, bevel=0.008, bevel_segments=1)
        # Overhanging lid
        add_box(bm, uv_layer, (0.0, 0.0, lid_zc), (W, D, lid_h), UV_WOOD_PLANKS, bevel=0.008, bevel_segments=1)
        # Simplified steel strapping (2 bands)
        for bx in (-0.28, 0.28):
            add_box(bm, uv_layer, (bx, 0.0, 0.5 * (body_z0 + H)), (0.045, D + 0.008, H - body_z0 + 0.008), UV_STEEL, bevel=0.0)
    else:
        bev_sm = 0.005 if lod == 0 else 0.0
        bev_lg = 0.008 if lod == 0 else 0.004
        seg = 2 if lod == 0 else 1

        # 1. Bottom wooden pallet skids (3 longitudinal runners with forklift gaps)
        for sx in (-0.42, 0.0, 0.42):
            add_box(bm, uv_layer, (sx, 0.0, skid_h * 0.5), (0.12, D - 0.03, skid_h), UV_WOOD_FRAME, bevel=bev_sm, bevel_segments=1)

        # 2. Inner sealed wood core (prevents any light leak between recessed planks)
        core_w, core_d = W - 0.075, D - 0.075
        add_box(bm, uv_layer, (0.0, 0.0, body_zc), (core_w, core_d, body_h - 0.01), UV_WOOD_PLANKS, bevel=0.0)

        # 3. Recessed horizontal wooden planks on Front (-Y) and Back (+Y)
        n_planks = 5 if lod == 0 else 3
        panel_z0 = body_z0 + 0.07
        panel_z1 = body_z1 - 0.07
        plank_h = (panel_z1 - panel_z0) / n_planks - 0.004
        stencil_bounds = (-core_w * 0.44, core_w * 0.44, panel_z0, panel_z1)
        for side_y in (-1.0, 1.0):
            y_pos = side_y * (core_d * 0.5 + 0.008)
            for i in range(n_planks):
                pz = panel_z0 + (i + 0.5) * ((panel_z1 - panel_z0) / n_planks)
                # Front/back recessed planks map continuously across the cargo stencil quadrant
                add_box(
                    bm,
                    uv_layer,
                    (0.0, y_pos, pz),
                    (core_w + 0.004, 0.018, plank_h),
                    UV_WOOD_STENCIL,
                    bevel=0.002 if lod == 0 else 0.0,
                    bevel_segments=1,
                    fit_planar_axis="Y",
                    planar_bounds=stencil_bounds,
                )

        # 4. Recessed horizontal wooden planks on Left (-X) and Right (+X)
        for side_x in (-1.0, 1.0):
            x_pos = side_x * (core_w * 0.5 + 0.008)
            for i in range(n_planks):
                pz = body_z0 + 0.07 + (i + 0.5) * ((body_h - 0.14) / n_planks)
                add_box(
                    bm,
                    uv_layer,
                    (x_pos, 0.0, pz),
                    (0.018, core_d + 0.004, plank_h),
                    UV_WOOD_PLANKS,
                    bevel=0.002 if lod == 0 else 0.0,
                    bevel_segments=1,
                )

        # 5. Raised perimeter timber framing (top/bottom horizontal rails + 4 vertical corner posts)
        frame_t = 0.036
        rail_h = 0.068
        # Front/back top & bottom rails
        for side_y in (-1.0, 1.0):
            ry = side_y * (D * 0.5 - frame_t * 0.5 - 0.005)
            for rz in (body_z0 + rail_h * 0.5, body_z1 - rail_h * 0.5):
                add_box(bm, uv_layer, (0.0, ry, rz), (W - 0.02, frame_t, rail_h), UV_WOOD_FRAME, bevel=bev_sm, bevel_segments=1)
        # Left/right top & bottom rails
        for side_x in (-1.0, 1.0):
            rx = side_x * (W * 0.5 - frame_t * 0.5 - 0.005)
            for rz in (body_z0 + rail_h * 0.5, body_z1 - rail_h * 0.5):
                add_box(bm, uv_layer, (rx, 0.0, rz), (frame_t, D - 0.02, rail_h), UV_WOOD_FRAME, bevel=bev_sm, bevel_segments=1)
        # 4 vertical corner posts
        post_w = 0.072
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                px = sx * (W * 0.5 - post_w * 0.5 - 0.005)
                py = sy * (D * 0.5 - post_w * 0.5 - 0.005)
                add_box(bm, uv_layer, (px, py, body_zc), (post_w, post_w, body_h), UV_WOOD_FRAME, bevel=bev_sm, bevel_segments=1)

        # 6. Center vertical timber battens on front/back + diagonal reinforcement on sides
        if lod == 0:
            for side_x in (-1.0, 1.0):
                rx = side_x * (core_w * 0.5 + 0.022)
                diag_len = math.hypot(D - 0.22, body_h - 0.16)
                diag_ang = math.atan2(body_h - 0.16, D - 0.22)
                add_box(
                    bm,
                    uv_layer,
                    (rx, 0.0, body_zc),
                    (0.022, diag_len, 0.055),
                    UV_WOOD_FRAME,
                    bevel=0.003,
                    bevel_segments=1,
                    rot_euler=(diag_ang * side_x, 0.0, 0.0),
                )

        # 7. Heavy Overhanging Lid (perimeter skirt + recessed top planks)
        add_box(bm, uv_layer, (0.0, 0.0, lid_zc - 0.004), (W, D, lid_h - 0.008), UV_WOOD_FRAME, bevel=bev_lg, bevel_segments=seg)
        # Top surface planks
        top_planks = 4 if lod == 0 else 2
        tp_d = (D - 0.10) / top_planks - 0.004
        for i in range(top_planks):
            ty = -(D - 0.10) * 0.5 + (i + 0.5) * ((D - 0.10) / top_planks)
            add_box(bm, uv_layer, (0.0, ty, H - 0.006), (W - 0.10, tp_d, 0.012), UV_WOOD_PLANKS, bevel=0.002 if lod == 0 else 0.0, bevel_segments=1)

        # 8. Stamped Steel Corner Brackets (all 8 corners: 4 top on lid, 4 bottom on body)
        br_l = 0.135
        br_t = 0.012
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                # Top corner caps (wrapping X, Y, Z)
                cx = sx * (W * 0.5 + br_t * 0.35)
                cy = sy * (D * 0.5 + br_t * 0.35)
                cz_top = H - br_l * 0.38
                add_box(bm, uv_layer, (cx, sy * (D * 0.5 - br_l * 0.5 + 0.006), cz_top), (br_t, br_l, br_l * 0.76), UV_STEEL, bevel=bev_sm * 0.6, bevel_segments=1)
                add_box(bm, uv_layer, (sx * (W * 0.5 - br_l * 0.5 + 0.006), cy, cz_top), (br_l, br_t, br_l * 0.76), UV_STEEL, bevel=bev_sm * 0.6, bevel_segments=1)
                add_box(bm, uv_layer, (sx * (W * 0.5 - br_l * 0.5 + 0.006), sy * (D * 0.5 - br_l * 0.5 + 0.006), H + br_t * 0.25), (br_l, br_l, br_t), UV_STEEL, bevel=bev_sm * 0.6, bevel_segments=1)

                # Bottom corner brackets
                cz_bot = body_z0 + br_l * 0.42
                add_box(bm, uv_layer, (cx, sy * (D * 0.5 - br_l * 0.5 + 0.006), cz_bot), (br_t, br_l, br_l * 0.84), UV_STEEL, bevel=bev_sm * 0.6, bevel_segments=1)
                add_box(bm, uv_layer, (sx * (W * 0.5 - br_l * 0.5 + 0.006), cy, cz_bot), (br_l, br_t, br_l * 0.84), UV_STEEL, bevel=bev_sm * 0.6, bevel_segments=1)

        # 9. Steel Strapping Bands (2 vertical wrap-around bands)
        strap_w = 0.040
        strap_t = 0.008
        for bx in (-0.30, 0.30):
            # Front & back vertical straps
            for sy in (-1.0, 1.0):
                add_box(bm, uv_layer, (bx, sy * (D * 0.5 + strap_t * 0.4), body_zc), (strap_w, strap_t, body_h + 0.01), UV_STEEL, bevel=0.0)
                add_box(bm, uv_layer, (bx, sy * (D * 0.5 + strap_t * 0.5), lid_zc), (strap_w, strap_t, lid_h + 0.004), UV_STEEL, bevel=0.0)
            # Top strap
            add_box(bm, uv_layer, (bx, 0.0, H + strap_t * 0.4), (strap_w, D + strap_t * 1.5, strap_t), UV_STEEL, bevel=0.0)

        # 10. Front Industrial Draw Latches (2 toggle clasps on -Y face)
        for lx in (-0.30, 0.30):
            ly = -(D * 0.5 + 0.012)
            # Upper catch plate on lid
            add_box(bm, uv_layer, (lx, ly, lid_zc - 0.015), (0.068, 0.014, 0.048), UV_STEEL, bevel=bev_sm * 0.5, bevel_segments=1)
            # Lower lever housing on body
            add_box(bm, uv_layer, (lx, ly - 0.004, body_z1 - 0.055), (0.064, 0.020, 0.088), UV_STEEL, bevel=bev_sm * 0.5, bevel_segments=1)
            # Bail loop / toggle handle
            add_box(bm, uv_layer, (lx, ly - 0.016, body_z1 - 0.012), (0.044, 0.012, 0.070), UV_FASTENER, bevel=bev_sm * 0.4, bevel_segments=1)

        # 11. Rear Barrel Hinges (2 heavy steel hinges on +Y face)
        for hx in (-0.30, 0.30):
            hy = D * 0.5 + 0.010
            add_box(bm, uv_layer, (hx, hy, body_z1 + 0.025), (0.076, 0.012, 0.052), UV_STEEL, bevel=0.0)
            add_box(bm, uv_layer, (hx, hy, body_z1 - 0.032), (0.076, 0.012, 0.064), UV_STEEL, bevel=0.0)
            add_cylinder(bm, uv_layer, (hx, hy + 0.008, body_z1), radius=0.011, depth=0.082, segments=10 if lod == 0 else 6, region=UV_FASTENER, rot_euler=(0.0, math.pi * 0.5, 0.0))

        # 12. Side Carry Handles (Left -X and Right +X)
        for sx in (-1.0, 1.0):
            hx = sx * (W * 0.5 + 0.008)
            hz = body_zc + 0.04
            # Backplate
            add_box(bm, uv_layer, (hx, 0.0, hz), (0.012, 0.22, 0.085), UV_STEEL, bevel=bev_sm * 0.5, bevel_segments=1)
            # Pivot mounts
            for hy in (-0.075, 0.075):
                add_box(bm, uv_layer, (hx + sx * 0.014, hy, hz + 0.015), (0.024, 0.024, 0.028), UV_STEEL, bevel=0.0)
            # U-bar grip handle
            add_cylinder(bm, uv_layer, (hx + sx * 0.028, 0.0, hz - 0.030), radius=0.010, depth=0.165, segments=10 if lod == 0 else 6, region=UV_FASTENER, rot_euler=(math.pi * 0.5, 0.0, 0.0))
            for hy in (-0.075, 0.075):
                add_box(bm, uv_layer, (hx + sx * 0.024, hy, hz - 0.008), (0.014, 0.014, 0.048), UV_STEEL, bevel=0.0)

        # 13. Hex Fasteners / Bolts on corner brackets (LOD0 only for crisp close-up detail)
        if lod == 0:
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    # Front/back corner bolts
                    for bz in (body_z0 + 0.032, body_z0 + 0.082, H - 0.032, H - 0.072):
                        bx = sx * (W * 0.5 - 0.035)
                        by = sy * (D * 0.5 + 0.013)
                        add_cylinder(bm, uv_layer, (bx, by, bz), radius=0.009, depth=0.010, segments=6, region=UV_FASTENER, rot_euler=(math.pi * 0.5, 0.0, 0.0))
                    # Side corner bolts
                    for bz in (body_z0 + 0.032, body_z0 + 0.082, H - 0.032, H - 0.072):
                        bx = sx * (W * 0.5 + 0.013)
                        by = sy * (D * 0.5 - 0.035)
                        add_cylinder(bm, uv_layer, (bx, by, bz), radius=0.009, depth=0.010, segments=6, region=UV_FASTENER, rot_euler=(0.0, math.pi * 0.5, 0.0))

    # Ensure strictly outward normals on all closed shells
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    # Add UV1 (LightmapUV)
    mesh.uv_layers.new(name="LightmapUV")

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)

    # Generate non-overlapping LightmapUV via Smart UV Project
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    mesh.uv_layers.active = mesh.uv_layers["LightmapUV"]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.02, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh.uv_layers.active = mesh.uv_layers["UVMap"]
    mesh.uv_layers["UVMap"].active_render = True
    obj.select_set(False)

    # Set smooth shading on curved/beveled faces with auto-sharp via flat faces on sharp boxes
    # For crisp hard-surface shading in Blender 5.2, set flat shading on planar faces and smooth on small bevels/cylinders
    for poly in mesh.polygons:
        poly.use_smooth = False

    # Enforce bottom-center pivot (origin at 0,0,0; min Z = 0)
    min_z = min((obj.matrix_world @ v.co).z for v in mesh.vertices)
    if abs(min_z) > 1e-6:
        for v in mesh.vertices:
            v.co.z -= min_z
        mesh.update()

    return obj


def build_collision_proxy(name: str, source_obj: bpy.types.Object) -> bpy.types.Object:
    """Create a tight 12-triangle closed convex box collision proxy covering LOD0 bounds."""
    xs = [v.co.x for v in source_obj.data.vertices]
    ys = [v.co.y for v in source_obj.data.vertices]
    zs = [v.co.z for v in source_obj.data.vertices]
    cx = 0.5 * (min(xs) + max(xs))
    cy = 0.5 * (min(ys) + max(ys))
    cz = 0.5 * (min(zs) + max(zs))
    sx = max(xs) - min(xs)
    sy = max(ys) - min(ys)
    sz = max(zs) - min(zs)

    bm = bmesh.new()
    mat = Matrix.Translation((cx, cy, cz)) @ Matrix.Diagonal((sx, sy, sz, 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def create_pbr_material(name: str, tex_dir: Path) -> bpy.types.Material:
    mat = bpy.data.materials.new(name=name)
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (260, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def load_tex(fname: str, colorspace: str, loc: tuple[int, int]):
        img = bpy.data.images.load(str((tex_dir / fname).resolve()), check_existing=True)
        img.colorspace_settings.name = colorspace
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        node.location = loc
        return node

    t_base = load_tex("base_color.png", "sRGB", (-450, 320))
    t_ao = load_tex("ao.png", "Non-Color", (-450, 60))
    t_met = load_tex("metallic.png", "Non-Color", (-450, -200))
    t_rgh = load_tex("roughness.png", "Non-Color", (-450, -460))
    t_nrm = load_tex("normal.png", "Non-Color", (-450, -720))

    # Multiply AO subtly into BaseColor for Cycles review renders
    mix_ao = nt.nodes.new("ShaderNodeMix")
    mix_ao.data_type = "RGBA"
    mix_ao.blend_type = "MULTIPLY"
    mix_ao.inputs["Factor"].default_value = 0.65
    mix_ao.location = (-80, 240)
    nt.links.new(t_base.outputs["Color"], mix_ao.inputs["A"])
    nt.links.new(t_ao.outputs["Color"], mix_ao.inputs["B"])
    nt.links.new(mix_ao.outputs["Result"], bsdf.inputs["Base Color"])

    nt.links.new(t_met.outputs["Color"], bsdf.inputs["Metallic"])
    nt.links.new(t_rgh.outputs["Color"], bsdf.inputs["Roughness"])

    nrm_node = nt.nodes.new("ShaderNodeNormalMap")
    nrm_node.location = (-60, -680)
    nrm_node.inputs["Strength"].default_value = 1.0
    nt.links.new(t_nrm.outputs["Color"], nrm_node.inputs["Color"])
    nt.links.new(nrm_node.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--raw-textures", type=Path, required=True)
    p.add_argument("--out-blend", type=Path, required=True)
    args = p.parse_args(argv)

    clear_scene()
    mat = create_pbr_material("M_SupplyCrate_Body", args.raw_textures)

    root_empty = bpy.data.objects.new("SupplyCrate", None)
    root_empty.empty_display_type = "PLAIN_AXES"
    root_empty.empty_display_size = 0.25
    bpy.context.scene.collection.objects.link(root_empty)

    lod0 = build_crate_mesh("SupplyCrate_LOD0", 0, mat)
    lod1 = build_crate_mesh("SupplyCrate_LOD1", 1, mat)
    lod2 = build_crate_mesh("SupplyCrate_LOD2", 2, mat)

    # Center X/Y bounding box on (0, 0) using LOD0 extents so asymmetric front/rear hardware stays centered
    xs0 = [v.co.x for v in lod0.data.vertices]
    ys0 = [v.co.y for v in lod0.data.vertices]
    dx0 = 0.5 * (min(xs0) + max(xs0))
    dy0 = 0.5 * (min(ys0) + max(ys0))
    for obj in (lod0, lod1, lod2):
        for v in obj.data.vertices:
            v.co.x -= dx0
            v.co.y -= dy0
        obj.data.update()

    col = build_collision_proxy("SupplyCrate_COL_01", lod0)

    for obj in (lod0, lod1, lod2, col):
        obj.parent = root_empty

    # Organize into per-LOD collections for clean bundle selection
    root_col = bpy.context.scene.collection
    for obj, cname in [
        (lod0, "SupplyCrate_LOD0"),
        (lod1, "SupplyCrate_LOD1"),
        (lod2, "SupplyCrate_LOD2"),
        (col, "SupplyCrate_COL"),
    ]:
        c = bpy.data.collections.new(cname)
        root_col.children.link(c)
        c.objects.link(obj)
        root_col.objects.unlink(obj)

    args.out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out_blend.resolve()))
    print(f"Saved {args.out_blend} | LOD0={len(lod0.data.polygons)}p LOD1={len(lod1.data.polygons)}p LOD2={len(lod2.data.polygons)}p COL={len(col.data.polygons)}p")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
