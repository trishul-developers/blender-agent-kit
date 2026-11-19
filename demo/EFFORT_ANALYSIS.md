# Blender Agent Kit v0.2.1 — Development Effort & Savings Analysis

## Measurement Disclosure & Methodology

- **What was directly measured:** Custom Python lines of code (LOC) authored, toolkit CLI commands executed, iteration counts, failed attempts, validation errors caught, and wall-clock execution durations for builds and renders.
- **What was NOT directly available:** Token-usage telemetry is not exposed inside this execution environment and is therefore not reported or fabricated. Active cognitive/authoring time is estimated from turn-by-turn implementation records and explicitly labeled as **measured (commands/LOC/iterations)** vs **estimated (active minutes & no-kit baseline)**.
- **Baseline estimation method:** The no-kit baseline estimates what an experienced Blender/Python pipeline engineer would have to author, debug, and run from scratch to achieve the **exact same verification and delivery bar**: headless Blender wrapper + error logging, scene inventory & QA validator (manifold, signed volume, pivot tolerance, LOD budgets, required hierarchy/parent pairs), 16-bit PNG reader/writer + unpremultiplied RGBA channel packer with Lanczos resampling, hierarchy-safe Unity Y-up static FBX prebake (`C·R·C⁻¹` frames + `C·R` directional sockets + scene restoration), Blender fresh-import round-trip verifier + binary FBX embedded-image scanner, automated Cycles orthographic/LOD/range/collision-wireframe review renderer, and contact-sheet composition.
- **Formula:**
  $$\text{Estimated effort saved (\%)} = \frac{\text{Estimated baseline effort} - \text{Actual effort with kit}}{\text{Estimated baseline effort}} \times 100$$

---

## Measured Trial Activity Inventory

| Metric | SupplyCrate | Sci-Fi Kit | Setup / Shared | Total |
| --- | ---: | ---: | ---: | ---: |
| Custom Python helper scripts written | 3 (`generate_pbr_atlas.py`, `build_supplycrate.py`, `compose_showcase.py`) | 3 (`generate_scifi_textures.py`, `build_scifi_kit.py`, `compose_scifi_showcase.py`) | 0 | **6 scripts** |
| Custom JSON specs/profiles written | 2 (`supplycrate.profile.json`, `bundle-spec.json`) | 2 (`scifikit.profile.json`, `bundle-spec.json`) | 0 | **4 configs** |
| Toolkit CLI commands executed | 11 (`inspect`, `qa` ×4, `pack`, `bundle` ×2, `review` ×2, `review_compose`) | 7 (`qa` ×2, `inspect`, `pack` ×2, `bundle`, `review`) | 6 (`install`, `doctor` ×2, `run_tests` ×3) | **24 commands** |
| Meaningful authoring iterations | 3 (initial → root+pivot QA fix → stencil UV + framing fix) | 2 (initial build → `required_parent_pairs` profile fix) | 2 (Blender container path → `$HOME/opt`) | **7 iterations** |
| Validation failures caught | 2 real asset bugs (`pivot_rule` root + 2.5 mm Y-offset) + 1 profile schema error | 1 profile format crash (`required_parent_pairs`) | 1 Blender discovery error | **5 catches** |

---

## Stage-by-Stage Effort Comparison (Active Engineering Minutes — Estimated Ranges)

| Stage | Actual effort with kit (est. active min) | Estimated without kit (est. active min) | Estimated savings | Confidence | Notes |
| --- | --- | --- | --- | --- | --- |
| **Setup / onboarding** | 12 min (incl. Blender 5.2.4 download, container `.so` workaround, reading skill docs/schemas) | 8 min (Blender 5.2.4 download only) | **-50%** (+4 min overhead) | High | Learning CLI flags (no subcommand `--help`) & profile schema added modest one-time onboarding overhead. |
| **Geometry authoring** | 45 min (SupplyCrate: 18 min; Sci-Fi 6 modules + 21-instance corridor: 27 min) | 45 min | **0%** (neutral) | High | Geometry is 100% custom `bmesh` authoring in both cases; skill docs give good conventions but no mesh generators. |
| **UV / baking** | 25 min (2048² crate atlas + 2048² trim sheet + 1024² emissive + UV1 Smart Project) | 28 min | **~11%** (3 min) | Medium | `blender-uv-baking` guardrails saved trial-and-error on 16-bit OpenGL normal conventions, but texture generation remained custom. |
| **Texture packing** | 4 min (3 `run.py pack` calls + validation) | 35–45 min (custom 8/16-bit PNG codec, unpremultiplied RGBA, `1-roughness`, Lanczos, normal-Y check) | **~89–91%** | High | Major direct win: zero custom packing code required. |
| **LOD / collision** | 16 min (parametric LODs + convex hulls authored in builder scripts) | 18 min | **~11%** (2 min) | Medium | Kit validates monotonicity & naming, but authoring LODs/colliders is still custom. |
| **QA** | 8 min (profile JSON authoring + debugging `required_parent_pairs` + fixing 2 real caught bugs) | 55–75 min (writing manifold, signed-volume, pivot, LOD monotonicity, material budget, required-node/parent-pair checks) | **~85–89%** | High | Caught 2 real SupplyCrate bugs automatically that would have escaped manual checks. |
| **Review rendering** | 10 min (configuring presets + custom interior corridor hero & catalog renders) | 45–60 min (camera framing math, auto-scaled lights, per-LOD visibility toggles, range matrix, collision wireframe overlay shader) | **~78–83%** | High | `run.py review` automated 17 SupplyCrate renders + 9 Bulkhead renders cleanly. |
| **Contact-sheet creation** | 22 min (testing `review_compose.py`, hitting 10px font/16-bit/alpha limits, writing 2 custom Pillow compositors) | 20 min (writing 2 custom Pillow compositors directly) | **-10%** (+2 min overhead) | High | Testing and working around `review_compose.py`'s limitations added slight net overhead. |
| **Export and verification** | 6 min (2 `bundle-spec.json` files + 2 `run.py bundle` runs across 10 FBX files) | 75–100 min (Unity Y-up `C·R·C⁻¹` / `C·R` prebake, depth-2 local matrix reconstruction, scene restore, fresh-import round-trip verifier, binary PNG/JPEG scanner) | **~92–94%** | High | Largest single engineering win of the entire toolkit. |
| **Total pipeline (Combined)** | **148 min** (2.47 hrs) | **329–399 min** (5.48–6.65 hrs) | **55% – 63%** (midpoint **~59%**) | Medium-High | Positive overall savings driven overwhelmingly by pipeline automation (`pack`, `qa`, `review`, `bundle` + round-trip). |

---

## Required Breakdown of Effort Savings

### 1. Pipeline-Only Work (Setup + Packing + QA + Review Rendering + Contact Sheets + Export/Verification)
- **Actual with kit:** `12 + 4 + 8 + 10 + 22 + 6 = 62 min`
- **Estimated without kit:** `8 + (35..45) + (55..75) + (45..60) + 20 + (75..100) = 238 – 308 min`
- **Estimated effort saved (%):**
  - Low bound: `(238 - 62) / 238 × 100 = 73.9%`
  - High bound: `(308 - 62) / 308 × 100 = 79.9%`
  - **Range: 74% – 80% (Confidence: High)**

### 2. Complete SupplyCrate Production (Allocated Share of Setup + Full Asset & Pipeline)
- **Actual with kit:** `6 (setup) + 18 (geo) + 12 (UV/tex) + 2 (pack) + 7 (LOD/col) + 4 (QA) + 4 (review) + 12 (sheets) + 3 (export) = 68 min`
- **Estimated without kit:** `4 + 18 + 14 + (20..25) + 8 + (30..40) + (25..35) + 10 + (30..40) = 159 – 194 min`
- **Estimated effort saved (%):**
  - Low bound: `(159 - 68) / 159 × 100 = 57.2%`
  - High bound: `(194 - 68) / 194 × 100 = 64.9%`
  - **Range: 57% – 65% (Confidence: Medium-High)**

### 3. Complete Sci-Fi Kit Production (Allocated Share of Setup + Full 6-Module Kit, Assembly & Pipeline)
- **Actual with kit:** `6 (setup) + 27 (geo/assembly) + 13 (UV/tex) + 2 (pack) + 9 (LOD/col) + 4 (QA) + 6 (review) + 10 (sheets) + 3 (export) = 80 min`
- **Estimated without kit:** `4 + 27 + 14 + (15..20) + 10 + (25..35) + (20..25) + 10 + (45..60) = 170 – 205 min`
- **Estimated effort saved (%):**
  - Low bound: `(170 - 80) / 170 × 100 = 52.9%`
  - High bound: `(205 - 80) / 205 × 100 = 61.0%`
  - **Range: 53% – 61% (Confidence: Medium-High)**

### 4. Combined End-to-End Effort (Both Demos + Setup)
- **Actual with kit:** `148 min`
- **Estimated without kit:** `329 – 399 min`
- **Estimated effort saved (%):**
  - Low bound: `(329 - 148) / 329 × 100 = 55.0%`
  - High bound: `(399 - 148) / 399 × 100 = 62.9%`
  - **Range: 55% – 63% (Confidence: Medium-High)**

---

## Summary Impact Metrics

- **Custom boilerplate lines avoided (estimated):** **~1,400 – 1,900 LOC** (headless Blender runner & JSON transport ~180 LOC; scene inspector & QA engine ~450 LOC; 16-bit PNG & channel packer ~280 LOC; Unity Y-up hierarchy prebake + FBX exporter + fresh-import round-trip verifier ~450 LOC; Cycles review camera/lighting/collision-overlay renderer ~300 LOC).
- **Validation failures caught:** **2 real asset defects** (unrooted SupplyCrate scene; 2.5 mm Y-center pivot offset from asymmetric hardware) + **2 configuration/schema errors**.
- **Custom helper scripts still required:** **6 Python scripts** (2 procedural PBR texture generators, 2 procedural Blender geometry/scene builders, 2 Pillow showcase contact-sheet compositors).
- **Most valuable toolkit capability:** **`run.py bundle` (Unity Y-up static hierarchy/socket prebake + automated Blender fresh-import round-trip verification)** closely followed by **`run.py qa`** and **`run.py pack`**.
- **Least useful / highest-friction capability:** **`tools/review_compose.py`** (tiny 10px bitmap default font, no headers, no 16-bit/alpha handling forced complete replacement with custom Pillow compositors) and **`run.py <subcommand> --help`** (hides subcommand flags).
