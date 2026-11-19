# blender-skills (`blender-agent-kit`)

Engine-agnostic, headless-first **Blender 5.2 LTS+** AI agent skill set with multi-agent support (`agentskills.io`), automated CI tests, and a **data-driven 2-file target-engine plugin architecture** (**Unity** shipped first with URP/HDRP + 2-stage C# `AssetPostprocessor`; **Godot**, **Unreal**, and **Web** drop in later with zero Python boilerplate).

## Quick Start

```bash
# 1. Install skills into ~/.agents/skills/ and ~/.claude/skills/
python3 tools/install.py --agent all --targets unity

# Or install into a specific game repository
python3 tools/install.py --project /path/to/your-game --targets unity

# 2. Verify Blender 5.2 LTS, add-ons, and Cycles GPU/CPU
python3 tools/doctor.py --device auto

# 3. Run Tier 1 host/schema/PNG/installer tests (no Blender required)
python3 tools/run_tests.py --suite host
```

## Single Agent Entrypoint

AI agents invoke one thin stdlib shim rather than assembling raw `blender -b ...` flags:

```bash
python3 skills/core/blender-core/scripts/run.py doctor --device auto
python3 skills/core/blender-core/scripts/run.py qa --blend prop.blend --target unity --asset-class solid_prop
python3 skills/core/blender-core/scripts/run.py export --blend prop.blend --target unity --profile urp --out build/
python3 skills/core/blender-core/scripts/run.py review --blend prop.blend --device auto --out review/
```

## Adding a New Target Engine (Zero Python Boilerplate)

```bash
python3 tools/new_target.py godot --format glb --normal opengl
python3 tools/new_target.py unreal --format fbx --normal directx
```

Each target plugin lives at `plugins/targets/blender-target-<engine>/` with only `target.json` + `SKILL.md` and is automatically picked up by Tier 3 round-trip CI tests.

## Documentation

- [`DESIGN.md`](DESIGN.md) — Full v1.2 architecture, `target.json` & `asset.manifest.json` schemas, PBR guardrails, and 2-stage Unity C# postprocessor contract.
- [`plugins/targets/blender-target-unity/editor/BlenderAssetPostprocessor.cs`](plugins/targets/blender-target-unity/editor/BlenderAssetPostprocessor.cs) — Drop into `Assets/Editor/` in Unity.

## License

MIT — see [`LICENSE`](LICENSE).
