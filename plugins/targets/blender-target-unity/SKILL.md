---
name: blender-target-unity
description: Use this skill when preparing, packing URP/HDRP PBR maps for, validating, or exporting Blender 5.2+ assets into Unity (FBX or static GLB), or setting up Unity's 2-stage BlenderAssetPostprocessor.cs.
---

# Blender Target: Unity (`urp` default, `hdrp` supported)

Execute through `blender-core`'s single entrypoint:

```bash
python <blender-core>/scripts/run.py qa --blend in.blend --target unity --asset-class solid_prop
python <blender-core>/scripts/run.py export --blend in.blend --target unity --profile urp --out build/
```

## Unity-Specific Rules & Gotchas
1. **FBX Scaling & Axes:** `target.json` enforces `FBX_SCALE_ALL`, `Forward -Z`, `Up Y`, `use_triangles: true`, and `use_tspace: true`. Static meshes use `apply_transform_static: true`; rigged meshes leave it `false` and rely on Unity's `Bake Axis Conversion`.
2. **Animation Clips:** NLA strips are authoritative (`bake_anim_use_nla_strips: true`, `bake_anim_use_all_actions: false`) to prevent duplicate clips in Unity.
3. **URP & HDRP Channel Packing:** OpenGL `+Y` normals (16-bit PNG, no flip). URP packs Smoothness (`1 - Roughness`) into `_MetallicGlossMap` Alpha; HDRP packs `R=Metallic, G=AO, B=Detail, A=Smoothness` into `_MaskMap`.
4. **Unity 6.2+ Auto Mesh LODs:** When shipping `_LOD0`/`_LOD1` `LODGroup` hierarchies, `disable_unity_auto_mesh_lod: true` in `*.asset.manifest.json` tells `BlenderAssetPostprocessor.cs` to disable Unity 6.2+'s automatic Mesh LOD generator so the two systems do not conflict.
5. **Unity Editor Bridge:** Copy `editor/BlenderAssetPostprocessor.cs` into your Unity project's `Assets/Editor/` folder. It uses a 2-stage import (`OnPreprocessTexture`/`OnPreprocessModel` + `OnPostprocessAllAssets`) and explicitly sets URP Lit `_Metallic = 1.0f` and `_Smoothness = 1.0f` so packed alpha smoothness is never halved.
