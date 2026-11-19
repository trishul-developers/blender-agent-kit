---
name: blender-lod-collision
description: Use this skill when generating LOD chains (_LOD0, _LOD1, _LOD2) and simplified convex collision proxies for game assets in headless Blender, using naming and triangle budgets from the active target.json.
---

# Blender LOD & Collision Generation

## Workflow
1. Read `naming.lod_pattern`, `naming.collider_pattern`, and `qa.asset_classes.<class>.max_tris` from the active target plugin (`target.json`).
2. Generate strictly monotonic LOD meshes (`LOD0 > LOD1 > LOD2` triangle counts) using Planar Decimate for hard-surface assets and Collapse Decimate for organic assets; verify UV integrity and silhouette preservation after decimation.
3. Never decimate deforming character meshes without checking skin weights and joint loops.
4. Generate simplified convex hull collision proxies using indexed naming (e.g., `{name}_COL_01`, `{name}_COL_02` for multi-hull decomposition).
5. Run `blender-asset-qa` to verify monotonic LOD counts and collider naming before export.
