"""Deterministic procedural SupplyCrate with LOD0/1/2 + collision proxy.

Run headless:  blender --factory-startup -b -P build_supplycrate.py -- --raw <raw_dir> --out <file.blend>
Authoring rules (blender-modeling): metric units, applied transforms, pivot at
bottom-centre Z=0, one material atlas, UV0 + non-overlapping UV1 (lightmap).
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
raw_dir = Path(argv[argv.index("--raw") + 1])
out_blend = Path(argv[argv.index("--out") + 1])

ASSET = "SupplyCrate"
CENTER = Vector((0.0, 0.0, 0.21))
REGION = {0: (0.25, 0.75), 1: (0.75, 0.75), 2: (0.25, 0.25)}   # wood, steel, rope atlas quadrants
UV_SCALE = 0.49                                                  # 1 m -> 0.49 UV (~1000 px/m on 2048 atlas)

LOD_SETTINGS = {
    0: dict(bevel_seg=2, bevel=0.006, rope_ring=10, rope_path=14, details=True, planks=True, handles=True),
    1: dict(bevel_seg=1, bevel=0.006, rope_ring=6, rope_path=8, details=True, planks=True, handles=True),
    2: dict(bevel_seg=0, bevel=0.0, rope_ring=0, rope_path=0, details=False, planks=False, handles=False),
}


def add_box(bm, layer, region, c, s, bevel, seg):
    before = set(bm.faces)
    res = bmesh.ops.create_cube(bm, size=1.0)
    verts = res["verts"]
    for v in verts:
        v.co = Vector((c[0] + v.co.x * s[0], c[1] + v.co.y * s[1], c[2] + v.co.z * s[2]))
    if bevel > 0 and seg > 0:
        edges = {e for v in verts for e in v.link_edges}
        bmesh.ops.bevel(bm, geom=list(edges), offset=bevel, segments=seg, profile=0.5, affect="EDGES")
    faces = [f for f in bm.faces if f not in before]
    for f in faces:
        f[layer] = region
    return faces


def add_tube(bm, layer, region, pts, radius, ring):
    """Closed capped tube along pts (list of Vectors)."""
    rings = []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        ref = Vector((1, 0, 0)) if abs(t.x) < 0.9 else Vector((0, 1, 0))
        a = t.cross(ref).normalized()
        b = t.cross(a).normalized()
        rings.append([bm.verts.new(p + (a * math.cos(2 * math.pi * k / ring) + b * math.sin(2 * math.pi * k / ring)) * radius) for k in range(ring)])
    faces = []
    for i in range(len(rings) - 1):
        for k in range(ring):
            faces.append(bm.faces.new((rings[i][k], rings[i][(k + 1) % ring], rings[i + 1][(k + 1) % ring], rings[i + 1][k])))
    faces.append(bm.faces.new(list(reversed(rings[0]))))
    faces.append(bm.faces.new(rings[-1]))
    for f in faces:
        f[layer] = region
        f.smooth = True
    return faces


def build_lod_mesh(lod):
    cfg = LOD_SETTINGS[lod]
    bm = bmesh.new()
    layer = bm.faces.layers.int.new("region")
    bv, sg = cfg["bevel"], cfg["bevel_seg"]
    L, D, H = 0.90, 0.50, 0.42
    # skids (wood)
    for y in (-0.18, 0.18):
        add_box(bm, layer, 0, (0, y, 0.02), (L, 0.06, 0.04), bv, sg)
    if cfg["planks"]:
        ph, pitch = 0.112, 0.118
        for k in range(3):
            z = 0.04 + ph / 2 + k * pitch
            for y in (-1, 1):
                add_box(bm, layer, 0, (0, y * (D / 2 - 0.015), z), (L - 0.06, 0.03, ph), bv, sg)
            for x in (-1, 1):
                add_box(bm, layer, 0, (x * (L / 2 - 0.015), 0, z), (0.03, D - 0.06, ph), bv, sg)
        for k in range(4):                                        # lid planks
            add_box(bm, layer, 0, (-0.3375 + k * 0.225, 0, 0.403), (0.218, D, 0.03), bv, sg)
    else:
        add_box(bm, layer, 0, (0, 0, 0.04 + 0.174), (L - 0.02, D - 0.02, 0.348), 0, 0)
        add_box(bm, layer, 0, (0, 0, 0.403), (L, D, 0.03), 0, 0)
    # steel: corner angles + bands + latches
    for sx in (-1, 1):
        for sy in (-1, 1):
            add_box(bm, layer, 1, (sx * (L / 2 + 0.004), sy * (D / 2 - 0.03), 0.22), (0.012, 0.06, 0.37), bv * 0.5, min(sg, 1))
            add_box(bm, layer, 1, (sx * (L / 2 - 0.03), sy * (D / 2 + 0.004), 0.22), (0.06, 0.012, 0.37), bv * 0.5, min(sg, 1))
    for x in (-0.25, 0.25):
        add_box(bm, layer, 1, (x, 0, 0.421), (0.05, D + 0.012, 0.006), 0, 0)
        for y in (-1, 1):
            add_box(bm, layer, 1, (x, y * (D / 2 + 0.003), 0.22), (0.05, 0.006, 0.37), 0, 0)
    if cfg["details"]:
        for x in (-0.2, 0.2):
            add_box(bm, layer, 1, (x, -(D / 2 + 0.012), 0.36), (0.08, 0.012, 0.055), bv * 0.5, min(sg, 1))
            add_box(bm, layer, 1, (x, -(D / 2 + 0.012), 0.41), (0.04, 0.014, 0.03), bv * 0.5, min(sg, 1))
    # rope handles on both ends (UV region 2)
    if cfg["handles"]:
        n = cfg["rope_path"]
        for sx in (-1, 1):
            pts = []
            for i in range(n + 1):
                t = i / n
                ang = math.pi * t
                y = -0.10 + 0.20 * t
                out = 0.035 * math.sin(ang)
                z = 0.30 - 0.0 * t
                pts.append(Vector((sx * (L / 2 + out), y, z)))
            add_tube(bm, layer, 2, pts, 0.011, cfg["rope_ring"])
    else:
        for sx in (-1, 1):
            add_box(bm, layer, 2, (sx * (L / 2 + 0.012), 0, 0.30), (0.024, 0.20, 0.024), 0, 0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # UV0: dominant-axis planar projection into per-material atlas quadrant
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        u0, v0 = REGION[f[layer]]
        for loop in f.loops:
            co = loop.vert.co - CENTER
            p, q = ((co.y, co.z), (co.x, co.z), (co.x, co.y))[ax]
            p = max(-0.5, min(0.5, p))
            q = max(-0.5, min(0.5, q))
            loop[uvl].uv = (u0 + p * UV_SCALE, v0 + q * UV_SCALE)
    bm.faces.layers.int.remove(layer)
    return bm


def make_material():
    mat = bpy.data.materials.new(f"{ASSET}_Body")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]

    def tex(name, noncolor):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(str(raw_dir / f"{name}.png"), check_existing=True)
        n.image.colorspace_settings.name = "Non-Color" if noncolor else "sRGB"
        return n

    base, rough, metal, ao, normal = tex("base_color", False), tex("roughness", True), tex("metallic", True), tex("ao", True), tex("normal", True)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    nt.links.new(base.outputs["Color"], mix.inputs[6])
    nt.links.new(ao.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(metal.outputs["Color"], bsdf.inputs["Metallic"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.uv_map = "UVMap"
    nt.links.new(normal.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def finish_object(name, bm, collection, material):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    for poly in mesh.polygons:
        pass
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material:
        mesh.materials.append(material)
    return obj


def add_lightmap_uv(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.data.uv_layers.new(name="LightmapUV")
    obj.data.uv_layers.active = obj.data.uv_layers["LightmapUV"]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.lightmap_pack(PREF_CONTEXT="ALL_FACES", PREF_PACK_IN_ONE=True, PREF_NEW_UVLAYER=False, PREF_BOX_DIV=24, PREF_MARGIN_DIV=0.2)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.data.uv_layers.active = obj.data.uv_layers["UVMap"]
    obj.select_set(False)


def add_review_lighting(scene):
    """Explicit prop-scale three-point rig for the reproducible showcase renders."""
    rig = [("Review_Key", (1.4, -1.6, 1.6), 40.0), ("Review_Fill", (-1.6, -0.9, 0.9), 12.0), ("Review_Rim", (0.4, 1.8, 1.3), 25.0)]
    center = Vector((0, 0, 0.25))
    for name, loc, energy in rig:
        data = bpy.data.lights.new(name, type="AREA")
        data.energy, data.shape, data.size = energy, "DISK", 1.0
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("ReviewWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.045, 0.05, 0.058, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    scene.world = world


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    mat = make_material()
    cols = {}
    for name in ("LOD0", "LOD1", "LOD2", "Collision"):
        c = bpy.data.collections.new(name)
        scene.collection.children.link(c)
        cols[name] = c
    for lod in (0, 1, 2):
        obj = finish_object(f"{ASSET}_LOD{lod}", build_lod_mesh(lod), cols[f"LOD{lod}"], mat)
        add_lightmap_uv(obj)
    # collision proxy: one convex hox hull
    bm = bmesh.new()
    res = bmesh.ops.create_cube(bm, size=1.0)
    for v in res["verts"]:
        v.co = Vector((v.co.x * 0.92, v.co.y * 0.52, 0.25 + v.co.z * 0.42))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    finish_object(f"{ASSET}_COL_01", bm, cols["Collision"], None)
    add_review_lighting(scene)
    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    for o in bpy.data.objects:
        print(o.name, len(o.data.polygons), "polys")


main()
