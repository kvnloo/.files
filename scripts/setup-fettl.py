#!/usr/bin/env python3
"""Install only the fleet-pinned, checksum-verified local Fettl executable."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile
import tomllib
import urllib.parse
import urllib.request


def download(url: str, maximum: int) -> bytes:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise RuntimeError("Fettl downloads require HTTPS")
    with urllib.request.urlopen(url, timeout=120) as response:
        if urllib.parse.urlsplit(response.url).scheme != "https":
            raise RuntimeError("Refusing an insecure download redirect")
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise RuntimeError("Fettl download exceeds its size limit")
    return data


def main() -> None:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise SystemExit("This fleet pin supports Linux x86_64 only")
    root = Path(__file__).resolve().parent.parent
    with (root / "fleet.toml").open("rb") as source:
        pin = tomllib.load(source)["hosts"]["desktop"]["fettl"]
    destination = Path(pin["binary"]).expanduser()
    if destination.is_file():
        with destination.open("rb") as installed:
            installed_digest = hashlib.file_digest(installed, "sha256").hexdigest()
        if installed_digest == pin["binary_sha256"] and os.access(destination, os.X_OK):
            print(f"Fettl {pin['version']} already installed with the pinned binary hash")
            return
    manifest = json.loads(download(pin["manifest"], 1024 * 1024))
    if manifest.get("schema_version") != 1 or manifest.get("version") != pin["version"]:
        raise RuntimeError("Fettl manifest version/schema does not match fleet pin")
    asset = manifest["assets"][pin["asset"]]
    if asset["sha256"] != pin["sha256"] or asset["size"] != pin["size"]:
        raise RuntimeError("Fettl release manifest disagrees with fleet checksum/size")
    url = urllib.parse.urljoin(pin["manifest"], pin["asset"])
    archive = download(url, pin["size"])
    if len(archive) != pin["size"] or hashlib.sha256(archive).hexdigest() != pin["sha256"]:
        raise RuntimeError("Fettl archive checksum or size verification failed")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        member = package.getmember("fettl")
        if not member.isfile() or not 0 < member.size <= 256 * 1024 * 1024:
            raise RuntimeError("Fettl archive has no bounded regular executable")
        stream = package.extractfile(member)
        if stream is None:
            raise RuntimeError("Fettl archive executable is unreadable")
        executable = stream.read()
    digest = hashlib.sha256(executable).hexdigest()
    if digest != pin["binary_sha256"]:
        raise RuntimeError("Fettl executable checksum verification failed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".fettl-", dir=destination.parent, delete=False) as staged:
            temporary = Path(staged.name)
            staged.write(executable)
            staged.flush()
            os.fsync(staged.fileno())
        temporary.chmod(0o755)
        version = subprocess.check_output([str(temporary), "--version"], text=True, timeout=15).strip()
        if version != f"fettl {pin['version']}":
            raise RuntimeError(f"Unexpected Fettl version: {version}")
        os.replace(temporary, destination)
        print(f"Installed {version}: {destination}; binary SHA256 {digest}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
