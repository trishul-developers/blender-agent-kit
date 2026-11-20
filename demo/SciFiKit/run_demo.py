#!/usr/bin/env python3
"""Canonical reproducible Helios Conduit Sci-Fi demo entrypoint."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEMO_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parents[1]
SOURCE = DEMO_DIR / "source"
RUN_PY = REPO_ROOT / "skills/core/blender-core/scripts/run.py"

FULL_SHOWCASE = [
    "01_hero_assembly.webp",
    "02_technical_multiview.webp",
    "03_lod_comparison.webp",
    "04_collision_hierarchy_sockets.webp",
    "05_textures_materials.webp",
]


def _blender(explicit: str | None) -> str:
    candidate = explicit or os.environ.get("BLENDER_EXECUTABLE") or shutil.which("blender")
    if not candidate:
        raise FileNotFoundError("Blender not found; pass --blender or set BLENDER_EXECUTABLE")
    path = Path(candidate).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Blender executable not found: {path}")
    return str(path)


def _run(name: str, command: list[str], steps: list[dict]) -> None:
    start = time.perf_counter()
    print(f"[{name}] {' '.join(command)}", flush=True)
    proc = subprocess.run(command, cwd=str(REPO_ROOT), check=False)
    elapsed = round((time.perf_counter() - start) * 1000.0, 3)
    steps.append({"name": name, "returncode": proc.returncode, "duration_ms": elapsed})
    if proc.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {proc.returncode}")


def _safe_clean(out: Path) -> None:
    protected = {REPO_ROOT.resolve(), DEMO_DIR.resolve(), (REPO_ROOT / "demo").resolve()}
    if out.resolve() in protected:
        raise ValueError(f"Refusing to clean protected path: {out}")
    if out.exists():
        shutil.rmtree(out)


def main() -> int:
    p = argparse.ArgumentParser(description="Rebuild the canonical Helios Conduit demo from source.")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "build/canonical-demos/SciFiKit")
    p.add_argument("--blender", default=None)
    p.add_argument("--mode", choices=["smoke", "full"], default="full")
    p.add_argument("--device", choices=["auto", "gpu", "cpu"], default="cpu")
    p.add_argument("--clean", action="store_true")
    args = p.parse_args()

    out = args.out.expanduser().resolve()
    if args.clean:
        _safe_clean(out)
    for sub in ("raw_textures", "scenes", "evidence", "packed_textures", "exports", "renders", "showcase"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    blender = _blender(args.blender)
    py = sys.executable
    steps: list[dict] = []
    total_start = time.perf_counter()

    _run("generate_textures", [
        py, str(SOURCE / "generate_scifi_textures.py"),
        "--out", str(out / "raw_textures"),
    ], steps)

    if args.mode == "smoke":
        _run("build_bulkhead", [
            blender, "--factory-startup", "-b", "--python-exit-code", "1",
            "-P", str(REPO_ROOT / "tools/ci_build_scifi_bulkhead.py"), "--",
            "--raw-textures", str(out / "raw_textures"),
            "--out-blend", str(out / "scenes/SF_Bulkhead_Arch.blend"),
        ], steps)
    else:
        _run("build_full_kit", [
            blender, "--factory-startup", "-b", "--python-exit-code", "1",
            "-P", str(SOURCE / "build_scifi_kit.py"), "--",
            "--raw-textures", str(out / "raw_textures"),
            "--out-dir", str(out),
        ], steps)

    inspect_blend = (
        out / "scenes/SF_Bulkhead_Arch.blend"
        if args.mode == "smoke"
        else out / "scenes/SciFi_Corridor_Assembly.blend"
    )
    _run("inspect", [
        py, str(RUN_PY), "inspect",
        "--blend", str(inspect_blend),
        "--target", "unity",
        "--project-profile", str(SOURCE / "scifikit.profile.json"),
        "--result-json", str(out / "evidence/inspect.json"),
    ], steps)

    _run("qa", [
        py, str(RUN_PY), "qa",
        "--blend", str(out / "scenes/SF_Bulkhead_Arch.blend"),
        "--target", "unity",
        "--project-profile", str(SOURCE / "scifikit.profile.json"),
        "--asset-class", "modular_bulkhead",
        "--result-json", str(out / "evidence/qa_bulkhead.json"),
    ], steps)
    _run("pack_trim", [
        py, str(RUN_PY), "pack",
        "--target", "unity", "--profile", "urp", "--asset-id", "SciFiKit",
        "--material", "M_SciFi_TrimSheet",
        "--input-dir", str(out / "raw_textures/trim_sheet"),
        "--size", "2048", "--detect-normal-y",
        "--out", str(out / "packed_textures"),
        "--result-json", str(out / "evidence/pack_trim_sheet.json"),
    ], steps)
    _run("pack_emissive", [
        py, str(RUN_PY), "pack",
        "--target", "unity", "--profile", "urp", "--asset-id", "SciFiKit",
        "--material", "M_SciFi_Emissive",
        "--input-dir", str(out / "raw_textures/emissive"),
        "--size", "1024", "--detect-normal-y",
        "--out", str(out / "packed_textures"),
        "--result-json", str(out / "evidence/pack_emissive.json"),
    ], steps)

    if args.mode == "smoke":
        _run("deliver", [
            py, str(RUN_PY), "deliver",
            "--blend", str(out / "scenes/SF_Bulkhead_Arch.blend"),
            "--target", "unity",
            "--project-profile", str(SOURCE / "scifikit.profile.json"),
            "--asset-class", "modular_bulkhead", "--profile", "urp",
            "--asset-id", "SciFiKit",
            "--bundle-spec", str(SOURCE / "bundle-spec.json"),
            "--review-style", "technical", "--device", args.device,
            "--out", str(out / "delivery"),
            "--result-json", str(out / "evidence/deliver.json"),
        ], steps)
    else:
        _run("bundle", [
            py, str(RUN_PY), "bundle",
            "--blend", str(out / "scenes/SF_Bulkhead_Arch.blend"),
            "--spec", str(SOURCE / "bundle-spec.json"),
            "--target", "unity", "--profile", "urp",
            "--out", str(out / "exports"),
            "--result-json", str(out / "evidence/bundle_bulkhead.json"),
        ], steps)
        _run("review_bulkhead", [
            py, str(RUN_PY), "review",
            "--blend", str(out / "scenes/SF_Bulkhead_Arch.blend"),
            "--target", "unity",
            "--project-profile", str(SOURCE / "scifikit.profile.json"),
            "--preset", "bulkhead_lods", "--style", "technical",
            "--samples", "14", "--device", args.device,
            "--out", str(out / "renders/bulkhead_review"),
            "--result-json", str(out / "evidence/review_bulkhead.json"),
        ], steps)
        _run("compose_showcase", [
            py, str(SOURCE / "compose_scifi_showcase.py"), "--scifi-dir", str(out),
        ], steps)
        for name in FULL_SHOWCASE:
            path = out / "showcase" / name
            if not path.is_file() or path.stat().st_size < 1000:
                raise RuntimeError(f"Expected showcase artifact missing/empty: {path}")

    summary = {
        "status": "ok",
        "demo": "SciFiKit",
        "mode": args.mode,
        "output": str(out),
        "blender": blender,
        "duration_ms": round((time.perf_counter() - total_start) * 1000.0, 3),
        "steps": steps,
    }
    (out / "evidence/run_demo.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
