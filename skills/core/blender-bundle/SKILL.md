---
name: blender-bundle
description: Use when one logical asset exports as multiple semantic files. Bundle specs select roots/collections and record per-part inventory, export, and fresh-import evidence.
---

# Blender Semantic Bundle Export

Use a declarative bundle spec and the resolved contract:

```bash
python <blender-core>/scripts/run.py bundle   --blend asset.blend --spec bundle.json   --target unity --out build/
```

A part selects exactly one collection or root hierarchy. `zero_root_location` is explicit; project profiles may provide role defaults. Export-time name normalization, when enabled by the resolved contract, is temporary and authoring names are restored.

Each part records authoring/export inventories, triangles/materials, hierarchy, fresh-import verification, root handling, and embedded-image checks.

See `references/bundle-spec.example.json` for a neutral example. Role strings are free-form; their meanings are downstream policy.
