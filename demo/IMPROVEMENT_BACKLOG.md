# Blender Agent Kit v0.2.1 — Product Improvement Backlog

Prioritized, generic, reusable product recommendations derived directly from independent production usage across `SupplyCrate` and `SciFiKit`. No game-specific or downstream project semantics are introduced.

---

## P0 — Blocking Defects

*No P0 blocking defects were encountered in v0.2.1.* Both demonstrations completed end-to-end (modeling, URP texture packing, QA, review rendering, and 10-part FBX round-trip verification) without modifying any production code in the toolkit.

---

## P1 — High-Value Improvements

### P1-1: Upgrade `tools/review_compose.py` to TrueType Fonts, Sheet Headers, 16-Bit PNG & Alpha-Split Tiles
- **Problem observed:** `review_compose.py` uses `ImageFont.load_default()` (10px bitmap font, illegible at 1920px+ / GitHub README width), lacks a top title/subtitle banner, converts images via Pillow `.convert("RGB")` (which fails to properly render 16-bit normal PNGs), and cannot visualize RGBA alpha channels (`_MetallicGlossMap` smoothness).
- **Actual evidence:** Tested `tools/review_compose.py` on SupplyCrate orthographics (`SupplyCrate/evidence/kit_compositor_sample.webp`); had to write two custom Pillow scripts (`compose_showcase.py`, `compose_scifi_showcase.py`, ~450 LOC combined) to meet visual legibility and 9-map PBR inspection standards.
- **Proposed solution:** Auto-discover system TrueType fonts (`DejaVuSans`, `LiberationSans`, `Arial`, `Segoe UI`) with configurable `font_size`, add optional `title`/`subtitle` header bar, support a `mode: "split_alpha"` tile option for RGBA packed masks, and reuse `shared/channel_pack.py`'s 16-bit PNG decoder for 16-bit tiles.
- **Generality:** Universal across all props, characters, vehicles, and environment kits.
- **Expected benefit:** Eliminates ~200+ LOC of custom contact-sheet code per asset and makes `review_compose.py` immediately README-ready.
- **Implementation complexity:** Low–Medium (1–2 days, pure host Python).
- **Suggested priority:** **P1**

### P1-2: Validate Merged `target_overrides` Against Full `target.schema.json` (Fix `required_parent_pairs` Crash)
- **Problem observed:** Passing `"required_parent_pairs": [["Child", "Parent"]]` in an external project profile passed `load_project_profile()` validation and crashed inside Blender at `shared/qa_checks.py:473` with `AttributeError: 'list' object has no attribute 'get'`.
- **Actual evidence:** `SciFiKit/evidence/qa_bulkhead_schema_crash.json`.
- **Proposed solution:** Define explicit JSON Schema constraints for `required_parent_pairs` (`{"type": "object", "required": ["child", "parent"]}`) and all `qa.asset_classes.*` fields in `schemas/target.schema.json`, and run schema validation on the merged target immediately after `load_profiled_target()`.
- **Generality:** Universal for any user authoring external project profiles.
- **Expected benefit:** Turns cryptic in-Blender tracebacks into instant, actionable host-side validation errors.
- **Implementation complexity:** Low (0.5 day).
- **Suggested priority:** **P1**

### P1-3: Exclude Colliders from `lods["0"]` by Default & Sync `review_shots.py` with `lod_exclude_patterns`
- **Problem observed:** `scene_inspector.py` detects `*_COL_*` objects into `inventory.colliders` yet still sums their triangles into `inventory.lods["0"]` unless a profile specifies `lod_exclude_patterns: ["*_COL_*"]`. Furthermore, `review_shots.py` ignores `lod_exclude_patterns`, causing `review_tiles.json` (`4,216` tris) to disagree with `qa.json` (`4,204` tris).
- **Actual evidence:** `SupplyCrate/evidence/qa_base.json` and `SupplyCrate/evidence/review_tiles.json` vs `SupplyCrate/evidence/qa.json`.
- **Proposed solution:** Automatically exclude objects classified as colliders (`inventory.colliders`) from visible LOD triangle aggregates in `scene_inspector.py`, and ensure `review_shots.py` passes the active target/profile's `lod_exclude_patterns` to `inspect_scene()`.
- **Generality:** Universal for every asset with a collision proxy.
- **Expected benefit:** Eliminates misleading LOD0 triangle counts across QA, inspect, and review reports without requiring boilerplate profile overrides.
- **Implementation complexity:** Low (0.5 day).
- **Suggested priority:** **P1**

### P1-4: Forward Subcommand `--help` in `run.py` Without Requiring Source Inspection
- **Problem observed:** Running `python3 skills/core/blender-core/scripts/run.py <subcommand> --help` prints only the top-level `run.py` usage (`--blend`, `--blender`, `--addons`, `--result-json`), hiding all subcommand flags (`--target`, `--asset-class`, `--size`, `--preset`, `--spec`, etc.).
- **Actual evidence:** Observed across all 6 subcommands (`inspect`, `qa`, `pack`, `export`, `bundle`, `review`) during onboarding.
- **Proposed solution:** Register lightweight subparsers in `run.py` (or forward `--help` to a fast host-side help printer) so `run.py <subcommand> --help` prints all flags and defaults immediately.
- **Generality:** Universal across all CLI users and autonomous agents.
- **Expected benefit:** Cuts onboarding time and eliminates needing to grep `shared/*.py` to discover flags.
- **Implementation complexity:** Low (0.5 day).
- **Suggested priority:** **P1**

---

## P2 — Usability Improvements

### P2-1: Add Optional `_EmissionMap` Slot to Unity URP/HDRP Target Texture Profiles
- **Problem observed:** Unity URP's `target.json` only packs `albedo`, `metallic_smoothness`, `normal`, and `ao`. Emissive materials (`M_SciFi_Emissive` with `emission.png`) cannot be packed/resized/manifested through `run.py pack` without a custom profile override.
- **Actual evidence:** `SciFiKit/evidence/pack_emissive.json` packed 4 maps while ignoring `raw_textures/emissive/emission.png`.
- **Proposed solution:** Add an optional `emission` map entry (`unity_slot: "_EmissionMap"`, `srgb: true`, `bit_depth: 8`, emitted only when `emission.png` is present in `--input-dir`).
- **Generality:** Applies to all sci-fi, architectural, vehicle, and UI/prop assets with glowing elements.
- **Expected benefit:** Complete out-of-the-box URP/HDRP emissive workflow with manifest tracking.
- **Implementation complexity:** Low (0.5 day).
- **Suggested priority:** **P2**

### P2-2: Surface Stderr Tail in `runner.py` Error JSON on Non-Zero Blender Exit
- **Problem observed:** When Blender exited with code 127 (missing shared library), `runner.py` returned `"Blender exited with code 127 without writing result JSON."` and hid the actual `libblender_cpu_check.so` error inside `/tmp/blender-agent-kit-logs/*.log`.
- **Actual evidence:** Milestone 1 doctor failure log `/tmp/blender-agent-kit-logs/tools_doctor_blender_2177.log`.
- **Proposed solution:** Include `"stderr_tail"` (last ~10 non-empty lines of stderr) directly in the returned JSON payload on failure.
- **Generality:** Universal for headless CI and autonomous agent debugging.
- **Expected benefit:** Saves an extra diagnostic turn on every Blender crash.
- **Implementation complexity:** Trivial (< 0.25 day).
- **Suggested priority:** **P2**

### P2-3: Add Minimal External `project-profile.json` & `review_presets` Reference to README
- **Problem observed:** README lists `project-profile` capabilities in prose but does not include a copy-paste minimal JSON example, leading to initial schema mismatch errors (`width`/`height` vs `resolution`, `views` vs `orthographic_views`, missing `version`/`target_overrides`).
- **Actual evidence:** Milestone 2 initial `supplycrate.profile.json` validation error.
- **Proposed solution:** Add a 20-line minimal external `project-profile.json` snippet to `README.md` and note `python3` for Linux/macOS in Quick Start.
- **Generality:** Universal for onboarding.
- **Expected benefit:** Eliminates first-attempt profile schema errors.
- **Implementation complexity:** Trivial (< 0.25 day).
- **Suggested priority:** **P2**

---

## P3 — Future Capabilities

### P3-1: Geometric UV1 Overlap & Texel-Density Verification in `qa_checks.py`
- **Problem observed:** Both `SupplyCrate` (3 warnings) and `SF_Bulkhead_Arch` (4 warnings) emitted `uv1_overlap_unverified`, and `texel_density_px_per_m` in `target.json` is currently declarative only.
- **Actual evidence:** `SupplyCrate/evidence/qa.json` and `SciFiKit/evidence/qa_bulkhead.json`.
- **Proposed solution:** Implement 2D triangle-intersection / rasterized coverage check on UV1 and world-area vs UV-area texel density bands in `shared/qa_checks.py`.
- **Generality:** Universal across all lightmapped game assets.
- **Expected benefit:** Closes the largest remaining gap in automated static-mesh QA.
- **Implementation complexity:** Medium–High (3–5 days).
- **Suggested priority:** **P3**

### P3-2: Optional Executable LOD Decimation & Convex-Hull Collision Helper Subcommand
- **Problem observed:** `blender-lod-collision` is currently skill documentation only; agents must write custom decimation or parametric LOD and convex-hull code in every builder script.
- **Actual evidence:** Both `build_supplycrate.py` and `build_scifi_kit.py` authored custom multi-LOD and collision-box builders.
- **Proposed solution:** Provide an opt-in `run.py optimize` (or helper module in `shared/`) supporting planar/collapse decimation with UV/seam preservation and single/multi-hull convex collider generation + convexity QA proof.
- **Generality:** High for rapid prop prototyping (while still allowing hand-authored parametric LODs).
- **Expected benefit:** Further reduces authoring boilerplate for standard props.
- **Implementation complexity:** Medium–High (4–6 days).
- **Suggested priority:** **P3**
