---
name: blender-batch
description: Use for bounded folder-scale QA, texture packing, export/bundle, or QA-gated delivery with per-asset subprocess isolation, safe content caching, and measured timing telemetry.
---

# Blender Batch

Discover the exact command first:

```bash
python <blender-core>/scripts/run.py batch --help
```

Examples:

```bash
# QA every .blend in one folder
python <blender-core>/scripts/run.py batch \
  --operation qa --input-dir assets \
  --target unity --asset-class solid_prop --out batch-build

# Export and fresh-import verify every .blend
python <blender-core>/scripts/run.py batch \
  --operation export --input-dir assets \
  --target unity --profile urp --out batch-build

# Pack one raw-map directory per asset (child directory name = asset id)
python <blender-core>/scripts/run.py batch \
  --operation pack --input-dir raw-assets \
  --target unity --profile urp --material Body --out batch-build
```

## Safety/caching

- Blender-backed misses execute in isolated headless subprocesses.
- Jobs are bounded by `--max-assets` (default 100); empty discovery fails closed.
- Cache identity includes source bytes, resolved target/policy/project configuration, toolkit executable/config identity, operation options, and Blender executable/version identity.
- Export/bundle cache hits additionally verify manifest build hashes and required artifact files.
- `--refresh-cache` forces rebuild; `--no-cache` disables read/write caching.
- Batch telemetry measures wall durations/cache/process counts only. It does **not** invent model/API tokens or agent-turn metrics.

Bundle jobs use a per-asset spec template (default `{stem}.bundle.json`); `deliver` jobs may optionally use the same template.
