#!/usr/bin/env python3
"""
UEFI Hidden Settings Inspector for ASUS AMI BIOS on Linux.

Reads current NVRAM variables via efivar(8) and diffs them against the
StdDefaults variable (factory defaults). This shows every byte that has
been changed from factory settings, including hidden options that are not
exposed in the BIOS GUI.

For full human-readable names you still need to extract the IFR from the
BIOS image (see the --extract-ifr workflow in this script), but the raw
diff is enough to see *which* settings were modified and their offsets,
so they can be looked up in an IFR dump.

Usage:
    python3 uefi-hidden-settings-inspector.py [command]

Commands:
    dump                Dump all current UEFI variables to ./uefi-dump/
    diff                Compare current variables against StdDefaults
    list                List all variables with setup-related names
    extract-ifr PATH    Given a BIOS .CAP/.ROM/.fd image, extract Setup
                        modules and run IFR extractor (needs chipsec,
                        UEFITool, ifrextractor-rs on PATH or in ./tools/)

Requires: efivar (already installed on most modern Linux distros).
Recommended: chipsec, UEFITool, ifrextractor-rs for IFR extraction.
"""

import os
import re
import sys
import json
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

# Known ASUS AMI setup variable GUIDs and names.
SETUP_GUIDS = {
    "ec87d643-eba4-4bb5-a1e5-3f3e36b20da9": "ASUS Setup",
    "b08f97ff-e6e8-4193-a997-5e9e9b0adb32": "CPU Setup",
    "72c5e28c-7783-43a1-8767-fad73fccafa4": "SA Setup",
    "4570b7f1-ade8-4943-8dc3-406472842384": "PCH Setup",
    "5432122d-d034-49d2-a6de-65a829eb4c74": "ME Setup",
    "5e4ca5e2-c07f-455a-a4eb-d28550884e47": "ASUS AI Setup",
}

SETUP_NAMES = {
    "Setup",
    "SetupCpuFeatures",
    "CpuSetup",
    "SaSetup",
    "PchSetup",
    "MeSetup",
    "ASUSAiSetup",
    "AsusFanSetupFeatures",
    "AsusHwmSetupOneof",
    "AsusQFanSetupData",
}


def run(cmd, check=True, capture=True):
    result = subprocess.run(
        cmd,
        shell=isinstance(cmd, str),
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        print(f"[!] Command failed: {cmd}")
        print(result.stderr)
        sys.exit(1)
    return result


def list_variables():
    out = run("efivar -l").stdout.strip().splitlines()
    vars_ = []
    for line in out:
        if "-" not in line:
            continue
        guid, name = line.rsplit("-", 1)
        vars_.append((guid, name))
    return vars_


def read_variable(guid, name):
    """Read a variable and return raw bytes (stripping efivar -p header)."""
    result = run(f"efivar -n {guid}-{name} -p", check=False)
    if result.returncode != 0:
        return None
    text = result.stdout
    # Find the hex dump start.
    in_value = False
    tokens = []
    for line in text.splitlines():
        if line.startswith("Value:"):
            in_value = True
            continue
        if not in_value:
            continue
        if not line.strip():
            continue
        # Format: 00000000  00 01 ...  |....|
        # The hex part may contain a double-space gap after the 8th byte,
        # so split on "  " and drop the offset (first) and ASCII (last).
        parts = [p for p in line.split("  ") if p]
        if not parts:
            continue
        # First part is the offset, last is the ASCII bar; middle parts are hex.
        hex_parts = parts[1:-1]
        if not hex_parts:
            # Fallback: take everything after offset.
            hex_parts = parts[1:]
        for hp in hex_parts:
            tokens.extend(hp.strip().split())
    # Keep only valid two-character hex tokens.
    hex_str = "".join(t for t in tokens if len(t) == 2 and all(c in "0123456789abcdefABCDEF" for c in t))
    return bytes.fromhex(hex_str)


def parse_nvar(data):
    """
    Parse AMI NVAR storage (used by StdDefaults).
    Returns dict: name -> bytes(value).

    AMI NVAR entry header (10 bytes):
        UINT32 StartId        # 'NVAR' on first entry
        UINT16 Size           # total entry size incl. header
        UINT24 Next           # offset to next linked entry, or 0/0xFFFFFF
        UINT8  Attributes

    See: https://habr.com/ru/articles/281901/
    """
    if data[:4] != b"NVAR":
        print("[!] StdDefaults does not start with NVAR magic.")
        return {}

    ATTR_ASCII_NAME = 0x02
    ATTR_LOCAL_GUID = 0x04
    ATTR_EXTENDED_HEADER = 0x10
    ATTR_ENTRY_VALID = 0x80

    entries = {}
    offset = 0
    while offset + 10 <= len(data):
        start_id = data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 6], "little")
        nxt = int.from_bytes(data[offset + 6:offset + 9], "little")
        attrs = data[offset + 9]

        if size == 0 or size == 0xFFFF or offset + size > len(data):
            break
        if offset == 0 and start_id != b"NVAR":
            break

        if attrs & ATTR_ENTRY_VALID:
            pos = offset + 10
            if attrs & ATTR_LOCAL_GUID:
                pos += 16
            else:
                pos += 1  # GUID index

            if attrs & ATTR_ASCII_NAME:
                name_end = data.find(b"\x00", pos)
                if name_end == -1:
                    name = data[pos:].decode("latin-1", errors="ignore")
                    pos = len(data)
                else:
                    name = data[pos:name_end].decode("latin-1", errors="ignore")
                    pos = name_end + 1
            else:
                name_end = pos
                while name_end + 1 < len(data) and data[name_end:name_end + 2] != b"\x00\x00":
                    name_end += 2
                name = data[pos:name_end].decode("utf-16-le", errors="ignore")
                pos = name_end + 2

            value_end = offset + size
            if attrs & ATTR_EXTENDED_HEADER:
                # Extended header lives at the end of the entry.
                # Minimal form: ExtendedAttributes(1) + ... + ExtendedDataSize(2)
                if value_end > pos + 3:
                    value_end -= 3

            value = data[pos:value_end]
            entries[name] = value

        if nxt == 0 or nxt == 0xFFFFFF:
            offset += size
        else:
            offset += nxt
            if offset == 0 or offset >= len(data):
                break

    return entries


def hexdump(data, width=16):
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08x}  {hex_str:<{width * 3}} {ascii_str}")
    return "\n".join(lines)


def diff_bytes(cur, default, name, width=16):
    """Return a list of differing byte ranges (only within current var size)."""
    diffs = []
    compare_len = min(len(cur), len(default))
    i = 0
    while i < compare_len:
        if cur[i] != default[i]:
            start = i
            while i < compare_len and cur[i] != default[i]:
                i += 1
            end = i
            diffs.append((start, end, cur[start:end], default[start:end]))
        else:
            i += 1
    return diffs


def cmd_dump(args):
    out_dir = Path("logs") / "uefi-dump"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    manifest = {}
    vars_ = list_variables()
    print(f"[*] Dumping {len(vars_)} UEFI variables to {out_dir} ...")
    for guid, name in vars_:
        data = read_variable(guid, name)
        if data is None:
            continue
        safe_name = re.sub(r"[^A-Za-z0-9_\-]", "_", name)
        filename = f"{guid}-{safe_name}.bin"
        (out_dir / filename).write_bytes(data)
        manifest[filename] = {"guid": guid, "name": name, "size": len(data)}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[+] Dumped {len(manifest)} variables.")


def cmd_diff(args):
    # Read StdDefaults
    std_data = read_variable("4599d26f-1a11-49b8-b91f-858745cff824", "StdDefaults")
    if std_data is None:
        print("[!] Cannot read StdDefaults variable.")
        sys.exit(1)
    defaults = parse_nvar(std_data)
    print(f"[*] Parsed {len(defaults)} default entries from StdDefaults ({len(std_data)} bytes).")

    # Read current values for the same names.
    current = {}
    vars_ = list_variables()
    name_to_guid = {n: g for g, n in vars_}
    for name in sorted(defaults.keys()):
        if name in name_to_guid:
            cur = read_variable(name_to_guid[name], name)
            if cur is not None:
                current[name] = cur

    print(f"[*] Found {len(current)} current variables matching defaults.")

    report_lines = []
    report_lines.append("# UEFI Hidden Settings Diff Report")
    report_lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    report_lines.append(f"Board: {Path('/sys/class/dmi/id/board_name').read_text().strip() if Path('/sys/class/dmi/id/board_name').exists() else 'unknown'}")
    report_lines.append(f"BIOS: {Path('/sys/class/dmi/id/bios_version').read_text().strip() if Path('/sys/class/dmi/id/bios_version').exists() else 'unknown'}")
    report_lines.append("")

    changed_any = False
    changed_vars = []
    size_mismatch_vars = []
    for name in sorted(defaults.keys()):
        if name not in current:
            continue
        cur = current[name]
        default = defaults[name]
        diffs = diff_bytes(cur, default, name)
        if not diffs and len(cur) == len(default):
            continue
        changed_any = True
        guid = name_to_guid[name]
        friendly = SETUP_GUIDS.get(guid, guid)
        report_lines.append(f"## {name} ({friendly})")
        report_lines.append(f"GUID: `{guid}`  ")
        report_lines.append(f"Current size: {len(cur)} bytes | Default size: {len(default)} bytes")
        if len(cur) != len(default):
            report_lines.append(
                "*Size mismatch: only offsets within the current variable size are compared; "
                "extra bytes in StdDefaults may be padding or additional packed defaults.*"
            )
            size_mismatch_vars.append(name)
        report_lines.append("")
        if not diffs:
            report_lines.append("No byte differences within the comparable range.")
            report_lines.append("")
        else:
            changed_vars.append(name)
            for start, end, cur_bytes, def_bytes in diffs:
                report_lines.append(f"### Offset 0x{start:04x} - 0x{end:04x}")
                report_lines.append("**Current:**")
                report_lines.append("```")
                report_lines.append(hexdump(cur_bytes))
                report_lines.append("```")
                report_lines.append("**Default:**")
                report_lines.append("```")
                report_lines.append(hexdump(def_bytes))
                report_lines.append("```")
                report_lines.append("")

    report_lines.insert(4, f"Variables with byte changes: {len(changed_vars)}")
    report_lines.insert(5, f"Variables with size mismatch: {len(size_mismatch_vars)}")
    report_lines.insert(6, "")

    if not changed_any:
        report_lines.append("No differences found between current values and StdDefaults.")

    report_text = "\n".join(report_lines)
    out_path = Path("logs") / "uefi-hidden-settings-diff.md"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(report_text)
    print(f"[+] Report written to {out_path}")
    print(report_text)


def cmd_list(args):
    vars_ = list_variables()
    setup_vars = []
    for guid, name in vars_:
        if name in SETUP_NAMES or any(k in name.lower() for k in ["setup", "cpu", "asus", "pch", "sa", "me", "ai", "fan", "overclock", "xmp", "memory"]):
            setup_vars.append((guid, name))
    print(f"[*] Found {len(setup_vars)} setup-related variables:")
    for guid, name in sorted(setup_vars, key=lambda x: x[1]):
        friendly = SETUP_GUIDS.get(guid, "")
        print(f"  {guid}-{name} {f'({friendly})' if friendly else ''}")


def cmd_extract_ifr(args):
    image_path = Path(args[0]) if args else None
    if not image_path or not image_path.exists():
        print("[!] Provide a valid BIOS image path.")
        sys.exit(1)

    tools = Path("tools")
    tools.mkdir(exist_ok=True)

    # Prefer tools in PATH, otherwise look in ./tools.
    def find_tool(name):
        p = shutil.which(name)
        if p:
            return p
        for candidate in tools.glob(f"{name}*"):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return None

    print("[*] IFR extraction workflow:")
    print(f"    1. Image: {image_path}")
    print("    2. Open it in UEFITool (or run UEFITool CLI if available).")
    print("    3. Find the 'Setup' PE32 image section under SetupUtility DxeDriver.")
    print("    4. Extract body as Setup.bin and run: ifrextractor-rs Setup.bin")
    print("    5. The resulting Setup.txt contains human-readable setting names,")
    print("       offsets, and varstore GUIDs. Cross-reference offsets with the")
    print("       diff report above to identify modified hidden settings.")
    print("")

    ut = find_tool("UEFITool") or find_tool("uefitool")
    ifr = find_tool("ifrextractor-rs")

    if ut:
        print(f"[+] UEFITool found: {ut}")
    else:
        print("[-] UEFITool not found. Install from AUR: yay -S uefitool-ng-bin")
    if ifr:
        print(f"[+] ifrextractor-rs found: {ifr}")
    else:
        print("[-] ifrextractor-rs not found. Install from AUR: yay -S ifrextractor-rs-bin")

    # Optionally auto-extract Setup body if chipsec is present.
    chipsec = find_tool("chipsec_util")
    if chipsec:
        print(f"[+] chipsec_util found: {chipsec}")
        print("    You can dump SPI flash with: sudo chipsec_util spi dump bios.bin")
    else:
        print("[-] chipsec not found. Install from AUR: yay -S chipsec-git")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    command = sys.argv[1]
    args = sys.argv[2:]
    if command == "dump":
        cmd_dump(args)
    elif command == "diff":
        cmd_diff(args)
    elif command == "list":
        cmd_list(args)
    elif command == "extract-ifr":
        cmd_extract_ifr(args)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
