---
name: blender-bundle
description: Use this skill for compound game assets that export as multiple semantic files such as chassis/station, modular kits, collision proxies, wrecks, or separate LOD files. Uses a declarative bundle spec and records per-part inventory and round-trip evidence.
---

# Blender Semantic Bundle Export

Use a bundle spec when one logical asset produces multiple engine files. The core stays generic: roles are free-form strings and downstream project profiles define their own meaning.

```json
{
  "schema_version": "1.0",
  "asset_id": "Vehicle01",
  "parts": [
    { "id": "body_lod0", "role": "chassis", "lod": 0, "collection": "Body_LOD0", "file": "Vehicle01_Body_LOD0.fbx" },
    { "id": "collision", "role": "collision", "collection": "Collision", "file": "Vehicle01_Collision.fbx" }
  ]
}
```

Run:

```bash
python <blender-core>/scripts/run.py bundle --blend vehicle.blend \
  --spec bundle.json --target unity --out build/
```

Each part is exported independently, inventoried, re-imported into a fresh Blender scene, and compared for object names, hierarchy, scale, and triangle count. The resulting `*.bundle.manifest.json` is machine-readable evidence for downstream delivery tooling.
