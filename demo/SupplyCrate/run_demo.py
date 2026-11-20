#!/usr/bin/env python3
"""Canonical reproducible SupplyCrate demo entrypoint for Blender Agent Kit."""
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
    "01_hero.webp",
    "02_orthographic_multiview.webp",
    "03_lod_comparison.webp",
    "04_lod_distance_grid.webp",
    "05_collision_overlay.webp",
    "06_pbr_to_urp_textures.webp",
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
    p = argparse.ArgumentParser(description="Rebuild the canonical SupplyCrate demo from source.")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "build/canonical-demos/SupplyCrate")
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
        py, str(SOURCE / "generate_pbr_atlas.py"),
        "--out", str(out / "raw_textures"), "--size", "2048", "--seed", "42",
    ], steps)
    _run("build_blend", [
        blender, "--factory-startup", "-b", "--python-exit-code", "1",
        "-P", str(SOURCE / "build_supplycrate.py"), "--",
        "--raw-textures", str(out / "raw_textures"),
        "--out-blend", str(out / "scenes/SupplyCrate.blend"),
    ], steps)
    _run("inspect", [
        py, str(RUN_PY), "inspect",
        "--blend", str(out / "scenes/SupplyCrate.blend"),
        "--target", "unity",
        "--project-profile", str(SOURCE / "supplycrate.profile.json"),
        "--result-json", str(out / "evidence/inspect.json"),
    ], steps)
    _run("qa", [
        py, str(RUN_PY), "qa",
        "--blend", str(out / "scenes/SupplyCrate.blend"),
        "--target", "unity",
        "--project-profile", str(SOURCE / "supplycrate.profile.json"),
        "--asset-class", "solid_prop",
        "--result-json", str(out / "evidence/qa.json"),
    ], steps)
    _run("pack", [
        py, str(RUN_PY), "pack",
        "--target", "unity", "--profile", "urp",
        "--asset-id", "SupplyCrate", "--material", "M_SupplyCrate_Body",
        "--input-dir", str(out / "raw_textures"), "--size", "2048",
        "--detect-normal-y", "--out", str(out / "packed_textures"),
        "--result-json", str(out / "evidence/pack.json"),
    ], steps)

    if args.mode == "smoke":
        _run("deliver", [
            py, str(RUN_PY), "deliver",
            "--blend", str(out / "scenes/SupplyCrate.blend"),
            "--target", "unity",
            "--project-profile", str(SOURCE / "supplycrate.profile.json"),
            "--asset-class", "solid_prop", "--profile", "urp",
            "--asset-id", "SupplyCrate",
            "--bundle-spec", str(SOURCE / "bundle-spec.json"),
            "--review-style", "technical", "--device", args.device,
            "--out", str(out / "delivery"),
            "--result-json", str(out / "evidence/deliver.json"),
        ], steps)
    else:
        _run("bundle", [
            py, str(RUN_PY), "bundle",
            "--blend", str(out / "scenes/SupplyCrate.blend"),
            "--spec", str(SOURCE / "bundle-spec.json"),
            "--target", "unity", "--profile", "urp",
            "--out", str(out / "exports"),
            "--result-json", str(out / "evidence/bundle.json"),
        ], steps)
        _run("review_tiles", [
            py, str(RUN_PY), "review",
            "--blend", str(out / "scenes/SupplyCrate.blend"),
            "--target", "unity",
            "--project-profile", str(SOURCE / "supplycrate.profile.json"),
            "--preset", "showcase_tiles", "--style", "technical",
            "--samples", "14", "--device", args.device,
            "--out", str(out / "renders/tiles"),
            "--result-json", str(out / "evidence/review_tiles.json"),
        ], steps)
        _run("review_hd", [
            py, str(RUN_PY), "review",
            "--blend", str(out / "scenes/SupplyCrate.blend"),
            "--target", "unity",
            "--project-profile", str(SOURCE / "supplycrate.profile.json"),
            "--preset", "hero_hd", "--style", "showcase",
            "--samples", "28", "--device", args.device,
            "--out", str(out / "renders/hd"),
            "--result-json", str(out / "evidence/review_hd.json"),
        ], steps)
        _run("compose_showcase", [
            py, str(SOURCE / "compose_showcase.py"), "--trial-dir", str(out),
        ], steps)
        for name in FULL_SHOWCASE:
            path = out / "showcase" / name
            if not path.is_file() or path.stat().st_size < 1000:
                raise RuntimeError(f"Expected showcase artifact missing/empty: {path}")

    summary = {
        "status": "ok",
        "demo": "SupplyCrate",
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
