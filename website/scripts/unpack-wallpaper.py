#!/usr/bin/env python3
"""Offline Forgotten Ruins → web asset pipeline (local spike / private bake).

Reads a unpacked Wallpaper Engine workshop tree OR a scene.pkg directory that
already contains .tex files (e.g. /tmp/forgotten-ruins-pkg) and emits:

  website/public/media/ruins/
    scene.gen.json
    base.webp
    waterripplenormal.webp
    masks/*.webp

LEGAL: Do NOT commit raw scene.pkg, .tex, or extracted workshop art to the
public repo. Outputs under public/media/ruins/ are gitignored except README.
Public shipping requires owned / re-authored / explicitly licensed art.

Usage:
  python3 website/scripts/unpack-wallpaper.py \\
    --src /tmp/forgotten-ruins-pkg \\
    --out website/public/media/ruins

Requires: ImageMagick (`magick`). No WASM / no runtime Steam deps.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path


def lz4_decompress(src: bytes, uncompressed_size: int) -> bytes:
    """Minimal LZ4 block decoder (no frame header)."""
    i = 0
    out = bytearray()
    n = len(src)
    while i < n and len(out) < uncompressed_size:
        token = src[i]
        i += 1
        lit_len = token >> 4
        if lit_len == 15:
            while True:
                b = src[i]
                i += 1
                lit_len += b
                if b != 255:
                    break
        out.extend(src[i : i + lit_len])
        i += lit_len
        if i >= n or len(out) >= uncompressed_size:
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0:
            raise ValueError("lz4 offset 0")
        match_len = (token & 0xF) + 4
        if (token & 0xF) == 15:
            while True:
                b = src[i]
                i += 1
                match_len += b
                if b != 255:
                    break
        start = len(out) - offset
        for _ in range(match_len):
            out.append(out[start])
            start += 1
            if len(out) >= uncompressed_size:
                break
    return bytes(out[:uncompressed_size])


def extract_tex(path: Path) -> tuple[str, bytes, tuple[int, int]]:
    """Return (kind, payload, (w,h)) where kind is 'png' or 'rgba'."""
    data = path.read_bytes()
    if not data.startswith(b"TEXV0005\x00"):
        raise ValueError(f"not TEXV0005: {path}")
    texi = data.find(b"TEXI0001\x00")
    if texi < 0:
        raise ValueError(f"missing TEXI: {path}")
    # flags, fmt?, container_w, container_h, width, height, ...
    _flags, _a, _cw, _ch, width, height = struct.unpack_from("<6I", data, texi + 9)
    png = data.find(b"\x89PNG")
    if png >= 0:
        iend = data.find(b"IEND", png)
        if iend < 0:
            raise ValueError(f"truncated PNG: {path}")
        return "png", data[png : iend + 8], (width, height)

    texb = data.find(b"TEXB0003\x00")
    if texb < 0:
        raise ValueError(f"no PNG/TEXB in {path}")
    # version, format(-1=lz4 rgba), ?, w, h, mips, uncompressed
    _ver, fmt, _b, w, h, _mips, unc = struct.unpack_from("<IiIIIII", data, texb + 9)
    off = texb + 9 + 28
    comp_size = struct.unpack_from("<I", data, off)[0]
    payload = data[off + 4 : off + 4 + comp_size]
    if fmt != -1:
        raise ValueError(f"unsupported TEX format {fmt} in {path}")
    rgba = lz4_decompress(payload, unc)
    return "rgba", rgba, (w, h)


def run_magick(args: list[str]) -> None:
    cmd = ["magick", *args]
    subprocess.run(cmd, check=True)


def short_mask_name(tex_path: str) -> str:
    """materials/masks/waterwaves_mask_HASH → waterwaves_mask_HASH.webp"""
    name = Path(tex_path).name
    return f"{name}.webp"


def build_scene_gen(scene: dict, out_rel: str = "/media/ruins") -> dict:
    main = next(o for o in scene["objects"] if o.get("name") == "MAIN" and o.get("effects"))
    passes = []
    for effect in main["effects"]:
        file = effect.get("file", "")
        # WE scene stores one pass worth of constants under passes[0]
        p0 = effect["passes"][0]
        c = dict(p0.get("constantshadervalues") or {})
        textures = p0.get("textures") or []
        mask = None
        for t in textures:
            if t and "mask" in t:
                mask = f"masks/{Path(t).name}.webp"
                break
        if "waterripple" in file:
            passes.append(
                {
                    "type": "waterripple",
                    "mask": mask,
                    "scale": float(c.get("scale", 1)),
                    "ripplestrength": float(c.get("ripplestrength", 0.1)),
                    "scrollspeed": float(c.get("scrollspeed", 0)),
                    "animationspeed": float(c.get("animationspeed", 0.15)),
                    "ratio": float(c.get("ratio", 1)),
                    "scrolldirection": float(c.get("scrolldirection", c.get("direction", 0))),
                }
            )
        elif "waterwaves" in file:
            passes.append(
                {
                    "type": "waterwaves",
                    "mask": mask,
                    "direction": float(c.get("direction", 0)),
                    "scale": float(c.get("scale", 200)),
                    "speed": float(c.get("speed", 5)),
                    "strength": float(c.get("strength", 0.1)),
                    "perspective": float(c.get("perspective", 0)),
                }
            )

    particles = []
    for o in scene["objects"]:
        if not o.get("particle"):
            continue
        ov = o.get("instanceoverride") or {}
        particles.append(
            {
                "name": o.get("name"),
                "preset": o["particle"],
                "origin": [float(x) for x in str(o.get("origin", "0 0 0")).split()],
                "scale": float(str(o.get("scale", "1")).split()[0]),
                "angles_z": float(str(o.get("angles", "0 0 0")).split()[-1]),
                "rate": float(ov.get("rate", 1)),
                "size": float(ov.get("size", 1)) if "size" in ov else None,
                "alpha": float(ov.get("alpha", 1)) if "alpha" in ov else None,
                "color": [float(x) for x in str(ov["colorn"]).split()]
                if "colorn" in ov
                else None,
            }
        )

    return {
        "version": 1,
        "title": "Forgotten Ruins (web spike)",
        "workshopId": "2133182232",
        "size": [3840, 2160],
        "base": f"{out_rel}/base.webp",
        "rippleNormal": f"{out_rel}/waterripplenormal.webp",
        "passes": passes,
        "particles": particles,
        "notes": "Derived textures are local-only; do not commit workshop art.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--src",
        type=Path,
        required=True,
        help="Unpacked workshop dir containing materials/*.tex + scene.json",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "public" / "media" / "ruins",
    )
    ap.add_argument("--base-width", type=int, default=2048)
    ap.add_argument("--mask-width", type=int, default=1024)
    ap.add_argument("--skip-textures", action="store_true", help="Only emit scene.gen.json")
    args = ap.parse_args()

    src: Path = args.src
    out: Path = args.out
    scene_path = src / "scene.json"
    if not scene_path.is_file():
        print(f"missing {scene_path}", file=sys.stderr)
        return 1

    scene = json.loads(scene_path.read_text())
    out.mkdir(parents=True, exist_ok=True)
    (out / "masks").mkdir(exist_ok=True)

    gen = build_scene_gen(scene)
    (out / "scene.gen.json").write_text(json.dumps(gen, indent=2) + "\n")
    print(f"wrote {out / 'scene.gen.json'} ({len(gen['passes'])} passes)")

    if args.skip_textures:
        return 0

    if shutil.which("magick") is None:
        print("ImageMagick `magick` required for texture conversion", file=sys.stderr)
        return 1

    tmp = out / ".tmp"
    tmp.mkdir(exist_ok=True)

    main_tex = src / "materials" / "MAIN.tex"
    kind, payload, wh = extract_tex(main_tex)
    raw = tmp / "MAIN.png"
    if kind == "png":
        raw.write_bytes(payload)
    else:
        raise ValueError("MAIN.tex expected embedded PNG")
    run_magick(
        [
            str(raw),
            "-resize",
            f"{args.base_width}x",
            "-quality",
            "82",
            str(out / "base.webp"),
        ]
    )
    print(f"base.webp from {wh} → width {args.base_width}")

    rip_tex = src / "materials" / "effects" / "waterripplenormal.tex"
    kind, payload, wh = extract_tex(rip_tex)
    if kind != "rgba":
        raise ValueError("waterripplenormal expected lz4 rgba")
    rgba_path = tmp / "ripple.rgba"
    rgba_path.write_bytes(payload)
    run_magick(
        [
            "-size",
            f"{wh[0]}x{wh[1]}",
            "-depth",
            "8",
            f"rgba:{rgba_path}",
            "-quality",
            "90",
            str(out / "waterripplenormal.webp"),
        ]
    )
    print("waterripplenormal.webp")

    mask_dir = src / "materials" / "masks"
    for tex in sorted(mask_dir.glob("*.tex")):
        kind, payload, wh = extract_tex(tex)
        png = tmp / f"{tex.stem}.png"
        if kind == "png":
            png.write_bytes(payload)
        else:
            png_rgba = tmp / f"{tex.stem}.rgba"
            png_rgba.write_bytes(payload)
            run_magick(
                [
                    "-size",
                    f"{wh[0]}x{wh[1]}",
                    "-depth",
                    "8",
                    f"rgba:{png_rgba}",
                    str(png),
                ]
            )
        dest = out / "masks" / f"{tex.stem}.webp"
        run_magick(
            [
                str(png),
                "-resize",
                f"{args.mask_width}x",
                "-colorspace",
                "Gray",
                "-quality",
                "80",
                str(dest),
            ]
        )
        print(f"  {dest.name}")

    shutil.rmtree(tmp, ignore_errors=True)
    # rough size
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"done → {out} ({total / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
