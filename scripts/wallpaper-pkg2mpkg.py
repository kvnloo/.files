#!/usr/bin/env python3
"""Convert a desktop Wallpaper Engine scene folder (scene.pkg + project.json + preview) into an
Android Wallpaper Engine .mpkg.

Mobile format, learned from .mpkg files the Android app exported:
  - header magic PKGM0016 instead of PKGV00xx; project.json and preview.* live inside the package
  - textures carry one mip level, exact image dimensions, raw pixels LZ4-compressed
    (TEXB0003 image block: count=1, FreeImage format=-1, mips=1, w, h, lz4=1, raw_size, packed_size)
  - shaders must compile as GLSL ES (no int*vec arithmetic, no variables named `sample`)
usage: pkg2mpkg.py WORKSHOP_DIR OUT.mpkg [--max-side N]
"""
import io
import re
import struct
import sys
from pathlib import Path

import lz4.block
from PIL import Image


def read_pkg(path):
    b = Path(path).read_bytes()
    o = 0

    def u32():
        nonlocal o
        v = struct.unpack_from("<I", b, o)[0]
        o += 4
        return v

    def s():
        nonlocal o
        n = u32()
        v = b[o:o + n].decode()
        o += n
        return v

    magic = s()
    entries = [(s(), u32(), u32()) for _ in range(u32())]
    return magic, {n: b[o + off:o + off + sz] for n, off, sz in entries}


def write_pkg(path, files, magic="PKGM0016"):
    head = io.BytesIO()

    def s(x):
        x = x.encode()
        head.write(struct.pack("<I", len(x)) + x)

    s(magic)
    head.write(struct.pack("<I", len(files)))
    off = 0
    for name, data in files.items():
        s(name)
        head.write(struct.pack("<II", off, len(data)))
        off += len(data)
    Path(path).write_bytes(head.getvalue() + b"".join(files.values()))



def convert_tex(t, max_side):
    """Return a mobile texture (RGBA8888, one mip, LZ4) for a desktop .tex."""
    assert t[:8] == b"TEXV0005" and t[9:17] == b"TEXI0001", t[:18]
    fmt, flags, _tw, _th, iw, ih, unk = struct.unpack_from("<7I", t, 18)
    container = t[46:54]
    o = 55
    if container == b"TEXB0003":
        count, fif = struct.unpack_from("<iI", t, o)
        o += 8
    elif container in (b"TEXB0002", b"TEXB0001"):
        count, = struct.unpack_from("<i", t, o)
        fif = 0xFFFFFFFF
        o += 4
    else:
        raise ValueError(f"unknown container {container}")
    if flags & 4:
        raise ValueError("animated (gif) textures not handled")
    o += 4  # mips field skipped
    w, h, packed, raw_size, size = struct.unpack_from("<5I", t, o)
    o += 20
    data = t[o:o + size]
    if packed:
        data = lz4.block.decompress(data, uncompressed_size=raw_size)
    if fif != 0xFFFFFFFF:  # an embedded PNG/JPEG file
        img = Image.open(io.BytesIO(data)).convert("RGBA")
    elif fmt == 0:
        img = Image.frombytes("RGBA", (w, h), data)
    elif fmt == 8:
        img = Image.frombytes("LA", (w, h), data).convert("RGBA")
    elif fmt == 9:
        img = Image.frombytes("L", (w, h), data).convert("RGBA")
    else:
        raise ValueError(f"DXT texture fmt {fmt} not handled")
    img = img.crop((0, 0, min(iw, img.width), min(ih, img.height)))
    if max_side and max(img.size) > max_side:
        k = max_side / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    w, h = img.size
    raw = img.tobytes()
    comp = lz4.block.compress(raw, store_size=False, mode="high_compression")
    out = io.BytesIO()
    out.write(b"TEXV0005\0TEXI0001\0")
    out.write(struct.pack("<7I", 0, flags, w, h, w, h, unk))
    out.write(b"TEXB0003\0")
    out.write(struct.pack("<iiI", 1, -1, 1))
    out.write(struct.pack("<5I", w, h, 1, len(raw), len(comp)))
    out.write(comp)
    return out.getvalue()


def es_shader(src):
    src = re.sub(r"\bsample\b", "_sample", src)
    # int literals in float arithmetic: `* 2 - 1`, `/ 2`, `+ 1;` etc. after a float expression
    src = re.sub(r"([*/+\-]\s*)(\d+)(?![\d.xe])(?=\s*[-+*/;),])", r"\g<1>\2.0", src)
    return src


def main():
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    max_side = int(sys.argv[sys.argv.index("--max-side") + 1]) if "--max-side" in sys.argv else 0
    _, files = read_pkg(src / "scene.pkg")
    result = {}
    for name in ("project.json", *[p.name for p in src.glob("preview.*")]):
        result[name] = (src / name).read_bytes()
    for name, data in files.items():
        if name.endswith(".tex"):
            data = convert_tex(data, max_side)
        elif name.endswith((".frag", ".vert")):
            data = es_shader(data.decode()).encode()
        result[name] = data
        print(f"{name:80s} {len(data):>10d}")
    write_pkg(out, result)
    print("wrote", out, out.stat().st_size)


if __name__ == "__main__":
    main()
