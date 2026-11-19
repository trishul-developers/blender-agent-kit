# Independent Agent Evaluation Report — Blender Agent Kit v0.2.1

**Toolkit:** `https://github.com/trishul-developers/blender-agent-kit` · Tag `v0.2.1` · Commit `0c6c3d10cb7265166fe46e7c5ccab69ff2abf793`  
**Blender:** `5.2.4 LTS` (`cd5dc428cce1`) · **Host:** Debian GNU/Linux 12 (`x86_64`, Python `3.11.2`, Cycles CPU)

---

## Executive Summary

Blender Agent Kit `v0.2.1` was independently installed, verified, and evaluated through full production of two newly authored, materially distinct 3D demonstrations:

1. **Demonstration A — `SupplyCrate`**: A weathered industrial wooden-and-steel shipping crate (`1.19 × 0.86 × 0.73 m`, 2048² procedural PBR atlas, 3 LODs `4,204 / 1,084 / 136` tris, `12`-tri closed convex collision proxy, 4-part Unity URP FBX bundle, 6 master PNG + WebP showcase images).
2. **Demonstration B — `SciFiKit` ("Helios Conduit")**: A 6-piece industrial sci-fi modular environment kit (`4.0 × 4.0 × 3.6 m` grid, 2048² 5-band trim sheet + 1024² emissive telemetry trim, 21-instance assembled L-shaped corridor totaling `109` objects / `13,308` tris, hero 4-LOD `SF_Bulkhead_Arch` with `2,392 / 904 / 336 / 60` tris, 3-hull walkable collision `36` tris, depth-2 nested hierarchy + 6 directional `Socket_*` empties, 6-part Unity URP FBX bundle, 5 master PNG + WebP showcase images).

**Verdict:** Blender Agent Kit `v0.2.1` delivered **strong, measurable pipeline value** — saving an estimated **74%–80% on pipeline-only engineering** and **55%–63% across combined end-to-end production** — while catching **2 real asset bugs** automatically (`qa_before_root_fix.json` and `qa_before_pivot_center_fix.json`) and passing **100% of Blender fresh-import FBX round-trip checks across all 10 exported FBX files** with zero embedded images and zero hierarchy/transform errors. No P0 blocking defects were found. The main areas for improvement are `tools/review_compose.py` (tiny 10px bitmap font, no 16-bit/alpha handling), `run.py <subcommand> --help` discoverability, `required_parent_pairs` schema validation, and excluding colliders from `lods["0"]` by default across both `qa` and `review`.

---

## Verification Summary

| Component | Status | Key Machine Evidence |
| --- | --- | --- |
| **Environment & Tests** | PASS | `environment.json` · `doctor=ok`, `host` 33/33, `core` 16/16, `targets` unity PASS, `validate_skills` VALID |
| **SupplyCrate QA & Packing** | PASS | `SupplyCrate/evidence/qa.json` (`0` errors, `4,204 / 1,084 / 136` tris) · `pack.json` (16-bit `_BumpMap`, smoothness `MAE=2.23e-08`) |
| **SupplyCrate Bundle Round-Trip** | PASS (4/4) | `SupplyCrate/evidence/bundle.json` (`sha256:e23b269265ceb404fc4894020a29186f`, all 4 FBXs exact tri parity, 0 embedded images) |
| **SciFiKit Bulkhead QA & Packing** | PASS | `SciFiKit/evidence/qa_bulkhead.json` (`0` errors, 7/7 nodes, 4/4 parent pairs, `2,392 / 904 / 336 / 60` tris) · `pack_trim_sheet.json` (16-bit `_BumpMap`, smoothness `MAE=2.99e-08`) |
| **SciFiKit Bundle Round-Trip** | PASS (6/6) | `SciFiKit/evidence/bundle_bulkhead.json` (`sha256:ab55dc7252e998de4d2d35c22800e128`, 15-object complete hierarchy `3,728` tris, 0 parent/transform errors, 0 embedded images) |

> **Scope Note:** Unity Editor was not installed or executed in this Linux container; all engine-target verification is strictly based on Blender 5.2.4 LTS fresh-import round-trip parity, binary FBX header scans, and PNG bit-depth/channel validation.

---

## Supporting Documents in This Archive

- `environment.json` — Complete OS, Blender 5.2.4 LTS, Python, dependency, doctor, test-suite, and installation-issue record
- `KIT_EVALUATION.md` — Detailed onboarding, capability table, real bugs caught, confirmed defects, limitations, and DX review
- `EFFORT_ANALYSIS.md` — Measured activity inventory, no-kit baseline methodology, and effort-savings ranges with confidence levels
- `IMPROVEMENT_BACKLOG.md` — Prioritized `P0`–`P3` generic product recommendations
- `manifest.json` — Complete file inventory with SHA256 checksums for every deliverable file
- `SupplyCrate/README.md` & `SciFiKit/README.md` — Per-demo specs, metrics, showcase galleries, and exact clean-checkout reproduction commands
