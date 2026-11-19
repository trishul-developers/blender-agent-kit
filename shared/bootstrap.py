"""Blender-side bootstrap shim: injects kit root into sys.path and dispatches --module."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import traceback
from pathlib import Path


def _parse_after_double_dash(argv: list[str]) -> list[str]:
    if "--" in argv:
        return argv[argv.index("--") + 1:]
    return argv[1:]


def _write_result(result_json: str | None, payload: dict) -> None:
    text = json.dumps(payload, indent=2)
    if result_json:
        out = Path(result_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        # Single-line fallback marker when --result-json is omitted
        print("@@JSON@@" + json.dumps(payload))


def main(argv: list[str] | None = None) -> int:
    args_list = _parse_after_double_dash(argv if argv is not None else sys.argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--kit-root", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--result-json", default=None)
    known, remainder = parser.parse_known_args(args_list)

    kit_root = str(Path(known.kit_root).resolve())
    if kit_root not in sys.path:
        sys.path.insert(0, kit_root)
    os.environ["BLENDER_AGENT_KIT_ROOT"] = kit_root

    try:
        mod = importlib.import_module(known.module)
        if hasattr(mod, "cli_main"):
            result = mod.cli_main(remainder)
        elif hasattr(mod, "run"):
            result = mod.run()
        else:
            raise AttributeError(f"Module {known.module} defines neither cli_main(argv) nor run()")

        if not isinstance(result, dict):
            result = {"status": "ok", "result": result}
        result.setdefault("status", "ok")
        _write_result(known.result_json, result)
        return 0 if result.get("status") == "ok" else 1
    except Exception as exc:  # noqa: BLE001
        err_payload = {
            "status": "error",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        _write_result(known.result_json, err_payload)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
