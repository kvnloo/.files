#!/usr/bin/env python3
"""List the highest-resolution variant of each wallpaper, grouped by display class."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class Wallpaper:
    path: Path
    width: int
    height: int

    @property
    def pixels(self) -> int:
        return self.width * self.height


def identity(path: Path) -> str:
    stem = unicodedata.normalize("NFKD", path.stem).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", stem.lower()).strip()


def resolution_class(width: int, height: int) -> str:
    long, short = max(width, height), min(width, height)
    if long >= 7680 and short >= 4320:
        return "8K"
    if long >= 5120 and short >= 2880:
        return "5K"
    if long >= 3840 and short >= 2160:
        return "4K"
    if long >= 3440 and short >= 1440:
        return "UWQHD"
    if long >= 2560 and short >= 1440:
        return "QHD"
    return "HD+"


def aspect_label(width: int, height: int) -> str:
    if height > width:
        return "portrait"
    ratio = width / height
    if ratio >= 2.25:
        return "ultrawide"
    if ratio >= 1.7:
        return "16:9"
    if ratio >= 1.5:
        return "16:10"
    return "standard"


def measure(paths: list[Path]) -> list[Wallpaper]:
    if not paths:
        return []
    try:
        result = subprocess.run(
            ["magick", "identify", "-format", "%w\t%h\t%i\n", *map(str, paths)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        sys.exit("wallpaper catalog requires ImageMagick (`magick`)")
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stderr)
        sys.exit(error.returncode)

    wallpapers: list[Wallpaper] = []
    for line in result.stdout.splitlines():
        width, height, raw_path = line.split("\t", 2)
        wallpapers.append(Wallpaper(Path(raw_path), int(width), int(height)))
    return wallpapers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()

    paths = sorted(
        path
        for path in args.root.rglob("*")
        if path.is_file() and path.suffix.lower() in EXTENSIONS
    )
    best: dict[str, Wallpaper] = {}
    for wallpaper in measure(paths):
        key = identity(wallpaper.path)
        current = best.get(key)
        if current is None or (wallpaper.pixels, wallpaper.width) > (current.pixels, current.width):
            best[key] = wallpaper

    ordered = sorted(
        best.values(),
        key=lambda item: (-item.pixels, item.path.name.casefold(), str(item.path)),
    )
    for item in ordered:
        category = resolution_class(item.width, item.height)
        aspect = aspect_label(item.width, item.height)
        label = f"[{category:<6} {aspect:<9}] {item.path.name}  ·  {item.width}×{item.height}"
        print(f"{label}\t{item.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
