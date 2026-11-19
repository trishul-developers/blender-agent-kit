---
name: blender-batch
description: Use this skill when running headless QA, channel packing, or target exports across a folder of .blend assets with incremental build_hash caching and structured JSON inventory output.
---

# Blender Batch Pipeline

## Rules
1. Isolate each asset in its own headless subprocess (or reset state via `bpy.ops.wm.read_factory_settings(use_empty=True)`) to prevent image and undo datablock leaks across long runs.
2. Compare `build_hash` in each asset's `*.asset.manifest.json` against source `.blend`/script hashes to skip unchanged assets during incremental rebuilds.
3. Never write outputs into the source folder; always emit into a dedicated `--out` directory and summarize results as machine-readable JSON.
