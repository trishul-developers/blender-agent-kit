---
name: blender-target-unity
description: Use this skill when preparing, packing standard URP/HDRP PBR maps for, validating, or exporting Blender 5.2+ assets into Unity through FBX/GLB, including hierarchy-safe static Y-up export and optional manifest-driven import settings.
---

# Blender Target: Unity

The Unity target owns engine-level behavior only. Project budgets, exact pivots/sockets, vehicle dimensions, custom packed masks, prefab logic, and simulation semantics belong in reusable production policies, project profiles, or downstream repositories.

## Default production policy

The raw Unity `target.json` intentionally does **not** define universal prop/character triangle budgets, material caps, pivot rules, texel-density bands, LOD/collider naming, or socket naming. Those are not Unity engine requirements.

Normal commands automatically resolve the target's `default_policy: realtime-default` before an optional project profile. That reusable policy preserves the kit's backwards-compatible real-time defaults (including `solid_prop`) while keeping them explicitly attributable to Blender Agent Kit policy rather than Unity itself.

Resolution order:

```text
Unity engine target -> realtime-default production policy -> optional project profile
```

A project profile can override any resolved policy rule without modifying the Unity target.

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

For downstream projects that author multiple LOD hierarchies in one `.blend`, the target also exposes an opt-in export naming rule:

```json
{
  "strip_lod_suffix_on_export": true,
  "strip_lod_suffix_pattern": "_LOD[0-9]+$"
}
```

It is disabled in the base Unity target. When enabled by a project profile, names are normalized only inside the export context and restored afterward.

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
