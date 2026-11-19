"""Regenerate the SupplyCrate demo end-to-end with Blender Agent Kit."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_KIT = HERE.parents[1]
PROFILE = HERE / "prop-showcase.profile.json"
WORK, BUILD, RAW, RENDERS = HERE / "work", HERE / "build", HERE / "raw", HERE / "renders"
EVIDENCE = HERE / "evidence" / "generated"


def find_blender(explicit: str | None) -> str:
    candidates = [
        explicit,
        os.environ.get("BLENDER"),
        shutil.which("blender"),
        r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" if os.name == "nt" else None,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise SystemExit("Blender not found. Pass --blender <path> or set BLENDER.")


def step(name: str, cmd: list[object], capture: Path | None = None) -> dict | None:
    print(f"[{name}]", flush=True)
    result = subprocess.run([str(v) for v in cmd], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-3000:], result.stderr[-3000:])
        raise SystemExit(f"step {name} failed ({result.returncode})")
    if capture is None:
        return None
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text(result.stdout, encoding="utf-8")
    payload = json.loads(result.stdout[result.stdout.index("{"):])
    print("   status:", payload.get("status"), "passed:", payload.get("passed"))
    return payload


def _portable(value):
    if isinstance(value, dict):
        return {k: _portable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_portable(v) for v in value]
    if isinstance(value, str):
        try:
            path = Path(value)
            if path.is_absolute():
                resolved = path.resolve()
                try:
                    return resolved.relative_to(HERE).as_posix()
                except ValueError:
                    return value
        except (OSError, ValueError):
            pass
    return value


def publish_json(source: Path, destination: Path) -> None:
    data = json.loads(source.read_text(encoding="utf-8"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(_portable(data), indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kit-root", type=Path, default=DEFAULT_KIT)
    parser.add_argument("--blender")
    parser.add_argument("--samples", type=int, default=128)
    ns = parser.parse_args()

    kit = ns.kit_root.resolve()
    run = kit / "skills" / "core" / "blender-core" / "scripts" / "run.py"
    if not run.is_file():
        raise SystemExit(f"Blender Agent Kit entrypoint not found: {run}")
    blender = find_blender(ns.blender)
    for directory in (WORK, BUILD, RAW, RENDERS, EVIDENCE):
        directory.mkdir(parents=True, exist_ok=True)

    def kit_cmd(*args: object) -> list[object]:
        return [sys.executable, run, *args]

    step("textures", [sys.executable, HERE / "gen_textures.py", "--kit-root", kit, "--out", RAW])
    step("build", [blender, "--factory-startup", "-b", "-P", HERE / "build_supplycrate.py", "--", "--raw", RAW, "--out", WORK / "SupplyCrate.blend"])
    step("inspect", kit_cmd("inspect", "--blend", WORK / "SupplyCrate.blend"), WORK / "inspect.json")
    step("qa", kit_cmd("qa", "--blend", WORK / "SupplyCrate.blend", "--target", "unity", "--project-profile", PROFILE, "--asset-class", "lod_prop"), WORK / "qa.json")
    step("pack", kit_cmd("pack", "--target", "unity", "--profile", "urp", "--asset-id", "SupplyCrate", "--material", "Body", "--input-dir", RAW, "--size", "2048", "--detect-normal-y", "--out", BUILD), WORK / "pack.json")
    step("bundle", kit_cmd("bundle", "--blend", WORK / "SupplyCrate.blend", "--spec", HERE / "bundle-spec.json", "--target", "unity", "--project-profile", PROFILE, "--out", BUILD), WORK / "bundle.result.json")
    step("review", kit_cmd("review", "--blend", WORK / "SupplyCrate.blend", "--project-profile", PROFILE, "--preset", "prop", "--device", "auto", "--samples", ns.samples, "--out", RENDERS), WORK / "review.json")

    publish_json(WORK / "qa.json", EVIDENCE / "qa.json")
    publish_json(WORK / "pack.json", EVIDENCE / "pack.json")
    publish_json(BUILD / "SupplyCrate.bundle.manifest.json", EVIDENCE / "SupplyCrate.bundle.manifest.json")
    publish_json(WORK / "review.json", EVIDENCE / "review.json")
    step("showcase", [sys.executable, HERE / "make_sheets.py"])
    print("done")


if __name__ == "__main__":
    main()
