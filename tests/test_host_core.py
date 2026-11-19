"""Tier 1 host-side unit tests (no Blender required): schemas, installer, PNG encoder, RNA translator."""
from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import numpy as np

from shared.channel_pack import encode_png, pack_map, parse_channel_expr, write_packed_profile
from shared.exporter import translate_fbx_kwargs, translate_gltf_kwargs
from shared.paths import resolve_kit_root, write_pointer_manifest
from shared.runner import build_blender_command
from shared.target_loader import list_targets, load_target, validate_target_dict
from tools.install import install_skills
from tools.validate_skills import validate_repo

KIT_ROOT = Path(__file__).resolve().parent.parent


def _decode_png_raw(png_bytes: bytes) -> tuple[int, int, int, int, bytes]:
    """Minimal stdlib PNG reader to verify bit depth, color type, and exact unpremultiplied bytes."""
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    width = height = bit_depth = color_type = 0
    idat_parts: list[bytes] = []
    while pos < len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        ctype = png_bytes[pos + 4:pos + 8]
        data = png_bytes[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat_parts.append(data)
    raw = zlib.decompress(b"".join(idat_parts))
    return width, height, bit_depth, color_type, raw


class TestRepoSpecsAndSchemas(unittest.TestCase):
    def test_validate_repo_passes(self) -> None:
        errs = validate_repo(KIT_ROOT)
        self.assertEqual(errs, [], f"Repo validation errors: {errs}")

    def test_unity_target_loads_and_validates(self) -> None:
        targets = list_targets(KIT_ROOT)
        self.assertIn("unity", targets)
        cfg, profile, folder = load_target("unity", kit_root=KIT_ROOT)
        self.assertEqual(profile, "urp")
        self.assertEqual(folder.name, "blender-target-unity")
        self.assertEqual(cfg["export"]["apply_scalings"], "FBX_SCALE_ALL")
        self.assertTrue(cfg["export"]["use_triangles"])
        self.assertTrue(cfg["export"]["use_tspace"])
        self.assertFalse(cfg["export"]["bake_anim_use_all_actions"])
        self.assertTrue(cfg["export"]["bake_anim_use_nla_strips"])

    def test_reject_duplicate_anim_export_flags(self) -> None:
        cfg, _, _ = load_target("unity", kit_root=KIT_ROOT)
        bad = json.loads(json.dumps(cfg))
        bad["export"]["bake_anim_use_all_actions"] = True
        bad["export"]["bake_anim_use_nla_strips"] = True
        errs = validate_target_dict(bad, folder_name="blender-target-unity")
        self.assertTrue(any("duplicate clips" in e for e in errs))


class TestChannelPackAndPngEncoder(unittest.TestCase):
    def test_allowlisted_grammar_blocks_eval_injection(self) -> None:
        self.assertEqual(parse_channel_expr("1-roughness"), (True, "roughness", None))
        self.assertEqual(parse_channel_expr("base_color.r"), (False, "base_color", 0))
        with self.assertRaises(ValueError):
            parse_channel_expr("__import__('os').system('echo pwn')")

    def test_unpremultiplied_rgba_preserves_metallic_when_alpha_zero(self) -> None:
        """Critical URP test: (metallic=1.0, roughness=1.0) -> A=0 must NOT zero out RGB!"""
        raw = {
            "metallic": np.ones((4, 4), dtype=np.float32),
            "roughness": np.ones((4, 4), dtype=np.float32),
        }
        packed = pack_map(["metallic", "metallic", "metallic", "1-roughness"], raw, (4, 4))
        png_bytes = encode_png(packed, bit_depth=8)
        w, h, depth, ctype, scanlines = _decode_png_raw(png_bytes)
        self.assertEqual((w, h, depth, ctype), (4, 4, 8, 6))
        # First scanline: filter byte 0 + pixel 0 RGBA = (255, 255, 255, 0)
        self.assertEqual(list(scanlines[1:5]), [255, 255, 255, 0])

    def test_16bit_normal_png_and_directx_y_flip(self) -> None:
        raw = {"normal": np.full((2, 2, 3), [0.5, 0.25, 1.0], dtype=np.float32)}
        packed_dx = pack_map(["normal.r", "normal.g", "normal.b"], raw, (2, 2), normal_convention="directx")
        self.assertAlmostEqual(float(packed_dx[0, 0, 1]), 0.75, places=5)
        png_bytes = encode_png(packed_dx, bit_depth=16)
        w, h, depth, ctype, _ = _decode_png_raw(png_bytes)
        self.assertEqual((w, h, depth, ctype), (2, 2, 16, 2))

    def test_multi_material_texture_naming_no_collision(self) -> None:
        cfg, _, _ = load_target("unity", kit_root=KIT_ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            m1 = write_packed_profile(cfg, "urp", "crate01", "Mat_Steel", {}, (4, 4), out)
            m2 = write_packed_profile(cfg, "urp", "crate01", "Mat_Wood", {}, (4, 4), out)
            paths1 = {x["path"] for x in m1}
            paths2 = {x["path"] for x in m2}
            self.assertTrue(paths1.isdisjoint(paths2))
            self.assertTrue(all((out / p).is_file() for p in paths1 | paths2))


class TestExporterRnaAndRunner(unittest.TestCase):
    def test_fbx_and_gltf_rna_translation(self) -> None:
        cfg, _, _ = load_target("unity", kit_root=KIT_ROOT)
        fbx_static = translate_fbx_kwargs(cfg["export"], "out.fbx", is_rigged=False)
        self.assertEqual(fbx_static["apply_scale_options"], "FBX_SCALE_ALL")
        self.assertTrue(fbx_static["bake_space_transform"])
        self.assertTrue(fbx_static["use_triangles"])
        self.assertTrue(fbx_static["use_tspace"])
        self.assertEqual(fbx_static["object_types"], {"MESH", "EMPTY", "ARMATURE"})

        fbx_rigged = translate_fbx_kwargs(cfg["export"], "rig.fbx", is_rigged=True)
        self.assertFalse(fbx_rigged["bake_space_transform"])

        glb = translate_gltf_kwargs(cfg["export"], "out.glb")
        self.assertEqual(glb["export_format"], "GLB")
        self.assertTrue(glb["export_yup"])

    def test_blender_cli_strict_flag_ordering(self) -> None:
        cmd = build_blender_command(
            blender_exe="/usr/bin/blender",
            kit_root=KIT_ROOT,
            module_name="shared.exporter",
            module_args=["--target", "unity"],
            result_json=Path("/tmp/res.json"),
            blend_file="/tmp/a.blend",
            addons=["rigify"],
        )
        self.assertEqual(cmd[1], "-b")
        self.assertLess(cmd.index("--factory-startup"), cmd.index("--addons"))
        self.assertLess(cmd.index("--python-exit-code"), cmd.index("-P"))
        self.assertLess(cmd.index("-P"), cmd.index("--"))


class TestUnifiedInstaller(unittest.TestCase):
    def test_install_symlink_and_copy_modes(self) -> None:
        for copy_mode in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                proj = Path(tmp) / "game_repo"
                manifest = Path(tmp) / "cfg" / "manifest.json"
                res = install_skills(
                    agent="all",
                    targets=["unity"],
                    project_dir=proj,
                    copy_mode=copy_mode,
                    kit_root=KIT_ROOT,
                    manifest_path=manifest,
                )
                self.assertEqual(res["status"], "ok")
                self.assertTrue((proj / ".agents" / "skills" / "blender-core" / "SKILL.md").is_file())
                self.assertTrue((proj / ".agents" / "skills" / "blender-target-unity" / "SKILL.md").is_file())
                self.assertTrue((proj / ".claude" / "skills" / "blender-target-unity" / "target.json").is_file())
                self.assertTrue(manifest.is_file())
                self.assertEqual(resolve_kit_root(manifest_path=manifest), KIT_ROOT.resolve())


if __name__ == "__main__":
    unittest.main()
