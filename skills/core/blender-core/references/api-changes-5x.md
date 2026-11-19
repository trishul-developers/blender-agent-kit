# Blender 5.2 LTS / 5.3 `bpy` API Migration Cheat Sheet

Use these verified 5.x rules whenever authoring Blender Python scripts so you do not emit broken 3.x/4.x code:

1. **Render Engine Enum:** Use `scene.render.engine = 'BLENDER_EEVEE'` or `'CYCLES'` (legacy `'BLENDER_EEVEE_NEXT'` / `'BLENDER_EEVEE'` aliases differ from 4.2). For headless Linux CI without EGL, always prefer `'CYCLES'` on CPU.
2. **Slotted Actions & Channelbags:** Blender 5.x uses layered/slotted Actions (`action.slots`, `action.layers`, `strip.channelbag(slot)`). Do not assume `action.fcurves` exists directly on newly created slotted actions without accessing the slot's channelbag.
3. **Compositor Node Tree:** Access compositing nodes via `scene.compositing_node_group` rather than legacy `scene.node_tree` / `use_nodes` assumptions in 5.2+.
4. **Geometry Nodes Modifier Inputs:** In Blender 5.2+, inspect/assign Geometry Nodes modifier properties cleanly through the node group interface (`mod.node_group.interface.items_tree`) and `mod[socket.identifier]` (or `mod.properties.inputs` where exposed) instead of legacy `inputs` indices.
5. **Removed Legacy APIs:** `bgl` is removed (use `gpu` module only when a GL context exists). Do not use legacy `bpy.props` dictionary-style attribute indexing where removed.
6. **FBX & glTF Add-ons:** Never assume legacy `io_scene_fbx` needs manual enabling on 5.x; verify available add-ons dynamically via `tools/doctor.py`. Always pass `--factory-startup` **before** `--addons`.
7. **Image Saving:** Never use `image.save_render()` for data maps (Normal, Metallic, Roughness, AO) because it applies the active View Transform (AgX/Filmic). Use `shared/channel_pack.py`'s pure-stdlib PNG writer for exact 8/16-bit unpremultiplied output.
