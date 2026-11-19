#!/usr/bin/env python3
"""Headless test runner for Tier 1 (host stdlib), Tier 2 (core bpy), and Tier 3 (target contracts)."""
from __future__ import annotations

import argparse
import subprocess
import sys
import unittest
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from shared.runner import find_blender, run_blender_module  # noqa: E402
from tools.validate_skills import validate_repo  # noqa: E402


def run_host_tests() -> bool:
    errs = validate_repo(KIT_ROOT)
    if errs:
        print("Tier 1 spec/schema validation failed:")
        for e in errs:
            print(f"  - {e}")
        return False
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(KIT_ROOT / "tests"),
        pattern="test_host_*.py",
    )
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    return res.wasSuccessful()


def run_blender_suite(suite_name: str, blender_exe: str | None = None) -> bool:
    exe = find_blender(blender_exe)
    module = "tests.test_bpy_core" if suite_name == "core" else "tests.test_target_contract"
    res = run_blender_module(
        module_name=module,
        blender_exe=exe,
        kit_root=KIT_ROOT,
    )
    print(f"[{suite_name}] status={res.get('status')} details={res}")
    return res.get("status") == "ok"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run blender-agent-kit test suites.")
    p.add_argument("--suite", choices=["host", "core", "targets", "all"], default="host")
    p.add_argument("--blender", default=None)
    ns = p.parse_args(argv)

    ok = True
    if ns.suite in ("host", "all"):
        ok = run_host_tests() and ok
    if ns.suite in ("core", "all"):
        ok = run_blender_suite("core", ns.blender) and ok
    if ns.suite in ("targets", "all"):
        ok = run_blender_suite("targets", ns.blender) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
