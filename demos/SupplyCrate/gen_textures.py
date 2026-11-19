"""Procedural raw PBR maps for the SupplyCrate demo (host Python + numpy only).

Atlas layout (2048x2048, one material):
  top-left     wood (olive paint over timber)      UV centre (0.25, 0.75)
  top-right    steel (dark steel, rust patches)    UV centre (0.75, 0.75)
  bottom-left  rope (twisted hemp)                 UV centre (0.25, 0.25)
  bottom-right spare / neutral paint               UV centre (0.75, 0.25)
Writes canonical raw maps expected by `run.py pack`: base_color, metallic,
roughness, normal (OpenGL, 16-bit), ao.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def smooth(t):
    return t * t * (t * (t * 6 - 15) + 10)


def value_noise(h, w, cy, cx, rng):
    grid = rng.random((cy + 2, cx + 2)).astype(np.float32)
    ys = np.linspace(0, cy, h, endpoint=False, dtype=np.float32)
    xs = np.linspace(0, cx, w, endpoint=False, dtype=np.float32)
    y0 = ys.astype(int)
    x0 = xs.astype(int)
    fy = smooth(ys - y0)[:, None]
    fx = smooth(xs - x0)[None, :]
    g00 = grid[y0][:, x0]
    g01 = grid[y0][:, x0 + 1]
    g10 = grid[y0 + 1][:, x0]
    g11 = grid[y0 + 1][:, x0 + 1]
    top = g00 * (1 - fx) + g01 * fx
    bot = g10 * (1 - fx) + g11 * fx
    return top * (1 - fy) + bot * fy


def fbm(h, w, cy, cx, rng, octaves=4):
    total = np.zeros((h, w), np.float32)
    amp, norm = 1.0, 0.0
    for _ in range(octaves):
        total += amp * value_noise(h, w, cy, cx, rng)
        norm += amp
        amp *= 0.5
        cy *= 2
        cx *= 2
    return total / norm


def tile_wood(n, rng):
    grain = fbm(n, n, 90, 4, rng, 4)                    # long streaks along U
    fine = fbm(n, n, 380, 14, rng, 3)
    tone = 0.65 + 0.5 * (0.6 * grain + 0.4 * fine)
    timber = np.stack([0.43 * tone, 0.28 * tone, 0.15 * tone], -1)
    rings = 0.5 + 0.5 * np.sin((grain * 40 + np.linspace(0, 6, n)[:, None]) * 3.14)
    timber *= (0.9 + 0.1 * rings)[..., None]
    paint_mask = fbm(n, n, 5, 5, rng, 5)
    wear = fbm(n, n, 22, 22, rng, 4)
    painted = (paint_mask + 0.25 * (wear - 0.5)) > 0.34
    olive = np.array([0.24, 0.27, 0.15], np.float32)
    paint = olive[None, None] * (0.85 + 0.3 * fine)[..., None]
    base = np.where(painted[..., None], paint, timber)
    rough = np.where(painted, 0.62, 0.88).astype(np.float32) + 0.08 * fine
    metal = np.zeros((n, n), np.float32)
    height = 0.55 + 0.25 * grain + 0.1 * fine
    height = np.where(painted, height + 0.12, height)
    ao = 0.82 + 0.18 * fine
    return base, rough, metal, height, ao


def tile_steel(n, rng):
    fine = fbm(n, n, 60, 60, rng, 5)
    rust_mask = fbm(n, n, 7, 7, rng, 5)
    rusty = rust_mask > 0.52
    steel = np.array([0.13, 0.135, 0.145], np.float32)[None, None] * (0.8 + 0.5 * fine)[..., None]
    rust = np.array([0.36, 0.17, 0.07], np.float32)[None, None] * (0.7 + 0.6 * fine)[..., None]
    base = np.where(rusty[..., None], rust, steel)
    rough = np.where(rusty, 0.85, 0.42).astype(np.float32) + 0.1 * fine
    metal = np.where(rusty, 0.25, 0.92).astype(np.float32)
    height = 0.5 + 0.2 * fine - 0.12 * rusty
    ao = 0.85 + 0.15 * fine
    return base, rough, metal, height, ao


def tile_rope(n, rng):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    twist = 0.5 + 0.5 * np.sin((xx * 0.45 + yy * 0.18) * 0.62)
    fibre = fbm(n, n, 220, 220, rng, 3)
    tone = 0.62 + 0.38 * twist - 0.2 * fibre
    base = np.stack([0.64 * tone, 0.51 * tone, 0.30 * tone], -1)
    rough = np.full((n, n), 0.95, np.float32)
    metal = np.zeros((n, n), np.float32)
    height = 0.3 + 0.7 * twist
    ao = 0.55 + 0.45 * twist
    return base, rough, metal, height, ao


def tile_spare(n, rng):
    fine = fbm(n, n, 40, 40, rng, 4)
    olive = np.array([0.25, 0.28, 0.16], np.float32)[None, None] * (0.85 + 0.3 * fine)[..., None]
    return olive, np.full((n, n), 0.7, np.float32), np.zeros((n, n), np.float32), 0.5 + 0.1 * fine, 0.9 + 0.1 * fine


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kit-root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, default=2048)
    p.add_argument("--seed", type=int, default=7)
    ns = p.parse_args()
    sys.path.insert(0, ns.kit_root)
    from shared.channel_pack import encode_png

    n = ns.size // 2
    rng = np.random.default_rng(ns.seed)
    tiles = [tile_wood(n, rng), tile_steel(n, rng), tile_rope(n, rng), tile_spare(n, rng)]
    # row-major quadrants: TL wood, TR steel, BL rope, BR spare (row 0 = top = v 1.0)
    order = [(0, 0), (0, 1), (1, 0), (1, 1)]
    S = ns.size
    base = np.zeros((S, S, 3), np.float32)
    rough = np.zeros((S, S), np.float32)
    metal = np.zeros((S, S), np.float32)
    height = np.zeros((S, S), np.float32)
    ao = np.zeros((S, S), np.float32)
    for (r, c), (b, ro, m, h, a) in zip(order, tiles):
        sl = (slice(r * n, (r + 1) * n), slice(c * n, (c + 1) * n))
        base[sl], rough[sl], metal[sl], height[sl], ao[sl] = b, ro, m, h, a
    gy, gx = np.gradient(height)
    strength = 18.0
    nx, ny, nz = -gx * strength, gy * strength, np.ones_like(gx)   # OpenGL (+Y up; row 0 is top)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack([nx * inv, ny * inv, nz * inv], -1) * 0.5 + 0.5
    out = Path(ns.out)
    out.mkdir(parents=True, exist_ok=True)
    maps = {
        "base_color": (np.clip(base, 0, 1), 8),
        "roughness": (np.clip(rough, 0, 1), 8),
        "metallic": (np.clip(metal, 0, 1), 8),
        "ao": (np.clip(ao, 0, 1), 8),
        "normal": (normal.astype(np.float32), 16),
    }
    for name, (arr, depth) in maps.items():
        (out / f"{name}.png").write_bytes(encode_png(arr, depth))
        print("wrote", out / f"{name}.png")


if __name__ == "__main__":
    main()
