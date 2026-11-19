"""Safe PBR channel packing, Lanczos resizing, and normal-Y convention reporting."""
from __future__ import annotations

import argparse
import math
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
    m = _EXPR_RE.match(expr.strip())
    if not m:
        raise ValueError(f"Unsupported channel expression (blocked by allowlist): {expr!r}")
    return bool(m.group(1)), m.group(2), _CHANNEL_IDX[m.group(3)] if m.group(3) else None


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
        chan = np.full(shape_hw, float(fallbacks.get(map_name, 0.0)), dtype=np.float32)

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
    if len(channel_exprs) not in (1, 3, 4):
        raise ValueError(f"PNG packing supports 1, 3, or 4 channels, got {len(channel_exprs)}")
    planes = [
        _extract_channel(expr, raw_maps, shape_hw, fallbacks or {}, normal_convention)
        for expr in channel_exprs
    ]
    return planes[0] if len(planes) == 1 else np.stack(planes, axis=-1)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def encode_png(array_float: np.ndarray, bit_depth: int = 8) -> bytes:
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

    quant = np.rint(arr * (255.0 if bit_depth == 8 else 65535.0))
    quant = quant.astype(np.uint8 if bit_depth == 8 else ">u2")
    row_bytes = quant.reshape(height, -1).view(np.uint8)
    raw_scanlines = np.concatenate(
        [np.zeros((height, 1), dtype=np.uint8), row_bytes], axis=1
    ).tobytes()
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, _PNG_COLOR_TYPE[channels], 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw_scanlines, level=6))
        + _png_chunk(b"IEND", b"")
    )


def _lanczos_kernel(x: np.ndarray, a: float) -> np.ndarray:
    ax = np.abs(x)
    return np.where(ax < a, np.sinc(x) * np.sinc(x / a), 0.0)


def _resample_axis(arr: np.ndarray, dst_size: int, axis: int, a: int = 3, chunk: int = 32) -> np.ndarray:
    src_size = arr.shape[axis]
    if src_size == dst_size:
        return arr.copy()
    scale = src_size / dst_size
    support = a * max(1.0, scale)
    taps = max(2, int(math.ceil(support)) * 2)
    centers = (np.arange(dst_size, dtype=np.float64) + 0.5) * scale - 0.5
    left = np.floor(centers - support + 1.0).astype(np.int64)
    offsets = np.arange(taps, dtype=np.int64)
    indices = left[:, None] + offsets[None, :]
    distances = centers[:, None] - indices
    kernel_x = distances / max(1.0, scale)
    weights = _lanczos_kernel(kernel_x, float(a))
    clipped = np.clip(indices, 0, src_size - 1)
    weights_sum = weights.sum(axis=1, keepdims=True)
    weights = np.divide(weights, weights_sum, out=np.zeros_like(weights), where=np.abs(weights_sum) > 1e-12)

    moved = np.moveaxis(arr, axis, 0)
    rest_shape = moved.shape[1:]
    flat = moved.reshape(src_size, -1)
    out = np.empty((dst_size, flat.shape[1]), dtype=np.float32)
    for start in range(0, dst_size, chunk):
        end = min(dst_size, start + chunk)
        gathered = flat[clipped[start:end], :]
        out[start:end] = np.einsum("kt,ktf->kf", weights[start:end], gathered, optimize=True)
    shaped = out.reshape((dst_size,) + rest_shape)
    return np.moveaxis(shaped, 0, axis)


def lanczos_resample(array: np.ndarray, shape_hw: tuple[int, int], a: int = 3) -> np.ndarray:
    arr = np.asarray(array, dtype=np.float32)
    target_h, target_w = map(int, shape_hw)
    if target_h < 1 or target_w < 1:
        raise ValueError(f"Invalid target size {shape_hw}")
    out = _resample_axis(arr, target_w, axis=1, a=a)
    out = _resample_axis(out, target_h, axis=0, a=a)
    return np.clip(out, 0.0, 1.0)


def detect_normal_y_convention(normal: np.ndarray) -> dict:
    arr = np.asarray(normal, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[2] < 2:
        raise ValueError("normal map must be HxWxC with at least two channels")
    green = np.clip(arr[:, :, 1], 0.0, 1.0)
    mean_g = float(np.mean(green))
    median_g = float(np.median(green))
    bias = mean_g - 0.5
    confidence = min(1.0, abs(bias) * 4.0)
    if abs(bias) < 0.02:
        convention = "ambiguous"
    else:
        convention = "opengl" if bias > 0 else "directx"
    return {
        "convention": convention,
        "heuristic_only": True,
        "mean_green": mean_g,
        "median_green": median_g,
        "confidence": confidence,
        "note": "Tangent-space normal convention cannot be proven from pixels alone; this is a directional-bias heuristic.",
    }


def write_packed_profile(
    target_cfg: dict,
    profile_name: str,
    asset_id: str,
    material_name: str,
    raw_maps: Mapping[str, np.ndarray],
    shape_hw: tuple[int, int],
    out_dir: Path,
) -> list[dict]:
    tex_cfg = target_cfg["textures"]
    profile_cfg = tex_cfg["profiles"][profile_name]
    fallbacks = tex_cfg.get("fallback_constants", {})
    normal_conv = tex_cfg.get("normal_convention", "opengl")
    pattern = target_cfg["naming"]["texture_pattern"]

    written: list[dict] = []
    for map_key, map_spec in profile_cfg["maps"].items():
        if map_spec.get("optional"):
            dependencies = {parse_channel_expr(expr)[1] for expr in map_spec["channels"]}
            if not dependencies.issubset(raw_maps.keys()):
                continue
        packed = pack_map(map_spec["channels"], raw_maps, shape_hw, fallbacks, normal_conv)
        rel_path = pattern.format(asset_id=asset_id, material_name=material_name, map=map_key)
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
            "normal_map": map_spec.get("unity_type") == "NormalMap" or str(map_key).lower() == "normal",
            "max_size": int(max(shape_hw)),
        })
    return written


def required_raw_map_names(target_cfg: dict, profile_name: str) -> set[str]:
    result: set[str] = set()
    for spec in target_cfg["textures"]["profiles"][profile_name]["maps"].values():
        for expr in spec["channels"]:
            _, map_name, _ = parse_channel_expr(expr)
            result.add(map_name)
    return result


def _load_raw_map(path: Path) -> np.ndarray:
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
        return np.flipud(pixels.reshape((height, width, channels)))
    finally:
        bpy.data.images.remove(image)


def cli_main(argv: list[str]) -> dict:
    from shared.profile_loader import load_profiled_target

    p = argparse.ArgumentParser()
    p.add_argument("--target", default="unity")
    p.add_argument("--profile", default=None)
    p.add_argument("--project-profile", default=None)
    p.add_argument("--asset-id", required=True)
    p.add_argument("--material", required=True)
    p.add_argument("--input-dir", required=True)
    p.add_argument("--out", default="build")
    p.add_argument("--size", type=int, default=None, help="Target square size; raw maps are Lanczos-resampled when needed")
    p.add_argument("--detect-normal-y", action="store_true")
    ns = p.parse_args(argv)

    target_cfg, profile_name, _, project_data, _ = load_profiled_target(
        ns.target,
        texture_profile=ns.profile,
        project_profile=ns.project_profile,
    )
    input_dir = Path(ns.input_dir)
    raw_maps: dict[str, np.ndarray] = {}
    shape_hw: tuple[int, int] | None = (ns.size, ns.size) if ns.size else None
    resized_maps: list[dict] = []

    for map_name in sorted(required_raw_map_names(target_cfg, profile_name)):
        candidate = input_dir / f"{map_name}.png"
        if not candidate.is_file():
            continue
        arr = _load_raw_map(candidate)
        original_shape = tuple(arr.shape[:2])
        if ns.size:
            if original_shape != (ns.size, ns.size):
                arr = lanczos_resample(arr, (ns.size, ns.size))
                resized_maps.append({"map": map_name, "from": list(original_shape), "to": [ns.size, ns.size], "filter": "lanczos3"})
        else:
            current_shape = tuple(arr.shape[:2])
            if shape_hw is None:
                shape_hw = current_shape
            elif current_shape != shape_hw:
                raise ValueError(
                    f"Raw map '{candidate}' shape {current_shape} != expected {shape_hw}; use --size to normalize inputs"
                )
        raw_maps[map_name] = arr

    if shape_hw is None:
        raise ValueError("No canonical raw PNGs found; provide --size for fallback-only packing")
    if not raw_maps and ns.size is None:
        raise ValueError("No canonical raw PNGs found")

    normal_report = None
    if ns.detect_normal_y and "normal" in raw_maps:
        normal_report = detect_normal_y_convention(raw_maps["normal"])

    written = write_packed_profile(
        target_cfg, profile_name, ns.asset_id, ns.material,
        raw_maps, shape_hw, Path(ns.out).resolve(),
    )
    return {
        "status": "ok",
        "target": target_cfg["name"],
        "profile": profile_name,
        "project_profile": project_data["name"] if project_data else None,
        "asset_id": ns.asset_id,
        "material": ns.material,
        "raw_maps": sorted(raw_maps),
        "target_size": list(shape_hw),
        "resized_maps": resized_maps,
        "normal_y_detection": normal_report,
        "artifacts": {"textures": written},
    }
