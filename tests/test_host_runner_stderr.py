"""Agent-readable error reports for Blender startup failures."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared import runner

ROOT = Path(__file__).resolve().parents[1]


class RunnerStderrTests(unittest.TestCase):
    def test_nonzero_exit_reports_bounded_stderr_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            response = subprocess.CompletedProcess(
                args=["blender"], returncode=127, stdout="",
                stderr=("other output\n" * 300) + "libblender_cpu_check.so: cannot open shared object file\n",
            )
            with patch.object(runner, "find_blender", return_value="fake-blender"):
                with patch.object(runner.subprocess, "run", return_value=response):
                    result = runner.run_blender_module(
                        "shared.scene_inspector", kit_root=ROOT,
                        log_dir=Path(directory),
                    )
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["returncode"], 127)
            self.assertIn("libblender_cpu_check.so", result["stderr_tail"])
            self.assertLessEqual(len(result["stderr_tail"]), 2000)
            self.assertTrue(Path(result["log_file"]).is_file())


if __name__ == "__main__":
    unittest.main()
