# blender-skills (`blender-agent-kit`)

Headless-first Blender 5.2+ skills and executable pipeline primitives for AI agents and game-asset production.

The repository is intentionally layered:

```text
generic Blender core
        ↓
engine target (Unity today)
        ↓
optional project profile / external profile JSON
        ↓
downstream asset-specific build scripts and game contracts
```

The core is not a tank generator, Unity game framework, or TTE-specific package. It provides reusable execution, inspection, QA, texture packing, export, semantic bundle export, round-trip verification, and review rendering that downstream projects can compose.

## Current status

The v0.2 development branch adds production-pipeline foundations on top of the v0.1 release:

- strict Blender 5.2+ doctor;
- strict JSON Schema checks in CI while runtime remains dependency-light;
- generic scene inventory;
- aggregate LOD/material/ground/hierarchy QA;
- stronger FBX/GLB round-trip checks;
- semantic multi-file bundle export;
- deterministic build hashes that include config/tool identity;
- multiview automatic review renders;
- optional project-profile overlays;
- optional `tactical-vehicle` profile demonstrating reusable requirements distilled from military-asset/TTE production without changing the base Unity target.

## Quick start

```bash
# Install generic core + Unity target
python tools/install.py --agent all --targets unity

# Optional: also install project-profile skills
python tools/install.py --agent all --targets unity --packs profiles

# Verify Blender
python tools/doctor.py --device auto

# Host/schema tests
python tools/run_tests.py --suite host

# Blender tests
python tools/run_tests.py --suite core
python tools/run_tests.py --suite targets
```

## Single agent entrypoint

Agents call one shim rather than assembling Blender flags:

```bash
python skills/core/blender-core/scripts/run.py doctor --device auto

python skills/core/blender-core/scripts/run.py inspect \
  --blend asset.blend

python skills/core/blender-core/scripts/run.py qa \
  --blend asset.blend --target unity --asset-class solid_prop

python skills/core/blender-core/scripts/run.py pack \
  --target unity --profile urp \
  --asset-id Prop01 --material Body --input-dir raw/ --out build/

python skills/core/blender-core/scripts/run.py export \
  --blend asset.blend --target unity --profile urp --out build/

python skills/core/blender-core/scripts/run.py bundle \
  --blend vehicle.blend --spec bundle.json --target unity --out build/

python skills/core/blender-core/scripts/run.py review \
  --blend asset.blend --device auto --out review/
```

## Project profiles

A project profile is an overlay on an engine target. It can add or override texture profiles, QA asset classes, budgets, naming rules, and other downstream conventions without changing the reusable target.

The built-in optional example is:

```text
plugins/profiles/blender-profile-tactical-vehicle/
```

It demonstrates:

- heavy/light tracked-vehicle LOD budgets;
- <= 0.50 LOD reduction ratio;
- ground-contact checks;
- optional turret/gun hierarchy checks;
- BaseColor + Normal + Mask output;
- semantic bundle roles such as chassis, station, collision, wreck, and kit.

Use it explicitly:

```bash
python skills/core/blender-core/scripts/run.py qa \
  --blend vehicle.blend \
  --target unity \
  --project-profile tactical-vehicle \
  --asset-class heavy_tracked_vehicle

python skills/core/blender-core/scripts/run.py pack \
  --target unity \
  --project-profile tactical-vehicle \
  --profile tactical_urp \
  --asset-id Vehicle01 --material Body \
  --input-dir raw/ --out build/
```

Exact game-specific socket inventories, simulation measurements, faction rules, damage contracts, or content IDs should live in the downstream project's own profile JSON.

## Semantic bundle export

Compound assets can be exported through a declarative spec instead of pretending that every mesh is an LOD:

```json
{
  "schema_version": "1.0",
  "asset_id": "Vehicle01",
  "parts": [
    {
      "id": "chassis_lod0",
      "role": "chassis",
      "lod": 0,
      "collection": "Chassis_LOD0",
      "file": "Vehicle01_Chassis_LOD0.fbx"
    },
    {
      "id": "collision",
      "role": "collision",
      "collection": "Collision",
      "file": "Vehicle01_Collision.fbx"
    }
  ]
}
```

Each part is inventoried and fresh-reimported. The bundle manifest records object hierarchy, triangle/material counts, build hash, and round-trip evidence.

## Target plugins

Targets remain engine-level only:

```text
plugins/targets/blender-target-unity/
  target.json
  SKILL.md
  editor/BlenderAssetPostprocessor.cs
```

A new target can be scaffolded with:

```bash
python tools/new_target.py godot --format glb --normal opengl
python tools/new_target.py unreal --format fbx --normal directx
```

Currently implemented export formats are FBX, GLB, and glTF.

## Important implementation boundaries

The pipeline now enforces mesh presence, transforms/scale, manifold/boundary rules, inward normals for closed meshes, UV presence, aggregate LOD triangle/material budgets, monotonic LOD counts, optional LOD reduction ratios, optional required-node/parent relationships, ground contact, bone-weight count, and basic pivot rules.

UV1 **presence** is enforced when requested, but geometric UV1-overlap detection is not yet implemented; QA reports that limitation explicitly. Texel-density measurement and automatic collider construction remain future work.

The Unity postprocessor configures import settings and material textures for standard URP/HDRP profiles. It does **not** currently build complete LODGroups/colliders/prefabs. Projects such as TTE that own their own prefab/material/import pipeline should use the Blender outputs and manifests as evidence rather than installing the generic postprocessor into production.

## Documentation

- [DESIGN.md](DESIGN.md) — architecture, implemented contracts, QA boundaries, and downstream-profile strategy.
- [Unity target](plugins/targets/blender-target-unity/SKILL.md)
- [Semantic bundle skill](skills/core/blender-bundle/SKILL.md)
- [Tactical vehicle profile](plugins/profiles/blender-profile-tactical-vehicle/SKILL.md)

## License

MIT — see [LICENSE](LICENSE).
