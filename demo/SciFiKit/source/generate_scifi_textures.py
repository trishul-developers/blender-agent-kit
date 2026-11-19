#!/usr/bin/env python3
"""Deterministic procedural PBR trim-sheet + emissive texture generator for SciFiKit (Independent Trial).

Produces two material raw PBR sets:
  1. raw_textures/trim_sheet/ (2048x2048):
       base_color.png, metallic.png, roughness.png, ao.png, normal.png (16-bit OpenGL +Y)
     5 horizontal trim bands (V in [0, 1], where V=0 is bottom, V=1 is top; y=0 is top = V=1):
       - Band 4 (V: 0.78..1.00, y: 0..22%):     Light ceramic-composite upper hull panels
       - Band 3 (V: 0.62..0.78, y: 22..38%):    Hazard chevron caution strip + sector stencil
       - Band 2 (V: 0.44..0.62, y: 38..56%):    Industrial ribbed grating / conduit vents
       - Band 1 (V: 0.22..0.44, y: 56..78%):    Brushed titanium-slate structural armor
       - Band 0 (V: 0.00..0.22, y: 78..100%):   Heavy dark gunmetal deck plating + diamond tread
  2. raw_textures/emissive/ (1024x1024):
       base_color.png, metallic.png, roughness.png, ao.png, normal.png (16-bit), emission.png
     3 horizontal zones (V):
       - Top    (V: 0.66..1.00): Cool cyan LED strip & light bar
       - Middle (V: 0.33..0.66): Warm amber status beacon / warning indicator
       - Bottom (V: 0.00..0.33): Dark cyan diagnostic console telemetry display
"""
from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _value_noise(h: int, w: int, gh: int, gw: int, rng: np.random.Generator) -> np.ndarray:
    grid = rng.random((gh, gw), dtype=np.float32)
    y = np.linspace(0, gh, h, endpoint=False, dtype=np.float32)
    x = np.linspace(0, gw, w, endpoint=False, dtype=np.float32)
    y0 = np.floor(y).astype(np.int32) % gh
    x0 = np.floor(x).astype(np.int32) % gw
    y1 = (y0 + 1) % gh
    x1 = (x0 + 1) % gw
    fy = y - np.floor(y)
    fx = x - np.floor(x)
    fy = fy * fy * (3.0 - 2.0 * fy)
    fx = fx * fx * (3.0 - 2.0 * fx)
    top = grid[y0[:, None], x0[None, :]] * (1.0 - fx[None, :]) + grid[y0[:, None], x1[None, :]] * fx[None, :]
    bot = grid[y1[:, None], x0[None, :]] * (1.0 - fx[None, :]) + grid[y1[:, None], x1[None, :]] * fx[None, :]
    return top * (1.0 - fy[:, None]) + bot * fy[:, None]


def fbm(h: int, w: int, octaves: list[tuple[int, int, float]], rng: np.random.Generator) -> np.ndarray:
    acc = np.zeros((h, w), dtype=np.float32)
    tw = 0.0
    for gh, gw, wt in octaves:
        acc += _value_noise(h, w, gh, gw, rng) * wt
        tw += wt
    return acc / max(tw, 1e-6)


def write_png_16bit_rgb(path: Path, arr_01: np.ndarray) -> None:
    arr16 = np.clip(np.round(arr_01 * 65535.0), 0, 65535).astype(">u2")
    h, w, c = arr16.shape
    assert c == 3
    raw = b"".join(b"\x00" + arr16[y].tobytes() for y in range(h))
    comp = zlib.compress(raw, level=6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def height_to_normal_opengl(height: np.ndarray, strength: float = 3.8) -> np.ndarray:
    hp = np.pad(height, 1, mode="edge")
    dx = ((hp[0:-2, 2:] + 2.0 * hp[1:-1, 2:] + hp[2:, 2:]) - (hp[0:-2, 0:-2] + 2.0 * hp[1:-1, 0:-2] + hp[2:, 0:-2])) * 0.25
    dy_v = ((hp[0:-2, 0:-2] + 2.0 * hp[0:-2, 1:-1] + hp[0:-2, 2:]) - (hp[2:, 0:-2] + 2.0 * hp[2:, 1:-1] + hp[2:, 2:])) * 0.25
    nx = -dx * strength
    ny = -dy_v * strength
    nz = np.ones_like(height, dtype=np.float32)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz + 1e-8)
    return np.clip(np.stack([nx * inv * 0.5 + 0.5, ny * inv * 0.5 + 0.5, nz * inv * 0.5 + 0.5], axis=-1), 0.0, 1.0)


def generate_trim_sheet(out_dir: Path, size: int = 2048, seed: int = 101) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    base = np.zeros((size, size, 3), dtype=np.float32)
    metallic = np.zeros((size, size), dtype=np.float32)
    roughness = np.full((size, size), 0.5, dtype=np.float32)
    ao = np.ones((size, size), dtype=np.float32)
    height = np.full((size, size), 0.5, dtype=np.float32)

    # Pixel row ranges (y=0 is top = V=1.0)
    y_b4 = (0, int(size * 0.22))            # V: 0.78..1.00 Light ceramic-composite cladding
    y_b3 = (y_b4[1], int(size * 0.38))      # V: 0.62..0.78 Hazard caution strip
    y_b2 = (y_b3[1], int(size * 0.56))      # V: 0.44..0.62 Ribbed grating / vents
    y_b1 = (y_b2[1], int(size * 0.78))      # V: 0.22..0.44 Brushed titanium-slate armor
    y_b0 = (y_b1[1], size)                  # V: 0.00..0.22 Heavy dark gunmetal deck tread

    def band_grid(y0: int, y1: int):
        bh = y1 - y0
        yy, xx = np.mgrid[0:bh, 0:size].astype(np.float32)
        return bh, xx / size, yy / bh

    # --- Band 4: Clean industrial ceramic-grey upper hull cladding with panel seams & bolts ---
    bh, u, v = band_grid(*y_b4)
    n4 = fbm(bh, size, [(8, 32, 0.5), (24, 96, 0.35), (64, 256, 0.15)], rng)
    panel_u = (u * 4.0) % 1.0
    seam_u = np.clip(np.minimum(panel_u, 1.0 - panel_u) / 0.015, 0.0, 1.0)
    seam_v = np.clip(np.minimum(v, 1.0 - v) / 0.04, 0.0, 1.0)
    seam = np.minimum(seam_u, seam_v)
    col4 = np.array([0.58, 0.62, 0.67], dtype=np.float32)[None, None, :] * (0.90 + 0.16 * n4[:, :, None])
    col4 *= (0.45 + 0.55 * seam[:, :, None])
    base[y_b4[0]:y_b4[1]] = col4
    metallic[y_b4[0]:y_b4[1]] = 0.25 + 0.15 * n4
    roughness[y_b4[0]:y_b4[1]] = np.clip(0.36 + 0.18 * (1.0 - n4), 0.22, 0.70)
    ao[y_b4[0]:y_b4[1]] = 0.45 + 0.55 * seam
    height[y_b4[0]:y_b4[1]] = 0.30 + 0.50 * seam + 0.08 * n4

    # --- Band 3: Industrial yellow/black hazard caution chevron trim ---
    bh, u, v = band_grid(*y_b3)
    n3 = fbm(bh, size, [(12, 48, 0.5), (36, 144, 0.5)], rng)
    chevron = ((u * 24.0 + v * 1.6) % 1.0) < 0.5
    border_v = (v > 0.10) & (v < 0.90)
    yellow = np.array([0.84, 0.62, 0.10], dtype=np.float32)
    charcoal = np.array([0.10, 0.11, 0.13], dtype=np.float32)
    steel_edge = np.array([0.32, 0.35, 0.39], dtype=np.float32)
    c3 = np.where(chevron[:, :, None], yellow, charcoal)
    c3 = np.where(border_v[:, :, None], c3, steel_edge)
    # Scuff wear
    wear3 = np.clip((n3 - 0.66) * 4.0, 0.0, 0.55)
    c3 = c3 * (1.0 - wear3[:, :, None]) + np.array([0.48, 0.50, 0.53], dtype=np.float32) * wear3[:, :, None]
    base[y_b3[0]:y_b3[1]] = c3
    metallic[y_b3[0]:y_b3[1]] = np.where(border_v, 0.18 + 0.65 * wear3, 0.80)
    roughness[y_b3[0]:y_b3[1]] = np.clip(0.45 + 0.20 * (1.0 - n3) - 0.20 * wear3, 0.20, 0.80)
    ao[y_b3[0]:y_b3[1]] = np.where(border_v, 0.88, 0.68)
    height[y_b3[0]:y_b3[1]] = np.where(border_v, 0.55 + 0.05 * n3, 0.38)

    # --- Band 2: Ribbed industrial vents / conduit grating ---
    bh, u, v = band_grid(*y_b2)
    n2 = fbm(bh, size, [(16, 64, 0.6), (48, 192, 0.4)], rng)
    ribs = np.sin(v * 18.0 * np.pi) * 0.5 + 0.5
    ribs = np.clip((ribs - 0.25) * 2.2, 0.0, 1.0)
    cross_bar = np.clip(np.minimum((u * 8.0) % 1.0, 1.0 - (u * 8.0) % 1.0) / 0.06, 0.0, 1.0)
    rib_h = np.maximum(ribs, 1.0 - cross_bar)
    col2 = (np.array([0.12, 0.14, 0.16], dtype=np.float32) * (1.0 - rib_h[:, :, None])
            + np.array([0.40, 0.44, 0.48], dtype=np.float32) * rib_h[:, :, None]) * (0.88 + 0.24 * n2[:, :, None])
    base[y_b2[0]:y_b2[1]] = col2
    metallic[y_b2[0]:y_b2[1]] = 0.60 + 0.30 * rib_h
    roughness[y_b2[0]:y_b2[1]] = np.clip(0.55 - 0.22 * rib_h + 0.12 * n2, 0.22, 0.82)
    ao[y_b2[0]:y_b2[1]] = 0.25 + 0.75 * rib_h
    height[y_b2[0]:y_b2[1]] = 0.12 + 0.78 * rib_h

    # --- Band 1: Brushed titanium-slate structural armor ---
    bh, u, v = band_grid(*y_b1)
    brushed = fbm(bh, size, [(8, 128, 0.5), (16, 256, 0.35), (32, 512, 0.15)], rng)
    grime1 = fbm(bh, size, [(6, 18, 0.5), (18, 54, 0.5)], rng)
    pu = (u * 6.0) % 1.0
    pv = (v * 2.0) % 1.0
    su = np.clip(np.minimum(pu, 1.0 - pu) / 0.018, 0.0, 1.0)
    sv = np.clip(np.minimum(pv, 1.0 - pv) / 0.035, 0.0, 1.0)
    s1 = np.minimum(su, sv)
    edge_wear = np.clip(1.0 - s1, 0.0, 1.0) * 0.4
    col1 = np.array([0.24, 0.28, 0.33], dtype=np.float32)[None, None, :] * (0.82 + 0.32 * brushed[:, :, None])
    col1 *= (0.80 + 0.20 * grime1[:, :, None])
    col1 = col1 * (0.55 + 0.45 * s1[:, :, None]) + np.array([0.55, 0.58, 0.62], dtype=np.float32) * (edge_wear[:, :, None] * 0.35)
    base[y_b1[0]:y_b1[1]] = col1
    metallic[y_b1[0]:y_b1[1]] = np.clip(0.76 + 0.18 * brushed, 0.45, 0.96)
    roughness[y_b1[0]:y_b1[1]] = np.clip(0.32 + 0.22 * (1.0 - grime1) - 0.10 * edge_wear, 0.16, 0.72)
    ao[y_b1[0]:y_b1[1]] = 0.38 + 0.62 * s1
    height[y_b1[0]:y_b1[1]] = 0.24 + 0.58 * s1 + 0.08 * brushed

    # --- Band 0: Heavy dark gunmetal deck plating with diamond-plate tread ---
    bh, u, v = band_grid(*y_b0)
    n0 = fbm(bh, size, [(8, 32, 0.5), (24, 96, 0.5)], rng)
    du = (u * 32.0) % 1.0 - 0.5
    dv = (v * 8.0) % 1.0 - 0.5
    diamond = np.clip(1.0 - (np.abs(du) + np.abs(dv)) / 0.32, 0.0, 1.0)
    col0 = np.array([0.14, 0.16, 0.19], dtype=np.float32)[None, None, :] * (0.80 + 0.35 * n0[:, :, None])
    col0 += np.array([0.14, 0.15, 0.17], dtype=np.float32) * diamond[:, :, None]
    base[y_b0[0]:y_b0[1]] = np.clip(col0, 0.03, 0.95)
    metallic[y_b0[0]:y_b0[1]] = np.clip(0.68 + 0.25 * diamond, 0.40, 0.95)
    roughness[y_b0[0]:y_b0[1]] = np.clip(0.52 - 0.20 * diamond + 0.14 * (1.0 - n0), 0.20, 0.84)
    ao[y_b0[0]:y_b0[1]] = 0.62 + 0.38 * diamond
    height[y_b0[0]:y_b0[1]] = 0.30 + 0.55 * diamond + 0.06 * n0

    normal = height_to_normal_opengl(height, strength=3.6)

    Image.fromarray(np.clip(np.round(base * 255.0), 0, 255).astype(np.uint8), mode="RGB").save(out_dir / "base_color.png")
    Image.fromarray(np.clip(np.round(metallic * 255.0), 0, 255).astype(np.uint8), mode="L").save(out_dir / "metallic.png")
    Image.fromarray(np.clip(np.round(roughness * 255.0), 0, 255).astype(np.uint8), mode="L").save(out_dir / "roughness.png")
    Image.fromarray(np.clip(np.round(ao * 255.0), 0, 255).astype(np.uint8), mode="L").save(out_dir / "ao.png")
    write_png_16bit_rgb(out_dir / "normal.png", normal)

    return {
        "resolution": [size, size],
        "seed": seed,
        "normal_bit_depth": 16,
        "normal_convention": "opengl",
    }


def generate_emissive_trim(out_dir: Path, size: int = 1024, seed: int = 202) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    base = np.zeros((size, size, 3), dtype=np.float32)
    emission = np.zeros((size, size, 3), dtype=np.float32)
    metallic = np.full((size, size), 0.12, dtype=np.float32)
    roughness = np.full((size, size), 0.16, dtype=np.float32)
    ao = np.ones((size, size), dtype=np.float32)
    height = np.full((size, size), 0.5, dtype=np.float32)

    t1 = size // 3
    t2 = (2 * size) // 3

    # Top third (V: 0.66..1.00): Cool cyan LED light bar with subtle segmented diffuser
    yy, xx = np.mgrid[0:t1, 0:size].astype(np.float32)
    v = yy / t1
    u = xx / size
    glow_v = np.exp(-((v - 0.5) / 0.34) ** 2)
    seg = 0.86 + 0.14 * (np.sin(u * 24.0 * np.pi) * 0.5 + 0.5)
    cyan = np.array([0.28, 0.88, 1.00], dtype=np.float32) * (glow_v * seg)[:, :, None]
    base[:t1] = np.clip(cyan * 0.8 + 0.12, 0.0, 1.0)
    emission[:t1] = np.clip(cyan, 0.0, 1.0)

    # Middle third (V: 0.33..0.66): Warm amber beacon / bulkhead alert strip
    bh = t2 - t1
    yy, xx = np.mgrid[0:bh, 0:size].astype(np.float32)
    v = yy / bh
    u = xx / size
    glow_v = np.exp(-((v - 0.5) / 0.32) ** 2)
    pulse = 0.78 + 0.22 * (np.cos(u * 12.0 * np.pi) * 0.5 + 0.5)
    amber = np.array([1.00, 0.58, 0.12], dtype=np.float32) * (glow_v * pulse)[:, :, None]
    base[t1:t2] = np.clip(amber * 0.85 + 0.08, 0.0, 1.0)
    emission[t1:t2] = np.clip(amber, 0.0, 1.0)

    # Bottom third (V: 0.00..0.33): Diagnostic telemetry console screen
    bh = size - t2
    scr = Image.new("RGB", (size, bh), (8, 22, 32))
    draw = ImageDraw.Draw(scr)
    # Subtle grid
    for gx in range(0, size, 32):
        draw.line([(gx, 0), (gx, bh)], fill=(14, 48, 64), width=1)
    for gy in range(0, bh, 32):
        draw.line([(0, gy), (size, gy)], fill=(14, 48, 64), width=1)
    # Telemetry bars & frame
    draw.rectangle([20, 20, size - 20, bh - 20], outline=(48, 210, 240), width=4)
    for i in range(10):
        bx = 60 + i * 88
        bar_h = int(45 + rng.integers(30, bh - 120))
        col = (60, 230, 255) if i < 7 else (255, 165, 40)
        draw.rectangle([bx, bh - 45 - bar_h, bx + 52, bh - 45], fill=col)
    font = ImageFont.load_default()
    for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if Path(fp).is_file():
            font = ImageFont.truetype(fp, 28)
            break
    draw.text((48, 36), "HELIOS CONDUIT  //  ATMOS: 101.3 kPa  //  SEAL: LOCKED", fill=(110, 240, 255), font=font)
    scr_arr = np.asarray(scr, dtype=np.float32) / 255.0
    base[t2:] = scr_arr
    emission[t2:] = scr_arr

    normal = height_to_normal_opengl(height, strength=1.0)
    Image.fromarray(np.clip(np.round(base * 255.0), 0, 255).astype(np.uint8), mode="RGB").save(out_dir / "base_color.png")
    Image.fromarray(np.clip(np.round(emission * 255.0), 0, 255).astype(np.uint8), mode="RGB").save(out_dir / "emission.png")
    Image.fromarray(np.clip(np.round(metallic * 255.0), 0, 255).astype(np.uint8), mode="L").save(out_dir / "metallic.png")
    Image.fromarray(np.clip(np.round(roughness * 255.0), 0, 255).astype(np.uint8), mode="L").save(out_dir / "roughness.png")
    Image.fromarray(np.clip(np.round(ao * 255.0), 0, 255).astype(np.uint8), mode="L").save(out_dir / "ao.png")
    write_png_16bit_rgb(out_dir / "normal.png", normal)

    return {"resolution": [size, size], "seed": seed, "normal_bit_depth": 16}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    m1 = generate_trim_sheet(args.out / "trim_sheet", size=2048, seed=101)
    m2 = generate_emissive_trim(args.out / "emissive", size=1024, seed=202)
    meta = {"trim_sheet": m1, "emissive": m2}
    (args.out / "textures_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
