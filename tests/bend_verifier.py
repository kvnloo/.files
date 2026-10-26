"""Fail-closed environment for a pinned Bend 2.0.34 verdict over one bend/<domain>."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

FILES_SHA256 = {
    "bin/bend": "7fafb749dd33df446a0cb5839c5694df237312a8e8048d2e9420480164ff5934",
    "bend2/base.bend": "c742fae9c49b14f0cc9128429a2c6109364c8a933a142f2c90b9f2e5fd976661",
    "bend2/bendtt.lean": "61e0d2d9f4ddd7dd8bb1497fa612fb49a7274fcac647bf70702ba22321d7c292",
}


@contextmanager
def verifier_environment(domain):
    """Reject ambient forks and cached kernels. Compile in an isolated HOME."""
    manifest = json.loads((Path(domain) / "toolchain.json").read_text())
    if (manifest["files_sha256"] != FILES_SHA256
            or manifest["source_semantics_attested"] is not False
            or manifest["proof_is_permission"] is not False):
        raise RuntimeError(f"{domain} toolchain manifest changed; review its pins")
    bend = Path(os.environ["BEND"]).resolve(strict=True)
    package = bend.parent.parent
    if bend != package / "bin/bend":
        raise RuntimeError("BEND must name the official package's bend/bin/bend")
    for relative, expected in FILES_SHA256.items():
        with (package / relative).open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                raise RuntimeError(f"official toolchain hash mismatch: {package / relative}")
    env = dict(os.environ)
    env.pop("BENDTT", None)
    clang = shutil.which("clang", path=env.get("PATH"))
    if not clang:
        raise RuntimeError("host clang is required to compile the pinned checker")
    lean_bin = Path(env["LEAN_BIN"]).resolve(strict=True)
    # Lean bundles clang too. It must not replace the host compiler.
    env["PATH"] = os.pathsep.join((str(Path(clang).parent), env["PATH"], str(lean_bin)))
    selected_lean = shutil.which("lean", path=env["PATH"])
    if selected_lean is None or Path(selected_lean).resolve() != (lean_bin / "lean").resolve(strict=True):
        raise RuntimeError("another Lean precedes LEAN_BIN; remove it from the verifier PATH")
    with tempfile.TemporaryDirectory(prefix="bend-verifier-") as folder:
        env["HOME"] = str(Path(folder) / "home")
        Path(env["HOME"]).mkdir()
        version = subprocess.run([str(bend), "version"], env=env,
                                 capture_output=True, text=True, check=True, timeout=30)
        if version.stdout.strip() != "bend 2.0.34":
            raise RuntimeError("requires official Bend 2.0.34")
        lean = subprocess.run([str(lean_bin / "lean"), "--version"], env=env,
                              capture_output=True, text=True, check=True, timeout=30)
        if "version 4.34.0," not in lean.stdout:
            raise RuntimeError("requires Lean 4.34.0 from the verified archive")
        yield str(bend), env
