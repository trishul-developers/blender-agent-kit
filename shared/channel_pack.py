"""Safe-grammar PBR channel packer with exact 8/16-bit unpremultiplied PNG output.

The module is usable both as a Python API and through blender-core's `pack`
subcommand. The CLI accepts canonical raw maps named after their logical inputs,
for example base_color.png, metallic.png, roughness.png, normal.png and ao.png.
"""
from __future__ import annotations

import argparse
import re
import struct
import zlib
from pathlib import Path
from typing import Mapping

import numpy as np

_EXPR_RE = re.compile(r"^(1-)?([a-z][a-z0-9_]*)(?:\.([rgba]))?$")
_CHANNEL_IDX = {"r": 0, "g": 1, "b": 2, "a": 3}
_PNG_COLOR_TYPE = {1: 0, 3: 2, 4: 6}


def parse_channel_expr(expr: str) -> tuple[bool, str, int | None]:
    """Parse an allowlisted channel expression without eval()."""
    m = _EXPR_RE.match(expr.strip())
    if not m:
        raise ValueError(f"Unsupported channel expression (blocked by allowlist): {expr!r}")
    invert = bool(m.group(1))
    map_name = m.group(2)
    ch_idx = _CHANNEL_IDX[m.group(3)] if m.group(3) else None
    return invert, map_name, ch_idx


def _extract_channel(
    expr: str,
    raw_maps: Mapping[str, np.ndarray],
    shape_hw: tuple[int, int],
    fallbacks: Mapping[str, float],
    normal_convention: str = "opengl",
) -> np.ndarray:
    invert, map_name, ch_idx = parse_channel_expr(expr)
    if map_name in raw_maps:
        arr = np.asarray(raw_maps[map_name], dtype=np.float32)
        if arr.ndim == 2:
            chan = arr
        elif arr.ndim == 3:
            idx = ch_idx if ch_idx is not None else 0
            if idx >= arr.shape[2]:
                raise ValueError(f"Map '{map_name}' has {arr.shape[2]} channels; requested index {idx}")
            chan = arr[:, :, idx]
        else:
            raise ValueError(f"Map '{map_name}' must be 2D or 3D array, got shape {arr.shape}")
        if chan.shape != shape_hw:
            raise ValueError(f"Map '{map_name}' shape {chan.shape} != expected {shape_hw}")
    else:
        default_val = float(fallbacks.get(map_name, 0.0))
        chan = np.full(shape_hw, default_val, dtype=np.float32)

    if map_name == "normal" and ch_idx == 1 and normal_convention == "directx":
        chan = 1.0 - chan
    if invert:
        chan = 1.0 - chan
    return np.clip(chan, 0.0, 1.0)


def pack_map(
    channel_exprs: list[str],
    raw_maps: Mapping[str, np.ndarray],
    shape_hw: tuple[int, int],
    fallbacks: Mapping[str, float] | None = None,
    normal_convention: str = "opengl",
) -> np.ndarray:
    """Pack 1, 3, or 4 float32 [0..1] channels into a contiguous HxW(xC) array."""
    if len(channel_exprs) not in (1, 3, 4):
        raise ValueError(f"PNG packing supports 1, 3, or 4 channels, got {len(channel_exprs)}")
    fb = fallbacks or {}
    planes = [
        _extract_channel(expr, raw_maps, shape_hw, fb, normal_convention=normal_convention)
        for expr in channel_exprs
    ]
    if len(planes) == 1:
        return planes[0]
    return np.stack(planes, axis=-1)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def encode_png(array_float: np.ndarray, bit_depth: int = 8) -> bytes:
    """Encode a float32 [0..1] HxW or HxWxC array into exact unpremultiplied PNG bytes."""
    if bit_depth not in (8, 16):
        raise ValueError(f"bit_depth must be 8 or 16, got {bit_depth}")
    arr = np.clip(np.asarray(array_float, dtype=np.float32), 0.0, 1.0)
    if arr.ndim == 2:
        height, width = arr.shape
        channels = 1
    elif arr.ndim == 3:
        height, width, channels = arr.shape
    else:
        raise ValueError(f"Expected 2D or 3D image array, got shape {arr.shape}")

    if channels not in _PNG_COLOR_TYPE:
        raise ValueError(f"Unsupported channel count {channels}; must be 1, 3, or 4")

    if bit_depth == 8:
        quant = np.rint(arr * 255.0).astype(np.uint8)
    else:
        quant = np.rint(arr * 65535.0).astype(">u2")

    row_bytes = quant.reshape(height, -1).view(np.uint8)
    filter_col = np.zeros((height, 1), dtype=np.uint8)
    raw_scanlines = np.concatenate([filter_col, row_bytes], axis=1).tobytes()

    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, _PNG_COLOR_TYPE[channels], 0, 0, 0)
    idat = zlib.compress(raw_scanlines, level=6)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def write_packed_profile(
    target_cfg: dict,
    profile_name: str,
    asset_id: str,
    material_name: str,
    raw_maps: Mapping[str, np.ndarray],
    shape_hw: tuple[int, int],
    out_dir: Path,
) -> list[dict]:
    """Pack and write all maps defined by a target texture profile."""
    tex_cfg = target_cfg["textures"]
    profile_cfg = tex_cfg["profiles"][profile_name]
    fallbacks = tex_cfg.get("fallback_constants", {})
    normal_conv = tex_cfg.get("normal_convention", "opengl")
    pattern = target_cfg["naming"]["texture_pattern"]

    written: list[dict] = []
    for map_key, map_spec in profile_cfg["maps"].items():
        packed = pack_map(
            channel_exprs=map_spec["channels"],
            raw_maps=raw_maps,
            shape_hw=shape_hw,
            fallbacks=fallbacks,
            normal_convention=normal_conv,
        )
        rel_path = pattern.format(
            asset_id=asset_id,
            material_name=material_name,
            map=map_key,
        )
        dest = out_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(encode_png(packed, bit_depth=map_spec["bit_depth"]))
        written.append({
            "map_key": map_key,
            "slot": map_spec.get("unity_slot") or map_spec.get("slot") or map_key,
            "material_name": material_name,
            "path": rel_path,
            "srgb": bool(map_spec["srgb"]),
            "bit_depth": int(map_spec["bit_depth"]),
            "normal_map": map_spec.get("unity_type") == "NormalMap" or map_key == "normal",
            "max_size": int(max(shape_hw)),
        })
    return written


def required_raw_map_names(target_cfg: dict, profile_name: str) -> set[str]:
    """Return logical raw-map names referenced by a packed profile."""
    result: set[str] = set()
    for spec in target_cfg["textures"]["profiles"][profile_name]["maps"].values():
        for expr in spec["channels"]:
            _, map_name, _ = parse_channel_expr(expr)
            result.add(map_name)
    return result


def _load_raw_map(path: Path) -> np.ndarray:
    """Read image pixels inside Blender without applying display/view transforms."""
    import bpy

    image = bpy.data.images.load(str(path.resolve()), check_existing=False)
    try:
        try:
            image.colorspace_settings.name = "Non-Color"
        except TypeError:
            pass
        width, height = map(int, image.size)
        channels = int(image.channels)
        pixels = np.empty(width * height * channels, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        # Blender exposes rows bottom-up; canonical arrays and our PNG writer are top-down.
        return np.flipud(pixels.reshape((height, width, channels)))
    finally:
        bpy.data.images.remove(image)


def cli_main(argv: list[str]) -> dict:
    """Pack canonical raw PNG maps using a target's declarative texture profile."""
    from shared.target_loader import load_target

    p = argparse.ArgumentParser()
    p.add_argument("--target", default="unity")
    p.add_argument("--profile", default=None)
    p.add_argument("--asset-id", required=True)
    p.add_argument("--material", required=True)
    p.add_argument("--input-dir", required=True)
    p.add_argument("--out", default="build")
    p.add_argument("--size", type=int, default=None, help="Fallback square size when every input uses constants")
    ns = p.parse_args(argv)

    target_cfg, profile_name, _ = load_target(ns.target, ns.profile)
    input_dir = Path(ns.input_dir)
    raw_maps: dict[str, np.ndarray] = {}
    shape_hw: tuple[int, int] | None = None

    for map_name in sorted(required_raw_map_names(target_cfg, profile_name)):
        candidate = input_dir / f"{map_name}.png"
        if not candidate.is_file():
            continue
        arr = _load_raw_map(candidate)
        current_shape = tuple(arr.shape[:2])
        if shape_hw is None:
            shape_hw = current_shape
        elif current_shape != shape_hw:
            raise ValueError(
                f"Raw map '{candidate}' shape {current_shape} does not match expected {shape_hw}"
            )
        raw_maps[map_name] = arr

    if shape_hw is None:
        if ns.size is None or ns.size < 1:
            raise ValueError("No canonical raw PNGs found; provide --size when packing fallback constants only")
        shape_hw = (ns.size, ns.size)

    written = write_packed_profile(
        target_cfg=target_cfg,
        profile_name=profile_name,
        asset_id=ns.asset_id,
        material_name=ns.material,
        raw_maps=raw_maps,
        shape_hw=shape_hw,
        out_dir=Path(ns.out).resolve(),
    )
    return {
        "status": "ok",
        "target": target_cfg["name"],
        "profile": profile_name,
        "raw_maps": sorted(raw_maps.keys()),
        "artifacts": {"textures": written},
    }
