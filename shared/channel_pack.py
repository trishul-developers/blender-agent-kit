"""Safe-grammar PBR channel packer with pure-stdlib 8-bit/16-bit unpremultiplied PNG writer.

Avoids bpy.types.Image.save_render() (View Transform corruption) and Image.save()
(bit-depth and alpha-zero RGB premultiplication quirks). Uses only Python stdlib + numpy.
"""
from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path
from typing import Mapping

import numpy as np

# Allowlisted channel expression grammar:
#   <map_name>[.<r|g|b|a>]   or   1-<map_name>[.<r|g|b|a>]
_EXPR_RE = re.compile(r"^(1-)?([a-z][a-z0-9_]*)(?:\.([rgba]))?$")
_CHANNEL_IDX = {"r": 0, "g": 1, "b": 2, "a": 3}

# PNG color types by channel count: 1=Grayscale(0), 3=RGB(2), 4=RGBA(6)
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

    # Automatic DirectX (-Y) normal green-channel flip when target requires DirectX normals
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
    """Encode a float32 [0..1] HxW or HxWxC array into exact unpremultiplied 8/16-bit PNG bytes."""
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
        # PNG stores 16-bit samples in big-endian byte order
        quant = np.rint(arr * 65535.0).astype(">u2")

    row_bytes = quant.reshape(height, -1).view(np.uint8)
    # Prepend filter byte 0 (None) to each scanline
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
    """Pack and write all maps defined by target_cfg['textures']['profiles'][profile_name]."""
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
