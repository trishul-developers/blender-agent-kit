"""CLI help must not require launching Blender or importing bpy."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.cli_help import render_subcommand_help
from shared.command_registry import COMMANDS, SUBCOMMAND_TO_MODULE

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "skills/core/blender-core/scripts/run.py"


class SubcommandHelpTests(unittest.TestCase):
    def test_every_subcommand_has_real_flags(self):
        for command, module in SUBCOMMAND_TO_MODULE.items():
            with self.subTest(command=command):
                output = render_subcommand_help(ROOT, command, module, mode=COMMANDS[command]["mode"])
                self.assertIn(command, output)
                self.assertIn("Host options:", output)
                if command == "qa":
                    self.assertIn("--asset-class", output)
                if command == "pack":
                    self.assertIn("--detect-normal-y", output)
                if command == "review":
                    self.assertIn("--preset", output)
                    self.assertIn("--style", output)
                if command == "deliver":
                    self.assertIn("--review-style", output)
                    self.assertIn("--asset-class", output)
                    self.assertIn("Execution mode: host", output)

    def test_host_help_does_not_start_blender(self):
        spec = importlib.util.spec_from_file_location("bak_help_entry", ENTRY)
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with patch("shared.runner.run_blender_module", side_effect=AssertionError("Blender must not run")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = entry.main(["qa", "--help"])
            self.assertEqual(result, 0)
            self.assertIn("--asset-class", out.getvalue())
            self.assertIn("--project-profile", out.getvalue())


if __name__ == "__main__":
    unittest.main()
