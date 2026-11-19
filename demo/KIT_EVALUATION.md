# Blender Agent Kit v0.2.1 — Usability & Product Evaluation

**Evaluated Release:** `v0.2.1` (`0c6c3d10cb7265166fe46e7c5ccab69ff2abf793`)  
**Runtime:** Blender `5.2.4 LTS` (`cd5dc428cce1`), Python `3.11.2`, Debian GNU/Linux 12 (`x86_64`, CPU Cycles)  
**Trial Scope:** Independent end-to-end authoring, validation, texture packing, review rendering, and Unity-target FBX bundle export of two newly created 3D assets (`SupplyCrate` and `SciFiKit` — "Helios Conduit").

---

## A. Installation and Onboarding

| Dimension | Assessment | Observed Evidence |
| --- | --- | --- |
| **Ease of installation** | Good | `python3 tools/install.py --agent all --targets unity` succeeded on the first attempt (`Installed 18 skill links. Pointer: ~/.config/blender-agent-kit/manifest.json`). |
| **Dependency management** | Strong | Core host tooling (`runner.py`, `doctor.py`, `run.py`) uses Python 3.10+ stdlib only. Optional host dependencies (`Pillow 11.1.0`, `numpy 2.1.3`, `jsonschema 4.23.0`) worked without version conflicts. |
| **Blender discovery** | Fair (minor friction) | `tools/doctor.py` checks `BLENDER_EXECUTABLE`, `PATH`, and `/usr/local/bin`, `/usr/bin`, `/snap/bin`. Users extracting the official Blender 5.2 Linux tarball into `$HOME/opt/` hit `Blender executable not found. Set BLENDER_EXECUTABLE or add blender to PATH.` until configured. |
| **Documentation clarity** | Good overall, gaps in schemas/CLI | `README.md` and `DESIGN.md` clearly articulate architecture, boundaries, and known limits. However, README Quick Start uses `python` (not `python3` on Debian/Ubuntu) and omits a minimal external `project-profile.json` example. |
| **Skill discoverability** | Good | `skills/core/blender-core/SKILL.md` provides a clear routing table to all specialist skills (`blender-modeling`, `blender-uv-baking`, `blender-lod-collision`, `blender-asset-qa`, `blender-bundle`, `blender-target-unity`). |
| **First successful command** | Fast once `BLENDER_EXECUTABLE` is set | `python3 tools/doctor.py --device auto` and `run.py doctor --device auto` returned structured JSON with `meets_5_2_lts: true`, `cycles_device: "CPU"`, `addons: ["cycles", "io_scene_fbx", "io_scene_gltf2"]`, and `smoke_save_reopen: true`. All 3 test suites (`host` 33/33, `core` 16/16, `targets` unity) passed cleanly. |
| **Error messages** | Mixed | JSON schema errors on `project_profile` top-level keys were clear (`Missing required project-profile key: version; target_overrides`). Conversely, when Blender exited with code 127 (missing shared libs in a restricted container path), `runner.py` only emitted `"Blender exited with code 127 without writing result JSON."` without surfacing stderr inline; and malformed `required_parent_pairs` caused an unhandled `AttributeError` traceback. |
| **Cross-platform assumptions** | Minor Linux friction | README commands assume `python` exists in `PATH`. No Windows-only path bugs were encountered on Linux. |
| **Missing examples** | Moderate gap | No minimal standalone `project-profile.json` template or `review_presets` reference in README; had to inspect `schemas/project-profile.schema.json` and `shared/qa_checks.py` directly to discover exact key names (`resolution` vs `width`/`height`, `orthographic_views` vs `views`, `{child, parent}` dict format). |

---

## B. Capability-by-Capability Assessment

| Capability | Attempted | Result | Kit contribution | Custom work | Issues |
| --- | --- | --- | --- | --- | --- |
| **Modeling** | Yes (both demos) | Pass | Skill guidance only (`blender-modeling`: metric 1 BU = 1 m, `bottom_center_z0`, applied transforms, deterministic Python build scripts). | 100% custom procedural `bmesh` builders (`build_supplycrate.py`, `build_scifi_kit.py`). | Expected by design (kit explicitly documents that asset authoring is agent-authored Python). |
| **UV / baking** | Yes (both demos) | Pass | Skill guidance (`blender-uv-baking`: UV0 atlas/trim + UV1 `LightmapUV`, 16-bit OpenGL `+Y` normals, avoid Cycles DIFFUSE pass on metals). | Custom deterministic NumPy/Pillow 2048² & 1024² PBR generators + Blender `smart_project` UV1. | Kit provides no executable baking or texel-density measurement CLI; `uv1_overlap_unverified` warning emitted as documented. |
| **Texture packing** | Yes (3 materials across both demos) | Pass | **Built-in executable (`run.py pack`)**: deterministic Lanczos resampling (`--size`), safe expression packing (`1-roughness` into alpha), 16-bit normal preservation, `--detect-normal-y` heuristic, JSON report. | None for packing; custom verification script confirmed `MAE < 3e-8` smoothness alpha and 16-bit PNG headers. | Unity URP default `target.json` has no `_EmissionMap` slot (raw `emission.png` must be carried separately for `M_SciFi_Emissive`). |
| **LOD generation** | Yes (3 LODs SupplyCrate, 4 LODs Bulkhead) | Pass | Skill guidance (`blender-lod-collision`: naming `{name}_LOD{index}`, monotonic triangle counts) + **built-in QA enforcement** of monotonicity & per-LOD budgets. | Custom parametric multi-LOD geometry in builder scripts. | No executable decimation/LOD-generation command; manual/parametric authoring required. |
| **Collision** | Yes (1-hull SupplyCrate, 3-hull walkable Bulkhead) | Pass | Naming contract (`{name}_COL_{index:02d}`), **built-in collider wireframe overlay renderer** (`collision_view: true`), and FBX bundle round-trip verification. | Custom convex hull box generation in builder scripts. | `scene_inspector` counts `*_COL_*` inside `lods["0"]` unless a project profile manually adds `lod_exclude_patterns: ["*_COL_*"]`; no convexity check. |
| **QA** | Yes (both demos, base + custom profile) | Pass | **Built-in executable (`run.py qa`)**: checked root count, `bottom_center_z0` pivot tolerance (`0.001 m`), applied scale, non-manifold/boundary edges, signed volume, UV0/UV1 presence, LOD monotonicity, material budgets, `required_nodes`, `required_parent_pairs`. | External profile JSONs (`supplycrate.profile.json`, `scifikit.profile.json`). | Unhandled `AttributeError` when `required_parent_pairs` used list pairs instead of `{child, parent}` dicts (missing schema validation). |
| **Hierarchy / sockets** | Yes (`SF_Bulkhead_Arch`: 15 objs, depth-2 `Header`, 6 `Socket_*`) | Pass | **Built-in executable (`run.py bundle` + Unity `prebake_yup_hierarchy`)**: basis conversion `C·R·C⁻¹` for frames, `C·R` for `Socket_*` directional empties, depth ≥ 2 parent-world reconstruction, scene restoration, QA parent-pair checks. | Authoring socket empties and parent hierarchy in `build_scifi_kit.py`. | None — worked reliably on the first valid run with `0` parent or transform mismatches on fresh re-import. |
| **Review rendering** | Yes (both demos) | Pass | **Built-in executable (`run.py review`)**: automated Cycles CPU/GPU rendering of orthographic views, close-ups, per-LOD × viewing-distance range matrices, auto-scaled lighting, and collision wireframe overlay over LOD0. | Custom Cycles renders for the assembled interior Sci-Fi corridor (`hero_corridor_1920x1080.png`) and 6-module catalog grid. | `review_shots.py` ignores `qa.common.lod_exclude_patterns`, reporting `4,216` LOD0 tris instead of `4,204` in `review_tiles.json`. |
| **Contact sheets** | Yes (tested built-in; delivered custom) | Partial / Workaround | **Built-in executable (`tools/review_compose.py`)** tested on 2×2 SupplyCrate orthographics (`kit_compositor_sample.webp`); fails closed on missing/flat tiles. | Custom Pillow compositors (`compose_showcase.py`, `compose_scifi_showcase.py`) required for all 11 final showcase sheets. | `review_compose.py` hardcodes Pillow's 10px bitmap `ImageFont.load_default()` (illegible at 1920px / README width), lacks sheet titles, cannot read 16-bit PNGs properly, and cannot visualize `_MetallicGlossMap` alpha. |
| **FBX export** | Yes (10 FBX files via `run.py bundle`) | Pass | **Built-in executable (`run.py bundle`)**: collection and root-hierarchy selection, Unity Y-up prebake, triangulation, tangents, zero embedded images, deterministic SHA256 build hash. | Authoring `bundle-spec.json` files. | None — all 10 FBX parts exported cleanly. |
| **Round-trip checking** | Yes (all 10 FBX files) | Pass | **Built-in executable** inside `run.py bundle`: fresh-imports every FBX into Blender, checks triangle parity, object presence, parent hierarchy, scale, child local transforms, Y-up root wrapper, and binary PNG/JPEG magic headers. | None. | Strongest automated verification feature in the kit; zero false positives or failures across all 10 FBXs. |
| **JSON evidence** | Yes (all subcommands) | Pass | **Built-in `--result-json`** on `inspect`, `qa`, `pack`, `bundle`, `review`, and `review_compose.py` (host-owned in v0.2.1). | Custom aggregation for `environment.json`, `texture_validation.json`, and archive `manifest.json`. | Clean, parseable schemas across all subcommands. |

---

## C. Bugs Actually Caught by the Toolkit

No bugs were artificially injected; both defects below occurred organically during independent asset authoring and were caught automatically by `run.py qa`.

### Bug 1 — Unrooted Multi-LOD SupplyCrate Scene
1. **Original defective condition:** The initial `build_supplycrate.py` linked `SupplyCrate_LOD0`, `SupplyCrate_LOD1`, `SupplyCrate_LOD2`, and `SupplyCrate_COL_01` directly at scene root (`4` roots) without a shared parent `EMPTY` root.
2. **Command that caught it:** `python3 skills/core/blender-core/scripts/run.py qa --blend SupplyCrate/scenes/SupplyCrate.blend --target unity --asset-class solid_prop --result-json SupplyCrate/evidence/qa.json`
3. **Original machine-readable error (`SupplyCrate/evidence/qa_before_root_fix.json`):**
   ```json
   {
     "code": "pivot_rule",
     "error": "bottom_center_z0 requires exactly one selected scene root"
   }
   ```
4. **Corrective action:** Added a single `SupplyCrate` `EMPTY` root at `(0.0, 0.0, 0.0)` and parented all 3 LODs and `SupplyCrate_COL_01` under it.
5. **Corrected run evidence:** `SupplyCrate/evidence/qa.json` (`"roots": ["SupplyCrate"]`, `"passed": true`, `"errors": []`).
6. **Would it have escaped without the toolkit?** Likely yes during standalone visual review — renders looked identical without a root Empty, yet Unity prefab/LODGroup hierarchy expectations would have received 4 ungrouped top-level nodes.

### Bug 2 — 2.5 mm Y-Axis Bounding-Box Pivot Offset from Asymmetric Hardware
1. **Original defective condition:** Front draw latches protruded `0.034 m` past `-Y` (`-0.434 m`) while rear barrel hinges protruded `0.029 m` past `+Y` (`+0.429 m`), shifting the overall bounding-box Y-center by `-2.5 mm` (`-0.0025 m`) off `(0, 0, 0)`.
2. **Command that caught it:** `python3 skills/core/blender-core/scripts/run.py qa --blend SupplyCrate/scenes/SupplyCrate.blend --target unity --asset-class solid_prop`
3. **Original machine-readable error (`SupplyCrate/evidence/qa_before_pivot_center_fix.json`):**
   ```json
   {
     "code": "pivot_rule",
     "error": "root origin [0.0, 0.0, 0.0] is not bottom-center [0.0, -0.002499997615814209, 0.0] within 0.001",
     "object": "SupplyCrate"
   }
   ```
4. **Corrective action:** Computed LOD0's X/Y bounding-box center `(dx0, dy0)` in `build_supplycrate.py` and recentered all LODs and `SupplyCrate_COL_01` vertices before saving so `bounds.center` is `[0.0, 0.0, 0.3645]`.
5. **Corrected run evidence:** `SupplyCrate/evidence/qa.json` (`"bounds": {"min": [-0.5955, -0.4315, 0.0], "max": [0.5955, 0.4315, 0.7290], "center": [0.0, 0.0, 0.3645]}`, `"passed": true`).
6. **Would it have escaped without the toolkit?** Almost certainly yes — a 2.5 mm shift is completely invisible in renders and viewport inspection, yet breaks strict `bottom_center_z0` snapping tolerances.

---

## D. Toolkit Defects and Limitations

### Confirmed Defects

#### Defect 1 — Unhandled `AttributeError` on `required_parent_pairs` List Format (Missing Schema Validation)
- **Exact command:** `python3 skills/core/blender-core/scripts/run.py qa --blend SciFiKit/scenes/SF_Bulkhead_Arch.blend --target unity --project-profile SciFiKit/source/scifikit.profile.json --asset-class modular_bulkhead`
- **Expected behavior:** Schema validation rejects malformed `required_parent_pairs` with a descriptive validation error pointing to `{"child": ..., "parent": ...}`.
- **Actual behavior:** Passed `load_project_profile()` validation and crashed inside Blender with `AttributeError: 'list' object has no attribute 'get'` at `shared/qa_checks.py:473`.
- **Reproduction steps:** Put `"required_parent_pairs": [["Child", "Parent"]]` in a project profile's `target_overrides.unity.qa.asset_classes.<cls>` and invoke `run.py qa`.
- **Error JSON:** Archived in `SciFiKit/evidence/qa_bulkhead_schema_crash.json`.
- **Severity:** Medium (`P1`).
- **Workaround:** Use `{"child": "Child", "parent": "Parent"}` objects.
- **Root cause:** `project-profile.schema.json` allows arbitrary `"additionalProperties": {"type": "object"}` under `target_overrides`, and `target.schema.json` does not validate `required_parent_pairs` item structure after merge.
- **Recommended generic fix:** Define strict `required_parent_pairs` schema (`type: object, required: [child, parent]`) in `target.schema.json` and validate the merged target before running QA.

#### Defect 2 — `review_shots.py` Ignores Profile `qa.common.lod_exclude_patterns`
- **Exact command:** `python3 skills/core/blender-core/scripts/run.py review --blend SupplyCrate/scenes/SupplyCrate.blend --project-profile SupplyCrate/source/supplycrate.profile.json --preset showcase_tiles`
- **Expected behavior:** `review_tiles.json` `inventory.lods["0"].tri_count` excludes `SupplyCrate_COL_01` (`4,204` tris), matching `qa.json`.
- **Actual behavior:** `review_tiles.json` reports `lods["0"].tri_count = 4216` (`SupplyCrate_COL_01` + `SupplyCrate_LOD0`), contradicting `qa.json` (`4,204`).
- **Severity:** Low–Medium (`P1`).
- **Workaround:** Always source LOD triangle counts for contact sheets from `qa.json` or `bundle.json`, never from `review.json`.
- **Root cause:** `shared/review_shots.py` calls `inspect_scene()` without passing `lod_exclude_patterns` from the merged target/profile.
- **Recommended generic fix:** Pass merged `qa.common.lod_exclude_patterns` (and default collider exclusion) to `inspect_scene()` inside `review_shots.py`.

#### Defect 3 — `run.py <subcommand> --help` Does Not Display Subcommand Flags
- **Exact command:** `python3 skills/core/blender-core/scripts/run.py qa --help` (and `pack`, `export`, `bundle`, `review`).
- **Expected behavior:** Displays the flags accepted by the subcommand (`--target`, `--asset-class`, `--size`, `--preset`, etc.).
- **Actual behavior:** Displays only the top-level `run.py` options (`--blend`, `--blender`, `--addons`, `--result-json`).
- **Severity:** Medium DX friction (`P1`).
- **Workaround:** Read `shared/*.py` source files to discover CLI arguments.
- **Root cause:** `run.py` parses `-h/--help` on the top-level `ArgumentParser` before forwarding remaining args.
- **Recommended generic fix:** Register subparsers or forward `--help` when a subcommand is present (or maintain host-side subcommand help text without launching Blender).

### Usability Limitations (Non-Crash)

1. **`tools/review_compose.py` presentation & image-format limits (`P1`):** Uses Pillow's tiny 10px bitmap `ImageFont.load_default()` (unreadable on 1920px+ sheets and GitHub README previews), has no sheet header/banner, calls `Image.open().convert("RGB")` which fails to properly normalize 16-bit PNGs (like `_BumpMap`), and has no alpha-channel split visualization for `_MetallicGlossMap`.
2. **Colliders counted in `lods["0"]` by default (`P1`):** `scene_inspector.py` detects `*_COL_*` into `inventory.colliders` yet still sums their triangles into `inventory.lods["0"]` unless a custom project profile specifies `lod_exclude_patterns: ["*_COL_*"]`.
3. **No `_EmissionMap` slot in Unity URP default `target.json` (`P2`):** Emissive sci-fi materials must carry `emission.png` outside `run.py pack` or add a custom project profile override.
4. **Silent stderr on Blender startup crash (`P2`):** `shared/runner.py` writes stderr to `/tmp/blender-agent-kit-logs/*.log` but omits a stderr snippet from the returned JSON error payload.
5. **Documented explicit QA limits (`P3`):** `uv1_overlap_unverified`, no texel-density measurement, no collider convexity check.

---

## E. Developer Experience

### Strong Points
- **Clean architectural layering:** Separating generic Blender mechanics (`shared/`), engine targets (`plugins/targets/`), and external project profiles keeps downstream asset scripts completely decoupled from Unity axis/FBX/texture quirks.
- **Host-owned `--result-json` (v0.2.1 fix):** Every operational subcommand (`inspect`, `qa`, `pack`, `bundle`, `review`) cleanly writes deterministic, machine-readable JSON without stdout scraping.
- **Hierarchy-safe Unity Y-up static prebake:** Exported a 15-object, depth-2 bulkhead hierarchy with 6 directional `Socket_*` empties and verified `0` parent/transform errors on Blender fresh re-import — zero custom axis-conversion code needed.
- **Channel packing reliability:** `run.py pack` handled 2048² and 1024² maps, preserved 16-bit OpenGL normals, and packed `1-roughness` into `_MetallicGlossMap` alpha with `MAE < 3e-8`.

### Weak Points
- **CLI discoverability:** `run.py <subcommand> --help` hiding subcommand flags forces agents/developers to read Python source files.
- **Contact-sheet readiness:** `tools/review_compose.py` is currently a minimal proof-of-concept rather than a README-ready showcase compositor (tiny bitmap font, no header, no 16-bit/alpha support), forcing custom Pillow scripts for production presentation.
- **Profile authoring friction:** Lack of a documented minimal `project-profile.json` example and incomplete `target_overrides` schema validation caused two avoidable trial-and-error iterations.
