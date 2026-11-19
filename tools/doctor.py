#!/usr/bin/env python3
"""Host-side environment doctor: checks Python, kit pointer, Blender 5.2+, add-ons, and GPU/CPU."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from shared.runner import find_blender, run_blender_module  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify blender-agent-kit environment and Blender 5.2+ setup.")
    p.add_argument("--blender", default=None, help="Explicit Blender executable path")
    p.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto")
    p.add_argument("--json", action="store_true", dest="as_json")
    ns = p.parse_args(argv)

    try:
        exe = find_blender(ns.blender)
    except FileNotFoundError as exc:
        out = {"status": "error", "error": str(exc)}
        print(json.dumps(out, indent=2))
        return 1

    res = run_blender_module(
        module_name="tools.doctor_blender",
        module_args=["--device", ns.device],
        blender_exe=exe,
        kit_root=KIT_ROOT,
    )
    res["blender_executable"] = exe
    if ns.as_json:
        print(json.dumps(res, indent=2))
    else:
        print(f"Status: {res.get('status')}")
        print(f"Blender: {exe} ({res.get('blender_version', 'unknown')})")
        print(f"Cycles device: {res.get('cycles_device', 'unknown')}")
        if res.get("addons"):
            print(f"Verified add-ons: {', '.join(res['addons'])}")
        if res.get("error"):
            print(f"Error: {res['error']}")
    return 0 if res.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
