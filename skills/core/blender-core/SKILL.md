---
name: blender-core
description: Start here for Blender Agent Kit. Discover executable capabilities and the resolved production contract before authoring or running headless Blender workflows.
---

# Blender Core

Use executable discovery before reading implementation files:

```bash
python <blender-core>/scripts/run.py capabilities --json
python <blender-core>/scripts/run.py contract --target unity --asset-class solid_prop
```

Add `--project-profile <name-or-json>`, `--profile <texture-profile>`, or `--preset <review-preset>` to `contract` when relevant.

## Minimum safe workflow

1. Read the resolved contract.
2. Author or modify the asset with the relevant specialist skill.
3. Prefer `deliver --blend <asset.blend>` for QA-gated review/export delivery; it stops before expensive stages when QA fails.
4. Use individual `qa`, `pack`, `review`, `export`, or `bundle` commands when you need stage-level control.
5. Preserve machine-readable results, stage timings, and source/build inputs.

Use `run.py <command> --help` for exact flags. Engine semantics belong to target plugins; reusable production defaults belong to policies; project-specific rules belong to project profiles.
