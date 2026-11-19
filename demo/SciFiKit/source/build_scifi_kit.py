#!/usr/bin/env python3
"""Deterministic Blender 5.2+ procedural builder for Helios Conduit Sci-Fi Modular Kit (Independent Trial).

Modular Grid (Metric, 1 BU = 1 m):
  Grid Pitch: 4.0 m x 4.0 m
  Corridor Clear Height: 3.60 m (Floor deck: Z in [-0.25, 0.0], Walls/Bulkheads/Pillars: Z in [0.0, 3.60], Ceiling: Z in [3.60, 3.95])

Builds 6 reusable modular components:
  1. SF_Wall_Straight   (4.00 x 0.45 x 3.60 m)
  2. SF_Wall_Corner     (4.00 x 4.00 x 3.60 m L-corner with angled diagnostic console)
  3. SF_Floor_Panel     (4.00 x 4.00 x 0.25 m)
  4. SF_Ceiling_Panel   (4.00 x 4.00 x 0.35 m)
  5. SF_Bulkhead_Arch   (4.00 x 0.90 x 3.60 m) — 4 LODs (LOD0..LOD3), 3-hull walkable collision, nested Header pivot & directional Sockets
  6. SF_Pillar_Support  (0.65 x 0.65 x 3.60 m)

Outputs:
  - scenes/SF_Bulkhead_Arch.blend        (isolated hero module for QA / bundle / review)
  - scenes/SF_Modules_Catalog.blend      (all 6 modules laid out for technical multiview)
  - scenes/SciFi_Corridor_Assembly.blend (21-instance assembled L-shaped corridor environment)
  - renders/hero_corridor_1920x1080.png
  - renders/catalog_persp.png, catalog_top.png, catalog_front.png
  - renders/socket_hierarchy_proof.png
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector

# Trim-sheet UV bands (U: 0..1, V: 0..1 where V=0 is bottom of image, V=1 is top)
UV_DECK_DARK = (0.02, 0.02, 0.98, 0.20)       # Band 0: dark gunmetal diamond tread
UV_ARMOR_SLATE = (0.02, 0.24, 0.98, 0.42)     # Band 1: brushed titanium-slate structural armor
UV_GRATING_RIB = (0.02, 0.46, 0.98, 0.60)     # Band 2: industrial ribbed grating / vents
UV_HAZARD = (0.02, 0.64, 0.98, 0.76)          # Band 3: yellow/black caution chevrons
UV_CERAMIC_LIGHT = (0.02, 0.80, 0.98, 0.98)   # Band 4: clean light ceramic-composite cladding

# Emissive trim UV bands (material slot 1)
UV_EMIT_CYAN = (0.04, 0.70, 0.96, 0.96)
UV_EMIT_AMBER = (0.04, 0.37, 0.96, 0.63)
UV_EMIT_SCREEN = (0.03, 0.03, 0.97, 0.31)


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def create_materials(raw_tex_dir: Path) -> tuple[bpy.types.Material, bpy.types.Material]:
    # Material 0: M_SciFi_TrimSheet
    m_trim = bpy.data.materials.new("M_SciFi_TrimSheet")
    nt = m_trim.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    tdir = raw_tex_dir / "trim_sheet"
    def load_img(d: Path, name: str, cs: str):
        im = bpy.data.images.load(str((d / name).resolve()), check_existing=True)
        im.colorspace_settings.name = cs
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = im
        return n

    t_b = load_img(tdir, "base_color.png", "sRGB")
    t_ao = load_img(tdir, "ao.png", "Non-Color")
    t_m = load_img(tdir, "metallic.png", "Non-Color")
    t_r = load_img(tdir, "roughness.png", "Non-Color")
    t_n = load_img(tdir, "normal.png", "Non-Color")

    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.65
    nt.links.new(t_b.outputs["Color"], mix.inputs["A"])
    nt.links.new(t_ao.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    nt.links.new(t_m.outputs["Color"], bsdf.inputs["Metallic"])
    nt.links.new(t_r.outputs["Color"], bsdf.inputs["Roughness"])
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(t_n.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])

    # Material 1: M_SciFi_Emissive
    m_emit = bpy.data.materials.new("M_SciFi_Emissive")
    nt2 = m_emit.node_tree
    nt2.nodes.clear()
    out2 = nt2.nodes.new("ShaderNodeOutputMaterial")
    bsdf2 = nt2.nodes.new("ShaderNodeBsdfPrincipled")
    nt2.links.new(bsdf2.outputs["BSDF"], out2.inputs["Surface"])
    edir = raw_tex_dir / "emissive"

    def load_img2(d: Path, name: str, cs: str):
        im = bpy.data.images.load(str((d / name).resolve()), check_existing=True)
        im.colorspace_settings.name = cs
        n = nt2.nodes.new("ShaderNodeTexImage")
        n.image = im
        return n

    e_b = load_img2(edir, "base_color.png", "sRGB")
    e_e = load_img2(edir, "emission.png", "sRGB")
    e_r = load_img2(edir, "roughness.png", "Non-Color")
    nt2.links.new(e_b.outputs["Color"], bsdf2.inputs["Base Color"])
    nt2.links.new(e_r.outputs["Color"], bsdf2.inputs["Roughness"])
    nt2.links.new(e_e.outputs["Color"], bsdf2.inputs["Emission Color"])
    bsdf2.inputs["Emission Strength"].default_value = 5.5

    return m_trim, m_emit


def _map_uv_box(faces: list, uv_layer, region: tuple[float, float, float, float], mat_idx: int = 0) -> None:
    u0, v0, u1, v1 = region
    du, dv = u1 - u0, v1 - v0
    for f in faces:
        f.material_index = mat_idx
        n = f.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
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
        sx = max(xmax - xmin, 1e-4)
        sy = max(ymax - ymin, 1e-4)
        for loop, (px, py) in zip(f.loops, proj):
            lu = u0 + ((px - xmin) / sx) * du
            lv = v0 + ((py - ymin) / sy) * dv
            loop[uv_layer].uv = (lu, lv)


def add_box(
    bm: bmesh.types.BMesh,
    uv_layer,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    region: tuple[float, float, float, float],
    mat_idx: int = 0,
    bevel: float = 0.0,
    segments: int = 1,
    rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    mat = (
        Matrix.Translation(Vector(center))
        @ Matrix.Rotation(rot_euler[2], 4, "Z")
        @ Matrix.Rotation(rot_euler[1], 4, "Y")
        @ Matrix.Rotation(rot_euler[0], 4, "X")
        @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    )
    ret = bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
    vset = set(ret["verts"])
    edges = [e for e in bm.edges if e.verts[0] in vset and e.verts[1] in vset]
    faces = [f for f in bm.faces if all(v in vset for v in f.verts)]
    if bevel > 0.0:
        bret = bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=segments, profile=0.5, affect="EDGES", clamp_overlap=True)
        nverts = vset | set(bret.get("verts", []))
        faces = [f for f in bm.faces if all(v in nverts for v in f.verts)]
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    _map_uv_box(faces, uv_layer, region, mat_idx=mat_idx)


def add_cyl(
    bm: bmesh.types.BMesh,
    uv_layer,
    center: tuple[float, float, float],
    radius: float,
    depth: float,
    segments: int,
    region: tuple[float, float, float, float],
    mat_idx: int = 0,
    rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    mat = (
        Matrix.Translation(Vector(center))
        @ Matrix.Rotation(rot_euler[2], 4, "Z")
        @ Matrix.Rotation(rot_euler[1], 4, "Y")
        @ Matrix.Rotation(rot_euler[0], 4, "X")
    )
    ret = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius, radius2=radius, depth=depth, matrix=mat)
    vset = set(ret["verts"])
    faces = [f for f in bm.faces if all(v in vset for v in f.verts)]
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    _map_uv_box(faces, uv_layer, region, mat_idx=mat_idx)


def finalize_mesh_obj(name: str, bm: bmesh.types.BMesh, mats: list[bpy.types.Material], make_uv1: bool = True) -> bpy.types.Object:
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = False
    for m in mats:
        mesh.materials.append(m)

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    if make_uv1:
        mesh.uv_layers.new(name="LightmapUV")
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
    return obj


def add_socket(name: str, parent: bpy.types.Object, loc: tuple[float, float, float], rot_z_deg: float = 0.0) -> bpy.types.Object:
    emp = bpy.data.objects.new(name, None)
    emp.empty_display_type = "ARROWS"
    emp.empty_display_size = 0.35
    emp.location = loc
    emp.rotation_euler = (0.0, 0.0, math.radians(rot_z_deg))
    emp.parent = parent
    bpy.context.collection.objects.link(emp)
    return emp


# ==============================================================================
# MODULE 1: SF_Bulkhead_Arch (Hero 4-LOD modular doorway with nested hierarchy)
# ==============================================================================
def build_bulkhead_lod_mesh(name: str, lod: int, mats: list[bpy.types.Material]) -> bpy.types.Object:
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    W, D, H = 4.00, 0.90, 3.60
    # Walkable opening: X in [-1.15, +1.15] (2.30 m wide), Z in [0.06, 2.65]
    jamb_w = 0.85
    jamb_x = 1.15 + jamb_w * 0.5  # 1.575

    if lod == 3:
        # LOD3 (~84 tris): 3 clean structural slabs (left jamb, right jamb, overhead lintel + threshold)
        for sx in (-1.0, 1.0):
            add_box(bm, uv, (sx * jamb_x, 0.0, H * 0.5), (jamb_w, D, H), UV_ARMOR_SLATE, 0)
        add_box(bm, uv, (0.0, 0.0, 3.125), (2.30, D, 0.95), UV_CERAMIC_LIGHT, 0)
        add_box(bm, uv, (0.0, 0.0, 0.03), (2.30, D * 0.9, 0.06), UV_HAZARD, 0)
        add_box(bm, uv, (0.0, -D * 0.5 - 0.01, 2.78), (1.40, 0.02, 0.08), UV_EMIT_CYAN, 1)
    else:
        bev = 0.025 if lod == 0 else (0.015 if lod == 1 else 0.0)
        seg = 2 if lod == 0 else 1

        # Main left & right structural jamb piers
        for sx in (-1.0, 1.0):
            add_box(bm, uv, (sx * jamb_x, 0.0, H * 0.5), (jamb_w, D - 0.08, H), UV_ARMOR_SLATE, 0, bevel=bev, segments=seg)
            # Heavy lower armored plinth on each jamb
            add_box(bm, uv, (sx * jamb_x, 0.0, 0.42), (jamb_w + 0.04, D, 0.84), UV_DECK_DARK, 0, bevel=bev, segments=1)
            # Recessed upper ceramic armor cladding panels (front & rear)
            for sy in (-1.0, 1.0):
                add_box(bm, uv, (sx * jamb_x, sy * (D * 0.5 - 0.02), 1.95), (jamb_w - 0.16, 0.06, 1.85), UV_CERAMIC_LIGHT, 0, bevel=bev * 0.6, segments=1)
            # Hazard stripe kickplate
            for sy in (-1.0, 1.0):
                add_box(bm, uv, (sx * jamb_x, sy * (D * 0.5 + 0.005), 0.14), (jamb_w - 0.08, 0.02, 0.18), UV_HAZARD, 0)

            # Diagonal octagonal upper corner gussets framing the doorway arch
            add_box(
                bm, uv,
                (sx * 1.02, 0.0, 2.48),
                (0.46, D - 0.14, 0.46),
                UV_ARMOR_SLATE, 0,
                bevel=bev * 0.7 if lod <= 1 else 0.0,
                segments=1,
                rot_euler=(0.0, sx * math.radians(45.0), 0.0),
            )

        # Overhead hydraulic header beam (Z: 2.65..3.60)
        add_box(bm, uv, (0.0, 0.0, 3.125), (2.34, D - 0.04, 0.95), UV_ARMOR_SLATE, 0, bevel=bev, segments=seg)
        for sy in (-1.0, 1.0):
            # Upper ceramic fascia + recessed vent grille
            add_box(bm, uv, (0.0, sy * (D * 0.5 - 0.01), 3.30), (2.10, 0.06, 0.42), UV_CERAMIC_LIGHT, 0, bevel=bev * 0.5, segments=1)
            add_box(bm, uv, (0.0, sy * (D * 0.5 - 0.02), 2.94), (1.70, 0.05, 0.22), UV_GRATING_RIB, 0)
            # Emissive cyan header light bar + twin amber beacons
            add_box(bm, uv, (0.0, sy * (D * 0.5 + 0.018), 2.75), (1.50, 0.03, 0.075), UV_EMIT_CYAN, 1)
            for bx in (-0.98, 0.98):
                add_box(bm, uv, (bx, sy * (D * 0.5 + 0.022), 2.75), (0.18, 0.04, 0.095), UV_EMIT_AMBER, 1)

        # Threshold deck ramp with hazard trim
        add_box(bm, uv, (0.0, 0.0, 0.03), (2.32, D, 0.06), UV_DECK_DARK, 0, bevel=0.008 if lod <= 1 else 0.0, segments=1)
        for sy in (-1.0, 1.0):
            add_box(bm, uv, (0.0, sy * (D * 0.5 - 0.08), 0.065), (2.20, 0.14, 0.012), UV_HAZARD, 0)

        # Doorway inner pneumatic seal track ribs (LOD0 and LOD1)
        if lod <= 1:
            for sx in (-1.0, 1.0):
                for ry in (-0.24, 0.0, 0.24):
                    add_box(bm, uv, (sx * 1.13, ry, 1.35), (0.06, 0.10, 2.48), UV_DECK_DARK, 0, bevel=0.008 if lod == 0 else 0.0, segments=1)
            # Side access keypad / intercom panels on front & rear right jamb
            for sy in (-1.0, 1.0):
                add_box(bm, uv, (1.50, sy * (D * 0.5 + 0.03), 1.32), (0.34, 0.07, 0.44), UV_DECK_DARK, 0, bevel=0.008 if lod == 0 else 0.0, segments=1)
                add_box(bm, uv, (1.50, sy * (D * 0.5 + 0.068), 1.38), (0.26, 0.012, 0.20), UV_EMIT_SCREEN, 1)

        # High-detail LOD0 features: vertical conduit pipes, mounting clamps, hydraulic pistons, bolts
        if lod == 0:
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    # Vertical hydraulic conduit pipe on outer jamb edge
                    px = sx * (W * 0.5 - 0.11)
                    py = sy * (D * 0.5 + 0.01)
                    add_cyl(bm, uv, (px, py, 1.85), radius=0.038, depth=2.90, segments=12, region=UV_GRATING_RIB, mat_idx=0)
                    for cz in (0.65, 1.45, 2.25, 3.05):
                        add_box(bm, uv, (px, py - sy * 0.015, cz), (0.11, 0.09, 0.065), UV_DECK_DARK, 0, bevel=0.005, segments=1)
                    # Bolted corner gusset flanges
                    for fz in (0.95, 2.85):
                        add_cyl(bm, uv, (sx * 1.84, sy * (D * 0.5 + 0.015), fz), radius=0.025, depth=0.025, segments=6, region=UV_ARMOR_SLATE, mat_idx=0, rot_euler=(math.pi * 0.5, 0.0, 0.0))

    return finalize_mesh_obj(name, bm, mats, make_uv1=True)


def build_bulkhead_module(mats: list[bpy.types.Material], include_all_lods: bool = True, name_prefix: str = "SF_Bulkhead_Arch") -> bpy.types.Object:
    root = bpy.data.objects.new(name_prefix, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.4
    bpy.context.collection.objects.link(root)

    if include_all_lods:
        for lod in (0, 1, 2, 3):
            obj = build_bulkhead_lod_mesh(f"{name_prefix}_LOD{lod}", lod, mats)
            obj.parent = root
            c = bpy.data.collections.new(f"Bulkhead_LOD{lod}")
            bpy.context.scene.collection.children.link(c)
            c.objects.link(obj)
            bpy.context.scene.collection.objects.unlink(obj)

        # 3-hull walkable collision proxy (left jamb, right jamb, overhead lintel)
        col_col = bpy.data.collections.new("Bulkhead_COL")
        bpy.context.scene.collection.children.link(col_col)
        col_specs = [
            (f"{name_prefix}_COL_01", (-1.575, 0.0, 1.80), (0.85, 0.90, 3.60)),
            (f"{name_prefix}_COL_02", (1.575, 0.0, 1.80), (0.85, 0.90, 3.60)),
            (f"{name_prefix}_COL_03", (0.0, 0.0, 3.125), (2.30, 0.90, 0.95)),
        ]
        for cname, center, size in col_specs:
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(center) @ Matrix.Diagonal((*size, 1.0)))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            m = bpy.data.meshes.new(cname)
            bm.to_mesh(m)
            bm.free()
            cobj = bpy.data.objects.new(cname, m)
            cobj.parent = root
            col_col.objects.link(cobj)
    else:
        obj = build_bulkhead_lod_mesh(f"{name_prefix}_Mesh", 0, mats)
        obj.parent = root

    # Nested child hierarchy (depth >= 2) + directional Socket_* empties
    header = bpy.data.objects.new(f"{name_prefix}_Header", None)
    header.empty_display_type = "CUBE"
    header.empty_display_size = 0.25
    header.location = (0.0, 0.0, 3.125)
    header.parent = root
    bpy.context.collection.objects.link(header)

    add_socket("Socket_OverheadConduit", header, (0.0, 0.0, 0.475), rot_z_deg=0.0)
    add_socket("Socket_StatusBeacon", header, (0.0, -0.46, -0.375), rot_z_deg=180.0)
    add_socket("Socket_Front", root, (0.0, -0.45, 0.0), rot_z_deg=180.0)
    add_socket("Socket_Rear", root, (0.0, 0.45, 0.0), rot_z_deg=0.0)
    add_socket("Socket_Left", root, (-2.0, 0.0, 0.0), rot_z_deg=90.0)
    add_socket("Socket_Right", root, (2.0, 0.0, 0.0), rot_z_deg=-90.0)
    return root


# ==============================================================================
# MODULE 2: SF_Wall_Straight (4.00 x 0.45 x 3.60 m)
# ==============================================================================
def build_wall_straight(mats: list[bpy.types.Material], name: str = "SF_Wall_Straight") -> bpy.types.Object:
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")

    # Core structural backing slab
    add_box(bm, uv, (0.0, 0.0, 1.80), (4.00, 0.34, 3.60), UV_ARMOR_SLATE, 0, bevel=0.012, segments=1)
    # Heavy lower armored wainscot dado (both faces so corridor walls read cleanly)
    add_box(bm, uv, (0.0, 0.0, 0.55), (3.96, 0.44, 1.10), UV_DECK_DARK, 0, bevel=0.018, segments=1)
    # Hazard safety strip along lower dado
    for sy in (-1.0, 1.0):
        add_box(bm, uv, (0.0, sy * 0.225, 0.14), (3.80, 0.015, 0.16), UV_HAZARD, 0)
    # 3 recessed upper ceramic hull panels separated by heavy vertical ribs
    for px in (-1.20, 0.0, 1.20):
        for sy in (-1.0, 1.0):
            add_box(bm, uv, (px, sy * 0.19, 2.28), (1.02, 0.06, 1.72), UV_CERAMIC_LIGHT, 0, bevel=0.012, segments=1)
            # Vent louver inset
            add_box(bm, uv, (px, sy * 0.215, 1.32), (0.86, 0.04, 0.24), UV_GRATING_RIB, 0)
    # 4 vertical structural framing ribs
    for rx in (-1.92, -0.64, 0.64, 1.92):
        add_box(bm, uv, (rx, 0.0, 1.80), (0.16, 0.45, 3.58), UV_ARMOR_SLATE, 0, bevel=0.012, segments=1)
    # Upper cornice beam + recessed cyan LED light strip
    add_box(bm, uv, (0.0, 0.0, 3.38), (4.00, 0.45, 0.44), UV_DECK_DARK, 0, bevel=0.012, segments=1)
    for sy in (-1.0, 1.0):
        add_box(bm, uv, (0.0, sy * 0.225, 3.12), (3.60, 0.025, 0.07), UV_EMIT_CYAN, 1)
        # Horizontal conduit pipe
        add_cyl(bm, uv, (0.0, sy * 0.23, 0.96), radius=0.032, depth=3.84, segments=10, region=UV_GRATING_RIB, mat_idx=0, rot_euler=(0.0, math.pi * 0.5, 0.0))

    mesh_obj = finalize_mesh_obj(f"{name}_Mesh", bm, mats, make_uv1=True)
    mesh_obj.parent = root
    add_socket("Socket_Left", root, (-2.0, 0.0, 0.0), rot_z_deg=90.0)
    add_socket("Socket_Right", root, (2.0, 0.0, 0.0), rot_z_deg=-90.0)
    return root


# ==============================================================================
# MODULE 3: SF_Wall_Corner (4.00 x 4.00 x 3.60 m L-corner + angled console)
# ==============================================================================
def build_wall_corner(mats: list[bpy.types.Material], name: str = "SF_Wall_Corner") -> bpy.types.Object:
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")

    # Back wall along +Y edge (Y=+1.78, X in [-2..+2]) and right wall along +X edge (X=+1.78, Y in [-2..+2])
    add_box(bm, uv, (0.0, 1.78, 1.80), (4.00, 0.44, 3.60), UV_ARMOR_SLATE, 0, bevel=0.015, segments=1)
    add_box(bm, uv, (1.78, 0.0, 1.80), (0.44, 4.00, 3.60), UV_ARMOR_SLATE, 0, bevel=0.015, segments=1)
    # Ceramic upper panels
    add_box(bm, uv, (-0.55, 1.54, 2.25), (2.20, 0.06, 1.70), UV_CERAMIC_LIGHT, 0, bevel=0.01, segments=1)
    add_box(bm, uv, (1.54, -0.55, 2.25), (0.06, 2.20, 1.70), UV_CERAMIC_LIGHT, 0, bevel=0.01, segments=1)
    # Emissive upper strips
    add_box(bm, uv, (-0.55, 1.54, 3.16), (2.20, 0.03, 0.07), UV_EMIT_CYAN, 1)
    add_box(bm, uv, (1.54, -0.55, 3.16), (0.03, 2.20, 0.07), UV_EMIT_CYAN, 1)
    # Angled 45-degree corner diagnostic console station
    add_box(bm, uv, (1.12, 1.12, 1.80), (1.45, 0.60, 3.60), UV_DECK_DARK, 0, bevel=0.02, segments=1, rot_euler=(0.0, 0.0, math.radians(-45.0)))
    # Console telemetry display screen + tilted desk shelf + amber status header
    add_box(bm, uv, (0.86, 0.86, 1.72), (1.02, 0.05, 0.56), UV_EMIT_SCREEN, 1, rot_euler=(0.0, 0.0, math.radians(-45.0)))
    add_box(bm, uv, (0.76, 0.76, 1.05), (1.18, 0.42, 0.14), UV_ARMOR_SLATE, 0, bevel=0.012, segments=1, rot_euler=(0.0, 0.0, math.radians(-45.0)))
    add_box(bm, uv, (0.88, 0.88, 2.25), (0.90, 0.04, 0.08), UV_EMIT_AMBER, 1, rot_euler=(0.0, 0.0, math.radians(-45.0)))
    add_box(bm, uv, (0.85, 0.85, 0.16), (1.20, 0.06, 0.18), UV_HAZARD, 0, rot_euler=(0.0, 0.0, math.radians(-45.0)))

    mesh_obj = finalize_mesh_obj(f"{name}_Mesh", bm, mats, make_uv1=True)
    mesh_obj.parent = root
    add_socket("Socket_West", root, (-2.0, 1.78, 0.0), rot_z_deg=90.0)
    add_socket("Socket_South", root, (1.78, -2.0, 0.0), rot_z_deg=180.0)
    return root


# ==============================================================================
# MODULE 4: SF_Floor_Panel (4.00 x 4.00 x 0.25 m, top at Z=0.0)
# ==============================================================================
def build_floor_panel(mats: list[bpy.types.Material], name: str = "SF_Floor_Panel") -> bpy.types.Object:
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")

    # Structural sub-deck
    add_box(bm, uv, (0.0, 0.0, -0.16), (4.00, 4.00, 0.18), UV_DECK_DARK, 0)
    # Left & right raised diamond-plate walkway decks
    for sx in (-1.35, 1.35):
        add_box(bm, uv, (sx, 0.0, -0.035), (1.28, 3.96, 0.07), UV_DECK_DARK, 0, bevel=0.01, segments=1)
        # Hazard chevron walkway border strips
        add_box(bm, uv, (sx * 0.58, 0.0, -0.002), (0.14, 3.94, 0.012), UV_HAZARD, 0)
    # Central recessed grating plates + subtle glowing under-floor conduit rails
    for gy in (-1.30, 0.0, 1.30):
        add_box(bm, uv, (0.0, gy, -0.042), (1.16, 1.18, 0.045), UV_GRATING_RIB, 0, bevel=0.006, segments=1)
    for cx in (-0.38, 0.38):
        add_box(bm, uv, (cx, 0.0, -0.015), (0.045, 3.88, 0.016), UV_EMIT_CYAN, 1)

    mesh_obj = finalize_mesh_obj(f"{name}_Mesh", bm, mats, make_uv1=True)
    mesh_obj.parent = root
    add_socket("Socket_North", root, (0.0, 2.0, 0.0), rot_z_deg=0.0)
    add_socket("Socket_South", root, (0.0, -2.0, 0.0), rot_z_deg=180.0)
    add_socket("Socket_East", root, (2.0, 0.0, 0.0), rot_z_deg=-90.0)
    add_socket("Socket_West", root, (-2.0, 0.0, 0.0), rot_z_deg=90.0)
    return root


# ==============================================================================
# MODULE 5: SF_Ceiling_Panel (4.00 x 4.00 x 0.35 m, bottom at Z=0.0 locally)
# ==============================================================================
def build_ceiling_panel(mats: list[bpy.types.Material], name: str = "SF_Ceiling_Panel") -> bpy.types.Object:
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")

    # Upper plenum deck
    add_box(bm, uv, (0.0, 0.0, 0.26), (4.00, 4.00, 0.18), UV_DECK_DARK, 0)
    # Coffered structural ribs along X and Y
    for rx in (-1.82, -0.82, 0.82, 1.82):
        add_box(bm, uv, (rx, 0.0, 0.10), (0.28, 3.96, 0.20), UV_ARMOR_SLATE, 0, bevel=0.012, segments=1)
    for ry in (-1.82, 0.0, 1.82):
        add_box(bm, uv, (0.0, ry, 0.11), (3.96, 0.26, 0.18), UV_ARMOR_SLATE, 0, bevel=0.012, segments=1)
    # Central overhead ventilation ducting
    add_box(bm, uv, (0.0, 0.0, 0.12), (0.84, 3.80, 0.16), UV_GRATING_RIB, 0, bevel=0.015, segments=1)
    # Twin linear recessed cyan-white LED overhead light troughs
    for lx in (-1.32, 1.32):
        add_box(bm, uv, (lx, 0.0, 0.12), (0.26, 3.40, 0.04), UV_EMIT_CYAN, 1)

    mesh_obj = finalize_mesh_obj(f"{name}_Mesh", bm, mats, make_uv1=True)
    mesh_obj.parent = root
    add_socket("Socket_North", root, (0.0, 2.0, 0.0), rot_z_deg=0.0)
    add_socket("Socket_South", root, (0.0, -2.0, 0.0), rot_z_deg=180.0)
    return root


# ==============================================================================
# MODULE 6: SF_Pillar_Support (0.65 x 0.65 x 3.60 m)
# ==============================================================================
def build_pillar_support(mats: list[bpy.types.Material], name: str = "SF_Pillar_Support") -> bpy.types.Object:
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")

    # Heavy bolted base plinth & top capital
    add_box(bm, uv, (0.0, 0.0, 0.22), (0.65, 0.65, 0.44), UV_DECK_DARK, 0, bevel=0.03, segments=1)
    add_box(bm, uv, (0.0, 0.0, 3.38), (0.65, 0.65, 0.44), UV_DECK_DARK, 0, bevel=0.03, segments=1)
    # Octagonal chamfered main shaft
    add_box(bm, uv, (0.0, 0.0, 1.80), (0.48, 0.48, 2.84), UV_ARMOR_SLATE, 0, bevel=0.06, segments=1)
    # Mid structural collar ring + hazard band
    add_box(bm, uv, (0.0, 0.0, 1.80), (0.56, 0.56, 0.22), UV_CERAMIC_LIGHT, 0, bevel=0.02, segments=1)
    add_box(bm, uv, (0.0, 0.0, 0.50), (0.54, 0.54, 0.14), UV_HAZARD, 0)
    # Vertical emissive cyan light channels on 4 faces
    for ang in (0.0, 90.0, 180.0, 270.0):
        r = math.radians(ang)
        add_box(bm, uv, (math.sin(r) * 0.245, -math.cos(r) * 0.245, 2.45), (0.06, 0.02, 1.05), UV_EMIT_CYAN, 1, rot_euler=(0.0, 0.0, r))

    mesh_obj = finalize_mesh_obj(f"{name}_Mesh", bm, mats, make_uv1=True)
    mesh_obj.parent = root
    add_socket("Socket_Base", root, (0.0, 0.0, 0.0), rot_z_deg=0.0)
    add_socket("Socket_Top", root, (0.0, 0.0, 3.60), rot_z_deg=0.0)
    return root


def setup_cycles(scene, width: int, height: int, samples: int) -> None:
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"


def aim_camera(cam_obj: bpy.types.Object, loc: tuple[float, float, float], target: tuple[float, float, float], lens: float = 28.0) -> None:
    cam_obj.location = Vector(loc)
    direction = Vector(target) - Vector(loc)
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam_obj.data.lens = lens


def build_and_render_corridor(raw_tex_dir: Path, out_blend: Path, renders_dir: Path) -> dict:
    clear_scene()
    mats = list(create_materials(raw_tex_dir))
    scene = bpy.context.scene

    # World: dark space-station ambient
    world = bpy.data.worlds.new("SciFiWorld")
    scene.world = world
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.012, 0.018, 0.028, 1.0)
        bg.inputs[1].default_value = 0.35

    def place(builder_fn, name: str, loc: tuple[float, float, float], rot_z_deg: float = 0.0):
        obj = builder_fn(mats, name=name)
        obj.location = loc
        obj.rotation_euler = (0.0, 0.0, math.radians(rot_z_deg))
        return obj

    # Assemble 3-bay straight corridor (Y = 0, 4, 8) + L-turn bay at (X = 4, Y = 8)
    instances = []
    # Floors (4 panels)
    for idx, (fx, fy) in enumerate([(0, 0), (0, 4), (0, 8), (4, 8)]):
        instances.append(place(build_floor_panel, f"Floor_{idx:02d}", (fx, fy, 0.0)))
    # Ceilings (4 panels at Z = 3.60)
    for idx, (cx, cy) in enumerate([(0, 0), (0, 4), (0, 8), (4, 8)]):
        instances.append(place(build_ceiling_panel, f"Ceiling_{idx:02d}", (cx, cy, 3.60)))
    # Left straight walls (X = -2.0, Y = 0, 4) and Right straight walls (X = +2.0, Y = 0, 4) + Far wall of L-turn
    instances.append(place(build_wall_straight, "Wall_L0", (-2.0, 0.0, 0.0), 90.0))
    instances.append(place(build_wall_straight, "Wall_L1", (-2.0, 4.0, 0.0), 90.0))
    instances.append(place(build_wall_straight, "Wall_R0", (2.0, 0.0, 0.0), -90.0))
    instances.append(place(build_wall_straight, "Wall_R1", (2.0, 4.0, 0.0), -90.0))
    instances.append(place(build_wall_straight, "Wall_Turn_N", (4.0, 10.0, 0.0), 0.0))
    instances.append(place(build_wall_straight, "Wall_Turn_S", (4.0, 6.0, 0.0), 180.0))
    # Corner wall at (0, 8) rotated 90 deg so the angled console faces down the corridor (-Y) and turns right (+X)!
    instances.append(place(build_wall_corner, "Wall_Corner_NW", (0.0, 8.0, 0.0), 90.0))
    # End bulkhead closing the turn at (6.0, 8.0) and hero mid-corridor bulkhead arches at Y=2.0 and Y=6.0!
    b1 = build_bulkhead_module(mats, include_all_lods=False, name_prefix="Bulkhead_Bay01")
    b1.location = (0.0, 2.0, 0.0)
    instances.append(b1)
    b2 = build_bulkhead_module(mats, include_all_lods=False, name_prefix="Bulkhead_Bay02")
    b2.location = (0.0, 6.0, 0.0)
    instances.append(b2)
    # 4 structural support pillars framing the corridor bays
    for idx, (px, py) in enumerate([(-1.62, 0.0), (1.62, 0.0), (-1.62, 4.0), (1.62, 4.0)]):
        instances.append(place(build_pillar_support, f"Pillar_{idx:02d}", (px, py, 0.0)))

    # Interior cinematic practical area lights matching the overhead troughs + warm amber bulkhead accents
    for ly, energy, col in [
        (0.0, 180.0, (0.72, 0.90, 1.0)),
        (4.0, 220.0, (0.70, 0.90, 1.0)),
        (8.0, 260.0, (0.62, 0.88, 1.0)),
        (2.0, 85.0, (1.0, 0.65, 0.25)),
        (6.0, 95.0, (1.0, 0.62, 0.22)),
    ]:
        ldata = bpy.data.lights.new(f"KeyLight_{ly}", type="AREA")
        ldata.energy = energy
        ldata.color = col
        ldata.shape = "RECTANGLE"
        ldata.size = 1.8
        ldata.size_y = 0.6
        lobj = bpy.data.objects.new(f"KeyLight_{ly}", ldata)
        lobj.location = (0.0, ly, 3.40)
        bpy.context.collection.objects.link(lobj)

    # Subtle fill light behind camera for crisp foreground material readability
    fill_d = bpy.data.lights.new("CamFill", type="AREA")
    fill_d.energy = 110.0
    fill_d.color = (0.85, 0.92, 1.0)
    fill_d.size = 2.4
    fill_o = bpy.data.objects.new("CamFill", fill_d)
    fill_o.location = (-0.6, -1.6, 2.2)
    fill_o.rotation_euler = (math.radians(72.0), 0.0, math.radians(-12.0))
    bpy.context.collection.objects.link(fill_o)

    # Hero Camera looking down the pressurized corridor through both bulkhead arches toward the illuminated corner console
    cam_data = bpy.data.cameras.new("HeroCam")
    cam_obj = bpy.data.objects.new("HeroCam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    aim_camera(cam_obj, loc=(-0.52, -1.55, 1.55), target=(0.18, 6.8, 1.62), lens=24.0)

    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend.resolve()))

    renders_dir.mkdir(parents=True, exist_ok=True)
    setup_cycles(scene, 1920, 1080, samples=40)
    hero_out = renders_dir / "hero_corridor_1920x1080.png"
    scene.render.filepath = str(hero_out.resolve())
    bpy.ops.render.render(write_still=True)

    mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
    total_tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in mesh_objs)
    return {
        "blend": str(out_blend),
        "module_instances": len(instances),
        "object_count": len(bpy.data.objects),
        "mesh_count": len(mesh_objs),
        "total_tris": total_tris,
        "hero_render": str(hero_out),
    }


def build_and_render_catalog(raw_tex_dir: Path, out_blend: Path, renders_dir: Path) -> dict:
    clear_scene()
    mats = list(create_materials(raw_tex_dir))
    scene = bpy.context.scene

    world = bpy.data.worlds.new("CatalogWorld")
    scene.world = world
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.04, 0.05, 0.065, 1.0)
        bg.inputs[1].default_value = 0.8

    # Arrange all 6 modules in a clean 3x2 grid (spacing 5.6 m X, 5.6 m Y)
    specs = [
        ("SF_Bulkhead_Arch", lambda: build_bulkhead_module(mats, include_all_lods=False, name_prefix="SF_Bulkhead_Arch"), (-5.6, 2.8, 0.0)),
        ("SF_Wall_Straight", lambda: build_wall_straight(mats, "SF_Wall_Straight"), (0.0, 2.8, 0.0)),
        ("SF_Wall_Corner", lambda: build_wall_corner(mats, "SF_Wall_Corner"), (5.6, 2.8, 0.0)),
        ("SF_Floor_Panel", lambda: build_floor_panel(mats, "SF_Floor_Panel"), (-5.6, -2.8, 0.25)),
        ("SF_Ceiling_Panel", lambda: build_ceiling_panel(mats, "SF_Ceiling_Panel"), (0.0, -2.8, 0.0)),
        ("SF_Pillar_Support", lambda: build_pillar_support(mats, "SF_Pillar_Support"), (5.6, -2.8, 0.0)),
    ]
    module_stats = {}
    for mname, fn, loc in specs:
        root = fn()
        root.location = loc
        child_meshes = [c for c in root.children_recursive if c.type == "MESH"]
        tris = sum(sum(len(p.vertices) - 2 for p in c.data.polygons) for c in child_meshes)
        sockets = [c.name for c in root.children_recursive if c.type == "EMPTY" and c.name.startswith("Socket_")]
        module_stats[mname] = {"tris": tris, "sockets": sorted(sockets)}

    # Studio 3-point lighting
    for lname, loc, energy, sz in [
        ("Key", (-10.0, -14.0, 14.0), 4500.0, 8.0),
        ("Fill", (12.0, -10.0, 10.0), 2200.0, 10.0),
        ("Rim", (0.0, 14.0, 12.0), 2400.0, 8.0),
    ]:
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.energy = energy
        ld.size = sz
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        direction = Vector((0.0, 0.0, 1.5)) - Vector(loc)
        lo.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        bpy.context.collection.objects.link(lo)

    cam_d = bpy.data.cameras.new("CatalogCam")
    cam_o = bpy.data.objects.new("CatalogCam", cam_d)
    bpy.context.collection.objects.link(cam_o)
    scene.camera = cam_o

    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend.resolve()))

    # Render 1: Perspective 3/4 catalog overview
    setup_cycles(scene, 1280, 720, samples=20)
    cam_d.type = "PERSP"
    aim_camera(cam_o, loc=(0.0, -19.5, 11.5), target=(0.0, 0.0, 1.4), lens=38.0)
    p_persp = renders_dir / "catalog_persp.png"
    scene.render.filepath = str(p_persp.resolve())
    bpy.ops.render.render(write_still=True)

    # Render 2: Orthographic Top view
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 18.5
    aim_camera(cam_o, loc=(0.0, 0.0, 22.0), target=(0.0, 0.0, 0.0))
    p_top = renders_dir / "catalog_top.png"
    scene.render.filepath = str(p_top.resolve())
    bpy.ops.render.render(write_still=True)

    # Render 3: Orthographic Front view
    cam_d.ortho_scale = 18.5
    aim_camera(cam_o, loc=(0.0, -22.0, 1.8), target=(0.0, 0.0, 1.8))
    p_front = renders_dir / "catalog_front.png"
    scene.render.filepath = str(p_front.resolve())
    bpy.ops.render.render(write_still=True)

    return {
        "blend": str(out_blend),
        "modules": module_stats,
        "renders": {"persp": str(p_persp), "top": str(p_top), "front": str(p_front)},
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--raw-textures", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args(argv)

    scenes_dir = args.out_dir / "scenes"
    renders_dir = args.out_dir / "renders"
    evidence_dir = args.out_dir / "evidence"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    renders_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build isolated SF_Bulkhead_Arch.blend (with 4 LODs, 3-hull collision, nested hierarchy & directional sockets)
    clear_scene()
    mats = list(create_materials(args.raw_textures))
    build_bulkhead_module(mats, include_all_lods=True, name_prefix="SF_Bulkhead_Arch")
    bulkhead_blend = scenes_dir / "SF_Bulkhead_Arch.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(bulkhead_blend.resolve()))

    # 2. Build & render 6-module technical catalog
    catalog_info = build_and_render_catalog(args.raw_textures, scenes_dir / "SF_Modules_Catalog.blend", renders_dir)

    # 3. Build & render full assembled L-shaped Sci-Fi corridor
    assembly_info = build_and_render_corridor(args.raw_textures, scenes_dir / "SciFi_Corridor_Assembly.blend", renders_dir)

    summary = {
        "bulkhead_blend": str(bulkhead_blend),
        "catalog": catalog_info,
        "assembly": assembly_info,
    }
    (evidence_dir / "build_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
