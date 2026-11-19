---
name: blender-target-unity
description: Use this skill when preparing, packing standard URP/HDRP PBR maps for, validating, or exporting Blender 5.2+ assets into Unity (FBX or static GLB), or when using the optional deterministic manifest-driven Unity import helper.
---

# Blender Target: Unity

The Unity target owns **engine-level** conventions only. Project-specific budgets, hierarchy, socket rules, or custom texture layouts should be supplied through a project profile.

```bash
python <blender-core>/scripts/run.py qa --blend in.blend --target unity --asset-class solid_prop
python <blender-core>/scripts/run.py export --blend in.blend --target unity --profile urp --out build/
```

## Implemented Unity rules

1. FBX uses `Forward -Z`, `Up Y`, `FBX_SCALE_ALL`, triangulation, and tangent export.
2. Static meshes use the configured static transform handling; rigged meshes preserve the rig transform policy.
3. NLA strips are authoritative by default and duplicate all-actions export is blocked.
4. Standard URP and HDRP packing remains in `target.json`.
5. The optional C# postprocessor deterministically binds a manifest to the exact model/texture it references before changing import settings.
6. Unity 6.2+ automatic mesh LOD generation can be disabled when an asset manifest declares authored LODs.

## Postprocessor boundary

`editor/BlenderAssetPostprocessor.cs` is a generic helper, especially useful in scratch verification projects. It configures model/texture import and standard URP/HDRP material textures.

It does **not** currently construct complete LODGroups, project-specific colliders, prefabs, content registrations, or custom project shaders. Downstream projects that own those systems should consume FBX/PNG + manifest evidence and keep their own Unity import pipeline authoritative.
