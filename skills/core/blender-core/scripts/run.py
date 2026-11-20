#!/usr/bin/env python3
"""Single host entrypoint shim for AI agents (Python 3.10+ stdlib only).

Usage:
  python <blender-core>/scripts/run.py capabilities --json
  python <blender-core>/scripts/run.py contract --target unity --asset-class solid_prop
  python <blender-core>/scripts/run.py doctor [--device auto|gpu|cpu]
  python <blender-core>/scripts/run.py qa --blend in.blend --target unity --asset-class solid_prop
  python <blender-core>/scripts/run.py export --blend in.blend --target unity --profile urp --out build/
  python <blender-core>/scripts/run.py review --blend in.blend --device auto --out review/
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path


def _bootstrap_kit_root() -> Path:
    env_val = os.environ.get("BLENDER_AGENT_KIT_ROOT")
    if env_val and (Path(env_val) / "shared").is_dir():
        return Path(env_val).resolve()

    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "shared").is_dir() and (candidate / "schemas").is_dir():
            return candidate

    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    manifest = base / "blender-agent-kit" / "manifest.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        root = Path(data["kit_root"]).resolve()
        if (root / "shared").is_dir():
            return root

    raise FileNotFoundError(
        "Could not resolve blender-agent-kit root. Run tools/install.py or set BLENDER_AGENT_KIT_ROOT."
    )


def main(argv: list[str] | None = None) -> int:
    kit_root = _bootstrap_kit_root()
    if str(kit_root) not in sys.path:
        sys.path.insert(0, str(kit_root))

    from shared.command_registry import COMMANDS, HOST_SUBCOMMANDS, SUBCOMMAND_TO_MODULE
    from shared.runner import run_blender_module, run_host_module

    parser = argparse.ArgumentParser(description="blender-agent-kit single agent entrypoint")
    parser.add_argument("subcommand", choices=sorted(SUBCOMMAND_TO_MODULE.keys()))
    parser.add_argument("--blend", default=None, help="Input .blend file")
    parser.add_argument("--blender", default=None, help="Override Blender executable")
    parser.add_argument("--addons", default=None, help="Comma-separated add-on IDs to enable")
    parser.add_argument("--result-json", default=None, help="Optional public JSON output path (owned by this entrypoint)")
    raw_args = list(argv if argv is not None else sys.argv[1:])
    if raw_args and raw_args[0] in SUBCOMMAND_TO_MODULE and any(
        arg in ("--help", "-h") for arg in raw_args[1:]
    ):
        from shared.cli_help import render_subcommand_help
        command = raw_args[0]
        print(render_subcommand_help(
            kit_root,
            command,
            SUBCOMMAND_TO_MODULE[command],
            mode=COMMANDS[command]["mode"],
        ))
        return 0
    if sum(arg == "--result-json" or arg.startswith("--result-json=") for arg in raw_args) > 1:
        parser.error("--result-json may only be supplied once")
    known, remainder = parser.parse_known_args(raw_args)

    if known.subcommand in HOST_SUBCOMMANDS:
        if known.blend or known.blender or known.addons:
            parser.error(
                f"{known.subcommand} is host-only; --blend/--blender/--addons are not applicable"
            )
        result = run_host_module(
            module_name=SUBCOMMAND_TO_MODULE[known.subcommand],
            module_args=remainder,
        )
    else:
        addon_list = [a.strip() for a in known.addons.split(",") if a.strip()] if known.addons else None
        result = run_blender_module(
            module_name=SUBCOMMAND_TO_MODULE[known.subcommand],
            module_args=remainder,
            blend_file=known.blend,
            addons=addon_list,
            blender_exe=known.blender,
            kit_root=kit_root,
        )
    serialized = json.dumps(result, indent=2)
    if known.result_json:
        destination = Path(known.result_json).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
