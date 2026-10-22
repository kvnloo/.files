"""No network, auth mutation or secrets. Temporary-home/OpenSSH fixture tests."""
import base64
import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/fleet-ssh"
loader = importlib.machinery.SourceFileLoader("fleet_ssh", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
fleet = importlib.util.module_from_spec(spec)
loader.exec_module(fleet)


def public(seed):
    wire = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes([seed]) * 32
    return "ssh-ed25519 " + base64.b64encode(wire).decode()


class FleetSSH(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fleet ssh ")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = {**os.environ, "HOME": str(self.home), "PATH": "/usr/bin:/bin",
                    "XDG_CONFIG_HOME": str(self.home / ".config"),
                    "XDG_DATA_HOME": str(self.home / ".local/share")}
        self.m = {"schema": fleet.VERSION, "nodes": []}
        for i, name in enumerate(("groot", "mbp", "phone"), 1):
            self.m["nodes"].append({"name": name, "owned": True, "tailscale_id": "n" + str(i),
                "owner_login": "owner@example.test", "kind": "phone" if name == "phone" else "linux",
                "proot": name == "phone", "user": "root" if name == "phone" else "kvn",
                "address": "100.64.0." + str(i), "port": 8022 if name == "phone" else 22,
                "identity_public_key": public(i), "host_public_key": public(i + 10),
                "host_fingerprint": fleet.key(public(i + 10)), "host_key_provenance": "fixture console"})
        self.manifest = self.home / "manifest.json"
        self.status = self.home / "tailscale.json"
        self.s = {"User": {"1": {"LoginName": "owner@example.test"}}, "Peer": {
            n["name"]: {"ID": n["tailscale_id"], "UserID": 1, "TailscaleIPs": [n["address"]]}
            for n in self.m["nodes"]}}
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.m))
        self.status.write_text(json.dumps(self.s))

    def cmd(self, *args, ok=True):
        r = subprocess.run(["python3", str(SCRIPT), *args], env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0 if ok else 1, r.stderr)
        return json.loads(r.stdout if ok else r.stderr)

    def tools(self):
        for folder in fleet.BINS:
            d = self.home / folder
            d.mkdir(parents=True)
        for name, folder in (("pi", ".npm-global/bin"), ("local-tool", ".local/bin"),
                             ("bun-tool", ".bun/bin"), ("cargo-tool", ".cargo/bin")):
            p = self.home / folder / name
            p.write_text("#!/bin/sh\nprintf '%s\\n' tool-ok\n")
            p.chmod(0o700)

    def test_path_installer_is_idempotent_and_preserves_guards(self):
        self.tools()
        startup = 'case $- in *i*) ;; *) return ;; esac\necho INTERACTIVE_ONLY\n'
        (self.home / ".bashrc").write_text(startup)
        (self.home / ".bash_profile").write_text('. "$HOME/.bashrc"\n')
        self.assertTrue(self.cmd("path-install", "--home", str(self.home))["changed"])
        snapshots = {p: p.stat().st_mtime_ns for p in self.home.rglob("*") if p.is_file() and p.name != "ssh-parity.lock"}
        self.assertEqual(self.cmd("path-install", "--home", str(self.home)), {"changed": []})
        self.assertTrue((self.home / ".bashrc").read_text().endswith(startup))
        self.assertEqual(snapshots, {p: p.stat().st_mtime_ns for p in snapshots})
        r = subprocess.run(["bash", "--noprofile", "--norc", "-c", '. "$HOME/.bashrc"; pi; local-tool; bun-tool; cargo-tool'],
                           env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "tool-ok\n" * 4)
        self.assertEqual(r.stderr, "")

    def test_actual_bash_login_loads_managed_path(self):
        self.tools()
        (self.home / ".bash_profile").write_text('. "$HOME/.bashrc"\n')
        (self.home / ".bashrc").write_text('case $- in *i*) ;; *) return ;; esac\necho NOISE\n')
        fleet.path_install(self.home)
        r = subprocess.run(["bash", "-lc", "pi; local-tool"], env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "tool-ok\n" * 2)
        self.assertEqual(r.stderr, "")

    def test_cli_install_is_idempotent_with_authenticated_status_fixture(self):
        args = ["install", "--manifest", str(self.manifest), "--tailscale-status", str(self.status),
                "--node", "groot", "--home", str(self.home)]
        self.assertTrue(self.cmd(*args)["changed"])
        self.assertEqual(self.cmd(*args), {"changed": []})

    def test_login_profile_selection_does_not_shadow_existing_file(self):
        self.tools()
        (self.home / ".bash_login").write_text('export EXISTING_LOGIN=yes\n')
        fleet.path_install(self.home)
        self.assertFalse((self.home / ".bash_profile").exists())
        r = subprocess.run(["bash", "--noprofile", "--norc", "-c", '. "$HOME/.bash_login"; pi; printf "%s" "$EXISTING_LOGIN"'],
                           env=self.env, text=True, capture_output=True)
        self.assertEqual(r.stdout, "tool-ok\nyes", r.stderr)

    def test_posix_repeated_source_no_duplicate_path_and_empty_path(self):
        self.tools()
        fleet.path_install(self.home)
        for initial in ("/usr/bin:/bin", ""):
            r = subprocess.run(["/bin/sh", "-c", '. "$HOME/.profile"; . "$HOME/.profile"; printf "%s" "$PATH"'],
                               env={**self.env, "PATH": initial}, text=True, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            parts = r.stdout.split(":")
            for folder in fleet.BINS:
                self.assertEqual(parts.count(str(self.home / folder)), 1)
            self.assertNotIn("", parts)

    @unittest.skipUnless(shutil.which("fish"), "fish not installed")
    def test_fish_noninteractive_spaces_and_omf_missing_is_quiet(self):
        self.tools()
        fleet.path_install(self.home)
        fish = self.home / ".config/fish/conf.d/omf.fish"
        fish.write_text((ROOT / "config/fish/conf.d/omf.fish").read_text())
        r = subprocess.run(["fish", "-c", "pi; local-tool; bun-tool; cargo-tool"],
                           env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "tool-ok\n" * 4)
        self.assertEqual(r.stderr, "")

    def test_missing_tool_directories_not_added(self):
        fleet.path_install(self.home)
        r = subprocess.run(["/bin/sh", "-c", '. "$HOME/.profile"; printf "%s" "$PATH"'],
                           env=self.env, text=True, capture_output=True)
        self.assertEqual(r.stdout, "/usr/bin:/bin")

    def test_manifest_valid_linux_and_phone(self):
        self.assertEqual(len(fleet.load_manifest(self.manifest, self.status)["nodes"]), 3)

    def test_admission_rejects_unowned_root_agentjob_duplicate_and_injection(self):
        original = copy.deepcopy(self.m)
        for field, value in (("owned", False), ("user", "root"), ("user", "agentjob"),
                             ("name", "bad\nHost *"), ("address", "192.168.0.1"),
                             ("port", True), ("port", 0), ("host_fingerprint", "SHA256:unverified"),
                             ("host_key_provenance", ""), ("identity_public_key", "restrict " + public(1))):
            with self.subTest(field=field, value=value):
                self.m = copy.deepcopy(original)
                self.m["nodes"][0][field] = value
                self.save()
                with self.assertRaises(ValueError):
                    fleet.load_manifest(self.manifest, self.status)
        self.m = copy.deepcopy(original)
        self.m["nodes"][2]["proot"] = False
        self.save()
        with self.assertRaises(ValueError):
            fleet.load_manifest(self.manifest)

    def test_shared_identity_and_host_key_refused(self):
        for field in ("identity_public_key", "host_public_key"):
            orig = self.m["nodes"][1][field]
            self.m["nodes"][1][field] = self.m["nodes"][0][field]
            self.save()
            with self.assertRaises(ValueError):
                fleet.load_manifest(self.manifest)
            self.m["nodes"][1][field] = orig

    def test_owner_id_ip_tags_and_unknown_node_fail_closed(self):
        for field, value in (("ID", "different"), ("UserID", 2), ("TailscaleIPs", ["100.64.1.1"]), ("Tags", ["tag:worker"])):
            old = copy.deepcopy(self.s)
            self.s["Peer"]["groot"][field] = value
            self.save()
            with self.assertRaises(ValueError):
                fleet.load_manifest(self.manifest, self.status)
            self.s = old
        with self.assertRaises(ValueError):
            fleet.node(self.m, "unowned-peer")

    def test_install_requires_ownership_evidence(self):
        r = self.cmd("install", "--manifest", str(self.manifest), "--node", "groot", "--home", str(self.home), ok=False)
        self.assertIn("ownership", r["error"])
        self.assertFalse((self.home / ".ssh/authorized_keys").exists())

    def test_install_preserves_existing_keys_config_and_revokes_only_managed(self):
        ssh = self.home / ".ssh"
        ssh.mkdir(mode=0o700)
        auth = ssh / "authorized_keys"
        old = public(99) + " owner-existing\n"
        auth.write_text(old)
        config = ssh / "config"
        config.write_text("Host mbp\n  Port 2222\n  User agentjob\n")
        self.assertTrue(fleet.install(self.m, "groot", self.home))
        self.assertEqual(fleet.install(self.m, "groot", self.home), [])
        self.assertTrue(auth.read_text().startswith(old))
        self.assertIn("User agentjob", config.read_text())
        self.assertEqual(auth.stat().st_mode & 0o777, 0o600)
        self.m["nodes"] = self.m["nodes"][:2]
        fleet.install(self.m, "groot", self.home)
        self.assertNotIn("fleet:phone", auth.read_text())
        self.assertIn(old, auth.read_text())

    def test_render_is_stable_restricted_source_and_strict_pinned(self):
        rendered = fleet.render(self.m, "groot")
        self.m["nodes"].reverse()
        self.assertEqual(rendered, fleet.render(self.m, "groot"))
        self.assertIn('from="100.64.0.2",restrict ', rendered["authorized_keys"])
        self.assertNotIn("fleet:groot", rendered["authorized_keys"])
        for line in ("StrictHostKeyChecking yes", "ForwardAgent no", "ControlPath none"):
            self.assertIn(line, rendered["config"])
        config = self.home / "ssh-config"
        config.write_text(rendered["config"])
        r = subprocess.run(["ssh", "-G", "-F", str(config), "fleet-mbp"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for line in ("user kvn", "port 22", "hostname 100.64.0.2", "stricthostkeychecking true", "hostkeyalias fleet-mbp"):
            self.assertIn(line, r.stdout)
        known = self.home / "known"
        known.write_text(rendered["known_hosts"])
        r = subprocess.run(["ssh-keygen", "-F", "fleet-mbp", "-f", str(known)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(self.m["nodes"][1]["host_public_key"], r.stdout)

    def test_identity_verifier_and_tamper_detection(self):
        fleet.install(self.m, "groot", self.home)
        p = self.home / ".ssh/fleet/id_ed25519-groot"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(p)], check=True)
        self.m["nodes"][0]["identity_public_key"] = Path(str(p) + ".pub").read_text().rsplit(" ", 1)[0]
        fleet.install(self.m, "groot", self.home)
        result = fleet.verify(self.m, "groot", self.home)
        self.assertTrue(result["verified"])
        self.assertFalse(result["all_to_all_verified"])
        known = self.home / ".ssh/fleet/known_hosts"
        known.write_text(known.read_text() + "# drift\n")
        with self.assertRaises(ValueError):
            fleet.verify(self.m, "groot", self.home)

    def test_refuses_symlink_and_unsafe_directory(self):
        outside = self.home / "outside"
        outside.write_text("untouched")
        (self.home / ".bashrc").symlink_to(outside)
        with self.assertRaises(ValueError):
            fleet.path_install(self.home)
        self.assertEqual(outside.read_text(), "untouched")
        ssh = self.home / ".ssh"
        ssh.mkdir(mode=0o777)
        ssh.chmod(0o777)
        with self.assertRaises(ValueError):
            fleet.install(self.m, "groot", self.home)

    def test_malformed_auth_block_refused_before_ssh_writes(self):
        ssh = self.home / ".ssh"
        ssh.mkdir(mode=0o700)
        (ssh / "authorized_keys").write_text(fleet.BEGIN + "\n")
        with self.assertRaises(ValueError):
            fleet.install(self.m, "groot", self.home)
        self.assertFalse((ssh / "fleet/config").exists())

    def test_requirements_cli_json_and_canonical_empty_admission(self):
        self.assertEqual(self.cmd("requirements")["schema"], fleet.VERSION)
        r = subprocess.run(["python3", str(SCRIPT), "validate", "--manifest", str(ROOT / "config/fleet/ssh-owned-hosts.json")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no admitted nodes", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
