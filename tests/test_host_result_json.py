"""Public --result-json belongs to run.py, never Blender's bootstrap transport."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared import runner

ROOT = Path(__file__).resolve().parents[1]
RUN_PATH = ROOT / "skills/core/blender-core/scripts/run.py"


def load_entrypoint():
    spec = importlib.util.spec_from_file_location("bak_host_entrypoint", RUN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResultJsonOwnershipTests(unittest.TestCase):
    def test_public_result_json_for_every_operational_subcommand(self):
        entry = load_entrypoint()
        for command in ("inspect", "qa", "pack", "export", "bundle", "review"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                dest = Path(directory) / "nested" / "result.json"
                stream = io.StringIO()
                with patch.object(runner, "run_blender_module", return_value={"status": "ok", "command": command}) as invoke:
                    with contextlib.redirect_stdout(stream):
                        rc = entry.main([command, "--result-json", str(dest), "--example", "value"])
                self.assertEqual(rc, 0)
                self.assertEqual(json.loads(dest.read_text(encoding="utf-8")), {"status": "ok", "command": command})
                self.assertEqual(json.loads(stream.getvalue()), {"status": "ok", "command": command})
                self.assertEqual(invoke.call_args.kwargs["module_args"], ["--example", "value"])

    def test_public_result_json_on_failure(self):
        entry = load_entrypoint()
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "failed.json"
            with patch.object(runner, "run_blender_module", return_value={"status": "error", "error": "failed"}):
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = entry.main(["pack", "--result-json=" + str(dest)])
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads(dest.read_text())["status"], "error")

    def test_duplicate_public_option_rejected(self):
        entry = load_entrypoint()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as context:
                entry.main(["pack", "--result-json", "one.json", "--result-json", "two.json"])
        self.assertEqual(context.exception.code, 2)

    def test_runner_rejects_bootstrap_result_override(self):
        for flag in ("--result-json", "--result-json=/tmp/other.json"):
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(ValueError, "owned by the host"):
                    runner.run_blender_module("shared.channel_pack", module_args=[flag], kit_root=ROOT)

    def test_internal_file_is_once_in_bootstrap_command(self):
        command = runner.build_blender_command(
            "blender", ROOT, "shared.channel_pack", ["--target", "unity"], Path("temporary.json")
        )
        self.assertEqual(command.count("--result-json"), 1)
        self.assertEqual(command[-2:], ["--target", "unity"])


if __name__ == "__main__":
    unittest.main()
