---
name: blender-target-unity
description: Unity engine target for Blender Agent Kit. Owns coordinate/export behavior and standard URP/HDRP texture layouts; production budgets and naming are supplied by resolved policies/profiles.
---

# Blender Target: Unity

Use `run.py contract --target unity --asset-class <class>` for the effective contract. The resolution order is:

```text
Unity engine target -> default production policy -> optional project profile
```

## Engine semantics

- Static hierarchy export uses Unity-friendly Y-up/+Z-forward conversion and restores the authoring scene afterward.
- Standard static export is FBX; GLB is available where configured.
- Standard URP/HDRP texture packing is target-owned.
- Embedded textures are disabled by default.
- Static hierarchy round-trip checks cover names, hierarchy/local transforms, scale, triangles, and embedded-image headers.
- Rigged exports do not use the static hierarchy prebake.

Triangle/material budgets, pivots, LOD/collider/socket naming, dimensions, and game semantics are **not universal Unity requirements**; read them from the resolved production contract.
