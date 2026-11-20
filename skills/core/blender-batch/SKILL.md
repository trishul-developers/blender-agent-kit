---
name: blender-batch
description: Guidance for repeated/folder-scale Blender processing. v0.2.3 currently has no public batch subcommand; use capabilities as executable truth until issue #11 lands.
---

# Blender Batch Guidance

**Guidance-only in the current command surface.** Do not assume `run.py batch` exists; confirm with `run.py capabilities --json`.

For external orchestration today:
- isolate assets in separate headless Blender processes (or reset factory state);
- write outputs outside source folders;
- retain per-asset JSON results;
- include source/config/tool identity in cache keys;
- never treat file existence alone as a valid cache hit.

Issue #11 tracks first-class batch, caching, and telemetry support.
