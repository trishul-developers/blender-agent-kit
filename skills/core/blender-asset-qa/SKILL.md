---
name: blender-asset-qa
description: Use this skill to audit Blender meshes, UVs, normals, transforms, LODs, and material slots against asset-class QA profiles (solid_prop, open_sheet, skinned_character) and render Cycles review sheets.
---

# Blender Asset QA

Run automated QA before every export:

```bash
python <blender-core>/scripts/run.py qa --blend in.blend --target unity --asset-class solid_prop
python <blender-core>/scripts/run.py review --blend in.blend --device auto --out review/
```

## Asset-Class Profiles
- `solid_prop`: Rejects boundary edges, requires non-overlapping UV1, enforces `bottom_center_z0` pivot and prop triangle/material budgets.
- `open_sheet`: Allows open boundary edges (foliage cards, hair planes, cloth hems, decals) while still rejecting >2-face non-manifold edges and negative scale.
- `skinned_character`: Enforces `max_bone_weights_per_vertex` and character LOD budgets while allowing open garment hems.
