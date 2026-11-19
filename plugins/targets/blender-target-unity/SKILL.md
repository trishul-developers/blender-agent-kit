---
name: blender-target-unity
description: Use this skill when preparing, packing standard URP/HDRP PBR maps for, validating, or exporting Blender 5.2+ assets into Unity through FBX/GLB, including hierarchy-safe static Y-up export and optional manifest-driven import settings.
---

# Blender Target: Unity

The Unity target owns engine-level behavior only. Project budgets, exact pivots/sockets, vehicle dimensions, custom packed masks, prefab logic, and simulation semantics belong in project profiles or downstream repositories.

## Static FBX contract

The target uses:

- `Forward -Z`, `Up Y`;
- `FBX_SCALE_ALL`;
- `use_space_transform = false`;
- `bake_space_transform = false` for the static prebake path;
- triangulation and tangent export;
- no embedded textures.

For static MESH/EMPTY hierarchies, `prebake_yup_hierarchy` converts the hierarchy into Unity's Y-up/+Z-forward basis before export. Ordinary nodes use a basis change; directional empties matching `Socket_*` preserve their authored +Z/+Y directions. Local transforms are rebuilt from converted world matrices so nested pivot chains remain stable.

This temporary conversion is restored after export.

Rigged/armature exports do **not** use the static hierarchy prebake.

## Standard profiles

`target.json` retains normal Unity profiles:

- `urp`
- `hdrp`

Custom project texture layouts should be added by a project profile rather than changing these defaults.

## Verification

Generic FBX round-trip checks include:

- object names;
- parent hierarchy;
- mesh/armature scale;
- child local transforms for pre-baked static hierarchies;
- triangle count;
- expected Blender root-axis wrapper for re-imported Y-up FBX;
- zero PNG/JPEG magic headers in FBX.

Unity identity-root proof itself belongs in an engine-side/downstream verifier using Unity's ModelImporter.

## Optional postprocessor

`editor/BlenderAssetPostprocessor.cs` can configure standard model/texture/material imports.

It does not construct project prefabs, project LODGroups/colliders, content registrations, ViewBinding, or custom project shaders.
