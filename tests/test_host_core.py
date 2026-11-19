"""Tier 1 host-side tests for contracts, profiles, packing, hashing, and installers."""
from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import numpy as np

from shared.bundle_exporter import validate_bundle_spec
from shared.channel_pack import (
    cli_main as channel_pack_cli_main,
    detect_normal_y_convention,
    encode_png,
    lanczos_resample,
    pack_map,
    parse_channel_expr,
    required_raw_map_names,
    write_packed_profile,
)
from shared.exporter import compute_build_hash, translate_fbx_kwargs, translate_gltf_kwargs
from shared.paths import resolve_kit_root
from shared.profile_loader import load_profiled_target, load_project_profile
from shared.runner import build_blender_command
from shared.target_loader import list_targets, load_target, validate_target_dict
from tools.install import install_skills
from tools.validate_skills import validate_json_instance, validate_repo

KIT_ROOT = Path(__file__).resolve().parent.parent


def _decode_png_raw(png_bytes: bytes) -> tuple[int, int, int, int, bytes]:
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
    return width, height, bit_depth, color_type, zlib.decompress(b"".join(idat_parts))


class TestRepoSpecsAndSchemas(unittest.TestCase):
    def test_validate_repo_passes(self) -> None:
        self.assertEqual(validate_repo(KIT_ROOT), [])

    def test_unity_target_uses_hierarchy_safe_static_fbx(self) -> None:
        self.assertIn("unity", list_targets(KIT_ROOT))
        cfg, profile, folder = load_target("unity", kit_root=KIT_ROOT)
        self.assertEqual(profile, "urp")
        self.assertEqual(folder.name, "blender-target-unity")
        self.assertTrue(cfg["export"]["prebake_yup_hierarchy"])
        self.assertFalse(cfg["export"]["use_space_transform"])
        self.assertFalse(cfg["export"]["apply_transform_static"])
        self.assertFalse(cfg["export"]["strip_lod_suffix_on_export"])
        self.assertEqual(cfg["export"]["strip_lod_suffix_pattern"], "_LOD[0-9]+$")

    def test_reject_duplicate_anim_export_flags(self) -> None:
        cfg, _, _ = load_target("unity", kit_root=KIT_ROOT)
        bad = json.loads(json.dumps(cfg))
        bad["export"]["bake_anim_use_all_actions"] = True
        bad["export"]["bake_anim_use_nla_strips"] = True
        self.assertTrue(any("duplicate clips" in e for e in validate_target_dict(bad)))

    def test_full_json_schema_rejects_usd_when_available(self) -> None:
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            self.skipTest("jsonschema optional outside strict CI")
        cfg, _, _ = load_target("unity", kit_root=KIT_ROOT)
        bad = json.loads(json.dumps(cfg))
        bad["export"]["format"] = "usd"
        schema = json.loads((KIT_ROOT / "schemas/target.schema.json").read_text(encoding="utf-8"))
        self.assertTrue(validate_json_instance(bad, schema, "bad", require_jsonschema=True))


class TestProjectProfiles(unittest.TestCase):
    def test_tactical_profile_is_optional_overlay(self) -> None:
        base, _, _ = load_target("unity", kit_root=KIT_ROOT)
        profiled, texture_profile, _, data, _ = load_profiled_target(
            "unity",
            texture_profile="tactical_urp",
            project_profile="tactical-vehicle",
            kit_root=KIT_ROOT,
        )
        self.assertEqual(texture_profile, "tactical_urp")
        self.assertEqual(data["name"], "tactical-vehicle")
        self.assertIn("heavy_tracked_vehicle", profiled["qa"]["asset_classes"])
        self.assertIn("Mask", profiled["textures"]["profiles"]["tactical_urp"]["maps"])
        self.assertEqual(profiled["qa"]["common"]["damage_prefix"], "Damage_")
        self.assertNotIn("tactical_urp", base["textures"]["profiles"])

    def test_profile_review_preset(self) -> None:
        data, path = load_project_profile("tactical-vehicle", kit_root=KIT_ROOT)
        self.assertTrue(path.is_file())
        preset = data["review_presets"]["tactical"]
        self.assertEqual(preset["resolution"], [1280, 720])
        self.assertEqual(preset["range_shots_m"], [50, 150, 400])
        self.assertEqual(preset["closeup_distance_m"], 12)


class TestBundleSpec(unittest.TestCase):
    def test_semantic_bundle_selectors_and_zero_root(self) -> None:
        valid = {
            "schema_version": "1.0",
            "asset_id": "x",
            "parts": [{"id": "station", "role": "station", "root": "Station", "zero_root_location": True}],
        }
        self.assertEqual(validate_bundle_spec(valid), [])
        invalid = {
            "schema_version": "1.0",
            "asset_id": "x",
            "parts": [{"id": "body", "collection": "Body", "root": "Root"}],
        }
        self.assertTrue(validate_bundle_spec(invalid))


class TestChannelPackAndPngEncoder(unittest.TestCase):
    def test_pack_subcommand_has_callable_entrypoint(self) -> None:
        self.assertTrue(callable(channel_pack_cli_main))

    def test_allowlisted_grammar_blocks_eval_injection(self) -> None:
        self.assertEqual(parse_channel_expr("1-roughness"), (True, "roughness", None))
        with self.assertRaises(ValueError):
            parse_channel_expr("__import__('os').system('echo pwn')")

    def test_profile_raw_map_discovery(self) -> None:
        cfg, _, _ = load_target("unity", kit_root=KIT_ROOT)
        self.assertTrue({"base_color", "metallic", "roughness", "normal", "ao"}.issubset(
            required_raw_map_names(cfg, "urp")
        ))

    def test_unpremultiplied_rgba_preserves_rgb_at_alpha_zero(self) -> None:
        raw = {"metallic": np.ones((4, 4), dtype=np.float32), "roughness": np.ones((4, 4), dtype=np.float32)}
        packed = pack_map(["metallic", "metallic", "metallic", "1-roughness"], raw, (4, 4))
        w, h, depth, ctype, scanlines = _decode_png_raw(encode_png(packed, bit_depth=8))
        self.assertEqual((w, h, depth, ctype), (4, 4, 8, 6))
        self.assertEqual(list(scanlines[1:5]), [255, 255, 255, 0])

    def test_16bit_normal_png_and_directx_y_flip(self) -> None:
        raw = {"normal": np.full((2, 2, 3), [0.5, 0.25, 1.0], dtype=np.float32)}
        packed = pack_map(["normal.r", "normal.g", "normal.b"], raw, (2, 2), normal_convention="directx")
        self.assertAlmostEqual(float(packed[0, 0, 1]), 0.75, places=5)
        self.assertEqual(_decode_png_raw(encode_png(packed, bit_depth=16))[:4], (2, 2, 16, 2))

    def test_lanczos_resample_normalizes_mixed_source_sizes(self) -> None:
        src = np.linspace(0.0, 1.0, 8 * 6 * 3, dtype=np.float32).reshape((8, 6, 3))
        out = lanczos_resample(src, (4, 4))
        self.assertEqual(out.shape, (4, 4, 3))
        self.assertGreaterEqual(float(out.min()), 0.0)
        self.assertLessEqual(float(out.max()), 1.0)

    def test_normal_y_detection_is_explicitly_heuristic(self) -> None:
        normal = np.full((8, 8, 3), [0.5, 0.8, 1.0], dtype=np.float32)
        report = detect_normal_y_convention(normal)
        self.assertEqual(report["convention"], "opengl")
        self.assertTrue(report["heuristic_only"])

    def test_multi_material_texture_naming_no_collision(self) -> None:
        cfg, _, _ = load_target("unity", kit_root=KIT_ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            p1 = {x["path"] for x in write_packed_profile(cfg, "urp", "crate", "Steel", {}, (4, 4), out)}
            p2 = {x["path"] for x in write_packed_profile(cfg, "urp", "crate", "Wood", {}, (4, 4), out)}
            self.assertTrue(p1.isdisjoint(p2))


class TestExporterRnaRunnerAndHash(unittest.TestCase):
    def test_fbx_and_gltf_translation(self) -> None:
        cfg, _, _ = load_target("unity", kit_root=KIT_ROOT)
        fbx = translate_fbx_kwargs(cfg["export"], "out.fbx", is_rigged=False)
        self.assertEqual(fbx["apply_scale_options"], "FBX_SCALE_ALL")
        self.assertFalse(fbx["use_space_transform"])
        self.assertFalse(fbx["bake_space_transform"])
        self.assertTrue(fbx["use_triangles"])

        synthetic = dict(cfg["export"])
        synthetic["use_space_transform"] = True
        synthetic["apply_transform_rigged"] = True
        rigged = translate_fbx_kwargs(synthetic, "rig.fbx", is_rigged=True)
        self.assertTrue(rigged["use_space_transform"])
        self.assertTrue(rigged["bake_space_transform"])

        glb = translate_gltf_kwargs(cfg["export"], "out.glb")
        self.assertEqual(glb["export_format"], "GLB")

    def test_blender_cli_startup_ordering(self) -> None:
        cmd = build_blender_command(
            "/usr/bin/blender", KIT_ROOT, "shared.exporter", ["--target", "unity"],
            Path("/tmp/res.json"), blend_file="/tmp/a.blend", addons=["rigify"],
        )
        self.assertEqual(cmd[1:3], ["--factory-startup", "-b"])
        self.assertLess(cmd.index("--factory-startup"), cmd.index(str(Path("/tmp/a.blend").resolve())))
        self.assertLess(cmd.index("-P"), cmd.index("--"))

    def test_build_hash_includes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "source.txt"
            p.write_text("same", encoding="utf-8")
            self.assertNotEqual(compute_build_hash([p], {"profile": "a"}), compute_build_hash([p], {"profile": "b"}))


class TestUnifiedInstaller(unittest.TestCase):
    def test_install_core_targets_and_optional_profile_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "game_repo"
            manifest = Path(tmp) / "cfg" / "manifest.json"
            res = install_skills(
                agent="all",
                targets=["unity"],
                packs=["profiles"],
                project_dir=proj,
                copy_mode=True,
                kit_root=KIT_ROOT,
                manifest_path=manifest,
            )
            self.assertEqual(res["status"], "ok")
            self.assertTrue((proj / ".agents/skills/blender-core/SKILL.md").is_file())
            self.assertTrue((proj / ".agents/skills/blender-target-unity/target.json").is_file())
            self.assertTrue((proj / ".agents/skills/blender-profile-tactical-vehicle/profile.json").is_file())
            self.assertEqual(resolve_kit_root(manifest_path=manifest), KIT_ROOT.resolve())


if __name__ == "__main__":
    unittest.main()
