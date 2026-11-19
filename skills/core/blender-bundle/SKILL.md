---
name: blender-bundle
description: Use this skill for compound game assets exported as multiple semantic files such as chassis/station, modular kits, collision proxies, wrecks, or separate LOD files. Uses a declarative bundle spec and records per-part authoring, export, and round-trip evidence.
---

# Blender Semantic Bundle Export

A bundle represents one logical asset composed of multiple files. Roles are free-form strings; project profiles define their meanings.

```json
{
  "schema_version": "1.0",
  "asset_id": "Vehicle01",
  "parts": [
    {
      "id": "body_lod0",
      "role": "chassis",
      "lod": 0,
      "collection": "Body_LOD0",
      "file": "Vehicle01_Body_LOD0.fbx"
    },
    {
      "id": "station_lod0",
      "role": "station",
      "lod": 0,
      "root": "Vehicle01_Station",
      "file": "Vehicle01_Station_LOD0.fbx",
      "zero_root_location": true
    }
  ]
}
```

Run:

```bash
python <blender-core>/scripts/run.py bundle \
  --blend vehicle.blend --spec bundle.json \
  --target unity --out build/
```

## Root handling

`zero_root_location: true` temporarily sets the selected part root location to zero for export and restores the assembled authoring location immediately afterward.

Profiles may supply:

```json
{
  "bundle_defaults": {
    "zero_root_location_roles": ["station", "kit"]
  }
}
```

The generic exporter does not hardcode role meanings.

## Evidence

Every part records:

- role, LOD, file, export root;
- `assembly_inventory` from the assembled authoring scene;
- `inventory` in the actual export coordinate basis;
- total/intact/damage triangle counts;
- materials;
- Blender fresh-import result;
- hierarchy/local-transform comparison;
- zero-root result;
- FBX embedded PNG/JPEG scan.

The resulting `*.bundle.manifest.json` is intended as machine evidence for downstream engine verification and delivery-document generation.
