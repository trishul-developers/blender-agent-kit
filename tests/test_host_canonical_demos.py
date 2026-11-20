"""Canonical demo entrypoints stay repo-relative and discoverable without Blender."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CanonicalDemoTests(unittest.TestCase):
    def test_canonical_entrypoints_have_host_help(self):
        for rel in ("demo/SupplyCrate/run_demo.py", "demo/SciFiKit/run_demo.py"):
            with self.subTest(rel=rel):
                proc = subprocess.run(
                    [sys.executable, str(ROOT / rel), "--help"],
                    cwd=str(ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("--mode", proc.stdout)
                self.assertIn("--out", proc.stdout)
                self.assertIn("--blender", proc.stdout)

    def test_entrypoints_do_not_embed_machine_specific_source_paths(self):
        forbidden = (
            "/working_dir/",
            "E:/Projects/",
            "C:\\Users\\",
            "/Users/",
        )
        for rel in ("demo/SupplyCrate/run_demo.py", "demo/SciFiKit/run_demo.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                for marker in forbidden:
                    self.assertNotIn(marker, text)
                self.assertIn("REPO_ROOT", text)
                self.assertIn("build/canonical-demos", text)

    def test_canonical_and_historical_lineage_are_explicit(self):
        canonical = (ROOT / "demo/README.md").read_text(encoding="utf-8")
        historical = (ROOT / "demos/README.md").read_text(encoding="utf-8")
        self.assertIn("canonical reproducible showcase lineage", canonical)
        self.assertIn("run_demo.py", canonical)
        self.assertIn("historical v0.2.1", historical.lower())
        self.assertIn("not the canonical reproduction path", historical.lower())

    def test_scifi_composer_proves_current_emission_map(self):
        text = (ROOT / "demo/SciFiKit/source/compose_scifi_showcase.py").read_text(encoding="utf-8")
        self.assertIn("emission_map_verified", text)
        self.assertIn("_EmissionMap", text)
        self.assertNotIn("lacks _EmissionMap", text)


if __name__ == "__main__":
    unittest.main()
