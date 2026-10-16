"""Behavioral bootstrap boundaries; no sudo, network, host services or installs.

The script is sourceable so fixtures can redirect its filesystem boundaries to
an isolated tree. Commands emulate a host; production checks/rendering/state
comparison still execute. No assertions depend on source text.
"""

import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "setup-k3s.sh"
FRESH_INSTALLER = b"#!/bin/sh\nexit 99\n"
FRESH_BINARY = b"isolated downloaded binary\n"

FAKE_COMMAND = r'''
import json
import os
import stat
import tempfile
import sys
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps([name, *args]) + '\n')

if name == 'uname':
    print({'-s': os.environ.get('HOST_OS', 'Linux'), '-r': os.environ.get('HOST_KERNEL', '6.12-cachyos'), '-m': os.environ.get('HOST_ARCH', 'x86_64')}[args[0]])
elif name == 'systemd-detect-virt':
    print(os.environ.get('VIRTUALIZATION', 'none'))
elif name == 'systemctl':
    if args[0] == 'show':
        field = next(value for value in args if value.startswith('--property=')).split('=', 1)[1]
        if field == 'Version':
            print('257')
        elif field == 'LoadState':
            print('loaded' if os.environ.get('MANAGED_FIXTURE') == '1' and args[1] == 'k3s.service' else 'not-found')
        elif field == 'FragmentPath':
            print(os.environ['FIXTURE_ROOT'] + '/systemd/k3s.service')
        elif field == 'DropInPaths':
            print(os.environ.get('SERVICE_DROPINS', ''))
        else:
            sys.exit(90)
    elif args[0] in ('is-active', 'is-enabled'):
        if args[-1] != 'k3s.service' or os.environ.get('SERVICE_INACTIVE') == '1':
            sys.exit(3)
    else:
        sys.exit('unexpected mutating systemctl: ' + repr(args))
elif name == 'getconf':
    print(os.environ.get('CPU_COUNT', '8'))
elif name == 'id':
    print(os.environ.get('HOST_UID', '0'))
elif name == 'df':
    if os.environ.get('DF_FAIL') == '1':
        sys.exit(1)
    is_inode = '-Pi' in args
    if is_inode:
        total = 1000000
        free = int(os.environ.get('FREE_INODE_PERCENT', '80'))
    else:
        total = 100 * 1024 * 1024
        is_root = args[-1] in ('/', os.environ['FIXTURE_ROOT'])
        free = int(os.environ.get('ROOT_FREE_PERCENT' if is_root else 'DATA_FREE_PERCENT', '50'))
    available = int(os.environ.get('FREE_INODES' if is_inode else ('ROOT_FREE_KIB' if is_root else 'DATA_FREE_KIB'), total * free // 100))
    print('Filesystem Size Used Avail Use% Mounted on')
    print(f'/dev/fixture {total} {total - available} {available} {100-free}% {args[-1]}')
elif name == 'ip':
    if 'address' in args:
        local = os.environ.get('NODE_ADDRESS', '192.168.1.20')
        iface = os.environ.get('NODE_IFACE', 'enp1s0')
        print(json.dumps([{'ifname': iface, 'addr_info': [{'local': local, 'prefixlen': 24}]}]))
    else:
        routes = [{'dst': 'default', 'gateway': '192.168.1.1', 'dev': 'enp1s0'}, {'dst': '192.168.1.0/24', 'dev': 'enp1s0'}]
        if os.environ.get('ROUTE_COLLISION') == '1':
            routes.append({'dst': '10.42.0.0/16', 'dev': 'docker0'})
        print(json.dumps(routes))
elif name == 'tailscale':
    print(os.environ.get('TAILSCALE_ADDRESS', '100.113.138.100'))
elif name == 'ss':
    print(os.environ.get('LISTENING_SOCKETS', ''))
elif name == 'ufw':
    if args == ['status', 'verbose']:
        print('Status: active\nDefault: deny (incoming), allow (outgoing), disabled (routed)')
    elif args == ['show', 'added']:
        print('Added user rules (see "ufw status" for running firewall):')
        print('ufw allow OpenSSH')
        for port in (6443, 10250):
            print(f'ufw allow in on cni0 from 10.42.0.0/16 to any port {port} proto tcp')
        if os.environ.get('MISSING_FORWARD_RULE') != '1':
            print('ufw route allow in on cni0 from 10.42.0.0/16')
        if os.environ.get('EXTRA_UFW_RULE'):
            print(os.environ['EXTRA_UFW_RULE'])
    elif args == ['app', 'info', 'OpenSSH']:
        print('Profile: OpenSSH\nPort:\n  ' + os.environ.get('SSH_PROFILE_PORT', '22/tcp'))
    else:
        sys.exit('unexpected mutating ufw: ' + repr(args))
elif name == 'kind':
    print('existing-integration')
elif name == 'stat':
    # Ownership is a host boundary, emulated independently of the pytest UID.
    # Modes and symlinks are inspected on real isolated fixture files.
    info = Path(args[-1]).stat() if '-Lc' in args else Path(args[-1]).lstat()
    fmt = args[args.index('-Lc') + 1] if '-Lc' in args else args[args.index('-c') + 1]
    print({'%u': '0', '%a': format(stat.S_IMODE(info.st_mode), 'o'), '%u:%a': '0:' + format(stat.S_IMODE(info.st_mode), 'o')}[fmt])
elif name == 'mktemp' and os.environ.get('FRESH_APPLY') == '1':
    root = Path(os.environ['FIXTURE_ROOT'])
    if args[0] == '-d':
        print(tempfile.mkdtemp(prefix='staging-', dir=root))
    else:
        parent = Path(args[0]).parent
        assert parent == root / 'config'
        fd, path = tempfile.mkstemp(prefix='.config.yaml.', dir=parent)
        os.close(fd)
        print(path)
elif name == 'curl' and os.environ.get('FRESH_APPLY') == '1':
    destination = Path(args[args.index('--output') + 1])
    assert destination.is_relative_to(Path(os.environ['FIXTURE_ROOT']))
    destination.write_bytes(b'#!/bin/sh\nexit 99\n' if destination.name == 'install.sh' else b'isolated downloaded binary\n')
elif name == 'install' and os.environ.get('FRESH_APPLY') == '1':
    root = Path(os.environ['FIXTURE_ROOT'])
    mode = int(args[args.index('-m') + 1], 8)
    if '-d' in args:
        for directory in args[args.index('-m') + 2:]:
            path = Path(directory)
            assert path.is_relative_to(root)
            path.mkdir(parents=True, mode=mode)
            path.chmod(mode)
    else:
        source, destination = map(Path, args[-2:])
        assert source.is_relative_to(root) and destination.is_relative_to(root)
        if os.environ.get('CONFIG_WRITE_FAIL') == '1' and destination.name.startswith('.config.yaml.'):
            destination.write_bytes(b'partial')
            sys.exit(1)
        destination.write_bytes(source.read_bytes())
        destination.chmod(mode)
else:
    sys.exit('unexpected mutation/download/privilege command: ' + name)
'''


class Host:
    def __init__(self, root: Path):
        self.root = root
        self.commands = root / "commands"
        self.commands.mkdir()
        self.log = root / "commands.jsonl"
        for name in (
            "uname", "systemd-detect-virt", "systemctl", "getconf", "id", "df",
            "ip", "ss", "ufw", "kind", "stat", "curl", "install", "mktemp", "sudo", "tailscale", "swapoff", "sysctl",
        ):
            command = self.commands / name
            command.write_text(f"#!{sys.executable}\n" + FAKE_COMMAND)
            command.chmod(0o755)
        (root / "proc" / "1").mkdir(parents=True)
        (root / "proc" / "1" / "comm").write_text("systemd\n")
        (root / "proc" / "meminfo").write_text("MemTotal: 16777216 kB\nMemAvailable: 8388608 kB\n")
        (root / "proc" / "swaps").write_text("Filename Type Size Used Priority\n")
        (root / "cgroup").mkdir()
        (root / "cgroup" / "cgroup.controllers").write_text("cpu memory pids io\n")
        (root / "bulk").mkdir()
        self.env = {
            **os.environ,
            "PATH": f"{self.commands}:/usr/bin:/bin",
            "COMMAND_LOG": str(self.log),
            "FIXTURE_ROOT": str(root),
        }
        for name in ("PROOT_TMP_DIR", "PROOT_LOADER", "ANDROID_ROOT"):
            self.env.pop(name, None)
        self.preamble = f'''
source {shlex.quote(str(SCRIPT))}
command() {{
    if [[ "$*" == '-v k3s' ]]; then return 1; fi
    builtin command "$@"
}}
CONFIG_DIR={shlex.quote(str(root / "config"))}
SERVICE_DIR={shlex.quote(str(root / "systemd"))}
BIN_DIR={shlex.quote(str(root / "bin"))}
STATE_FILE="$CONFIG_DIR/.dotfiles-managed"
PROC_ROOT={shlex.quote(str(root / "proc"))}
CGROUP_ROOT={shlex.quote(str(root / "cgroup"))}
KUBELET_DIR={shlex.quote(str(root / "kubelet"))}
HOST_ETC={shlex.quote(str(root / "etc"))}
HOST_RUN={shlex.quote(str(root / "run"))}
DEFAULT_DATA_DIR={shlex.quote(str(root / "default-data"))}
'''

    def run(self, *args: str, prepare: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", self.preamble + prepare + '\nmain "$@"', "fixture", *args],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
            cwd=self.root,
        )

    @property
    def flags(self) -> tuple[str, ...]:
        return (
            "--node-ip", "192.168.1.20", "--firewall-policy", "ufw-single-node",
            "--data-dir", str(self.root / "bulk" / "data"),
        )

    def snapshot(self) -> dict[str, tuple[int, bytes]]:
        return {
            str(path.relative_to(self.root)): (path.stat().st_mode, path.read_bytes())
            for path in self.root.rglob("*")
            if path.is_file() and path != self.log
        }

    def managed(self, version: str = "v1.36.5+k3s1") -> str:
        for directory in ("config", "systemd", "bin", "bulk/data/server"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        binary = self.root / "bin" / "k3s"
        binary.write_text(f"#!/bin/sh\nprintf '%s\\n' 'k3s version {version} (fixture)'\n")
        binary.chmod(0o755)
        (self.root / "systemd" / "k3s.service").write_text("isolated service fixture\n")
        (self.root / "systemd" / "k3s.service.env").write_text("")
        for relative in ("config/k3s.yaml", "bulk/data/server/token", "bulk/data/server/node-token"):
            path = self.root / relative
            path.write_text("isolated non-secret fixture\n")
            path.chmod(0o600)
        self.env["MANAGED_FIXTURE"] = "1"
        # Prepare real managed files/state before the operation being asserted.
        setup = self.preamble + f'''
NODE_IP=192.168.1.20
DATA_DIR={shlex.quote(str(self.root / "bulk" / "data"))}
FLANNEL_IFACE=enp1s0
BINARY_SHA256={hashlib.sha256(binary.read_bytes()).hexdigest()}
render_config > "$CONFIG_DIR/config.yaml"
chmod 600 "$CONFIG_DIR/config.yaml"
write_state
'''
        completed = subprocess.run(["bash", "-c", setup], env=self.env, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stderr
        return f'\nBINARY_SHA256={hashlib.sha256(binary.read_bytes()).hexdigest()}\n'

    def fresh(self) -> str:
        self.env["FRESH_APPLY"] = "1"
        (self.root / "run").mkdir()
        return (
            f"\nINSTALLER_SHA256={hashlib.sha256(FRESH_INSTALLER).hexdigest()}"
            f"\nBINARY_SHA256={hashlib.sha256(FRESH_BINARY).hexdigest()}\n"
        )


@pytest.fixture
def host(tmp_path: Path) -> Host:
    return Host(tmp_path)


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("HOST_OS", "Darwin", "native Linux/systemd required"),
        ("HOST_KERNEL", "6.6.98-android15", "Android/PRoot cannot host"),
        ("HOST_ARCH", "aarch64", "x86_64 desktops only"),
        ("VIRTUALIZATION", "docker", "container/PRoot environment unsupported"),
    ],
)
def test_unsupported_host_fails_without_mutation(host: Host, setting: str, value: str, message: str) -> None:
    host.env[setting] = value
    before = host.snapshot()
    result = host.run("--check", *host.flags)
    assert result.returncode != 0
    assert message in result.stderr
    assert host.snapshot() == before


def test_default_check_passes_without_writes_or_privilege_prompts(host: Host) -> None:
    before = host.snapshot()
    result = host.run(*host.flags)
    assert result.returncode == 0, result.stderr
    assert "Read-only: no changes made" in result.stdout
    assert "existing-integration" in result.stdout
    assert host.snapshot() == before
    calls = [json.loads(line) for line in host.log.read_text().splitlines()]
    assert not any(call[0] in {"sudo", "curl", "install", "mktemp"} for call in calls)
    assert all(call[1] in {"show", "is-active", "is-enabled"} for call in calls if call[0] == "systemctl")
    assert all(call[1:] in (["status", "verbose"], ["show", "added"], ["app", "info", "OpenSSH"]) for call in calls if call[0] == "ufw")


@pytest.mark.parametrize("mode", ["--check", "--apply"])
def test_bulk_data_dir_never_masks_root_pressure(host: Host, mode: str) -> None:
    host.env["ROOT_FREE_PERCENT"] = "1"
    host.env["DATA_FREE_PERCENT"] = "80"
    before = host.snapshot()
    result = host.run(mode, *host.flags)
    assert result.returncode != 0
    assert "root/nodefs disk pressure" in result.stderr
    assert host.snapshot() == before


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("DATA_FREE_PERCENT", "5", "data/imagefs disk pressure"),
        ("FREE_INODE_PERCENT", "5", "inode pressure"),
        ("DF_FAIL", "1", "cannot inspect root/nodefs disk capacity"),
        ("HOST_UID", "1000", "no escalation attempted"),
        ("ROUTE_COLLISION", "1", "route overlaps pod/service CIDR"),
        ("LISTENING_SOCKETS", "tcp LISTEN 0 128 0.0.0.0:6443 0.0.0.0:*", "port 6443 is already listening"),
        ("MISSING_FORWARD_RULE", "1", "missing dedicated cni0"),
        ("EXTRA_UFW_RULE", "ufw allow 6443/tcp", "inbound allow needs manual review"),
        ("EXTRA_UFW_RULE", "ufw allow from any port 22 to any", "inbound allow needs manual review"),
        ("EXTRA_UFW_RULE", "ufw allow in on cni0 from any to 10.42.0.0/16 port 6443 proto tcp", "inbound allow needs manual review"),
        ("EXTRA_UFW_RULE", "ufw allow 6443/tcp comment out", "inbound allow needs manual review"),
        ("SSH_PROFILE_PORT", "6443/tcp", "OpenSSH profile is not exclusively"),
    ],
)
def test_failed_preconditions_never_apply(host: Host, setting: str, value: str, message: str) -> None:
    host.env[setting] = value
    before = host.snapshot()
    result = host.run("--apply", *host.flags)
    assert result.returncode != 0
    assert message in result.stderr
    assert host.snapshot() == before


def test_swap_is_not_disabled_to_force_kubelet(host: Host) -> None:
    (host.root / "proc" / "swaps").write_text("Filename Type Size Used Priority\n/dev/zram0 partition 100000000 40000000 100\n")
    before = host.snapshot()
    result = host.run("--check", *host.flags)
    assert result.returncode == 0, result.stderr
    assert "Existing swap preserved" in result.stdout
    assert host.snapshot() == before
    calls = [json.loads(line) for line in host.log.read_text().splitlines()]
    assert not any(call[0] in {"swapoff", "sysctl"} for call in calls)


def test_unowned_configuration_is_never_adopted(host: Host) -> None:
    (host.root / "config").mkdir()
    (host.root / "config" / "config.yaml").write_text("existing user configuration\n")
    before = host.snapshot()
    result = host.run("--apply", *host.flags)
    assert result.returncode != 0
    assert "refusing overwrite/adoption" in result.stderr
    assert host.snapshot() == before


@pytest.mark.parametrize("mode", ["--check", "--apply"])
def test_matching_managed_rerun_never_restarts_or_writes(host: Host, mode: str) -> None:
    prepare = host.managed()
    before = host.snapshot()
    result = host.run(mode, *host.flags, prepare=prepare)
    assert result.returncode == 0, result.stderr
    assert "no changes, downloads or restart" in result.stdout
    assert host.snapshot() == before


@pytest.mark.parametrize("conflict", ["config", "service", "version", "inactive", "permissions"])
def test_managed_conflicts_abort_without_reconciliation(host: Host, conflict: str) -> None:
    prepare = host.managed()
    if conflict == "config":
        (host.root / "config" / "config.yaml").write_text("user-modified config\n")
    elif conflict == "service":
        (host.root / "systemd" / "k3s.service").write_text("user-modified service\n")
    elif conflict == "version":
        state = host.root / "config" / ".dotfiles-managed"
        state.write_text(state.read_text().replace("v1.36.5+k3s1", "v1.35.0+k3s1"))
    elif conflict == "inactive":
        host.env["SERVICE_INACTIVE"] = "1"
    else:
        (host.root / "config" / "k3s.yaml").chmod(0o644)
    before = host.snapshot()
    result = host.run("--apply", *host.flags, prepare=prepare)
    assert result.returncode != 0
    assert host.snapshot() == before
    assert any(message in result.stderr for message in ("changed", "conflict", "inactive", "permissions unsafe"))


@pytest.mark.parametrize("offset", [-1, 0, 1])
@pytest.mark.parametrize("resource", ["bytes", "inodes"])
def test_disk_gate_requires_strictly_five_percent_plus_reserve(host: Host, resource: str, offset: int) -> None:
    if resource == "bytes":
        host.env["DATA_FREE_KIB"] = str(100 * 1024 * 1024 // 20 + 1024 * 1024 + offset)
    else:
        host.env["FREE_INODES"] = str(1000000 // 20 + 1000 + offset)
    before = host.snapshot()
    result = host.run("--check", *host.flags)
    assert (result.returncode == 0) == (offset > 0), result.stderr
    assert host.snapshot() == before


@pytest.mark.parametrize("verified", [True, False])
def test_tailnet_binding_requires_verified_local_tailscale_address(host: Host, verified: bool) -> None:
    host.env["NODE_ADDRESS"] = "100.113.138.100"
    host.env["NODE_IFACE"] = "tailscale0"
    host.env["TAILSCALE_ADDRESS"] = "100.113.138.100" if verified else "100.113.138.101"
    before = host.snapshot()
    result = host.run("--check", *host.flags, "--node-ip", "100.113.138.100")
    assert (result.returncode == 0) == verified, result.stderr
    if not verified:
        assert "not verified by local tailscale" in result.stderr
    assert host.snapshot() == before


def test_rendered_config_binds_api_and_kubelet_only_to_chosen_private_address(host: Host) -> None:
    host.managed()
    lines = (host.root / "config" / "config.yaml").read_text().splitlines()
    for key in ("bind-address", "node-ip", "advertise-address"):
        values = [json.loads(line.split(":", 1)[1]) for line in lines if line.startswith(key + ":")]
        assert values == ["192.168.1.20"]
    assert [json.loads(line.split(":", 1)[1]) for line in lines if line.startswith("flannel-iface:")] == ["enp1s0"]
    addresses = [json.loads(line.strip()[2:]) for line in lines if line.strip().startswith('- "address=')]
    assert addresses == ["address=192.168.1.20"]


@pytest.mark.parametrize("mode", ["--check", "--apply"])
def test_unowned_existing_service_is_never_adopted(host: Host, mode: str) -> None:
    host.env["MANAGED_FIXTURE"] = "1"
    before = host.snapshot()
    result = host.run(mode, *host.flags)
    assert result.returncode != 0
    assert "unowned" in result.stderr.lower() and "service" in result.stderr.lower()
    assert host.snapshot() == before
    calls = [json.loads(line) for line in host.log.read_text().splitlines()]
    assert not any(call[0] in {"curl", "install", "mktemp"} for call in calls)
    assert all(call[1] in {"show", "is-active", "is-enabled"} for call in calls if call[0] == "systemctl")


@pytest.mark.parametrize("mode", ["--check", "--apply"])
def test_installed_binary_version_must_match_pin(host: Host, mode: str) -> None:
    prepare = host.managed(version="v1.35.0+k3s1")
    before = host.snapshot()
    result = host.run(mode, *host.flags, prepare=prepare)
    assert result.returncode != 0
    assert "version" in result.stderr.lower()
    assert host.snapshot() == before


@pytest.mark.parametrize("node_ip", ["8.8.8.8", "0.0.0.0", "127.0.0.1", "192.168.1.21"])
def test_public_wildcard_loopback_or_unassigned_node_ip_cannot_install(host: Host, node_ip: str) -> None:
    before = host.snapshot()
    result = host.run("--apply", *host.flags, "--node-ip", node_ip)
    assert result.returncode != 0
    assert "node-ip" in result.stderr
    assert host.snapshot() == before


@pytest.mark.parametrize("failure", ["checksum", "source-read", "config-write"])
def test_fresh_apply_failure_never_publishes_partial_config_or_starts_service(host: Host, failure: str) -> None:
    prepare = host.fresh()
    if failure == "checksum":
        prepare += f"\nBINARY_SHA256={'0' * 64}\n"
    elif failure == "source-read":
        # cat on a directory fails deterministically, even when pytest is root.
        prepare += f"\nDEFAULTS={shlex.quote(str(host.root / 'proc'))}\n"
    else:
        host.env["CONFIG_WRITE_FAIL"] = "1"
    result = host.run("--apply", *host.flags, prepare=prepare)
    assert result.returncode != 0
    assert not (host.root / "config" / "config.yaml").exists()
    assert not (host.root / "bin" / "k3s").exists()
    assert not (host.root / "systemd" / "k3s.service").exists()
    assert not (host.root / "config" / ".dotfiles-managed").exists()
    if failure != "config-write":
        assert not (host.root / "config").exists()
        assert not (host.root / "bulk" / "data").exists()
    else:
        candidates = list((host.root / "config").glob(".config.yaml.*"))
        assert len(candidates) == 1
        assert candidates[0].read_bytes() == b"partial"
    calls = [json.loads(line) for line in host.log.read_text().splitlines()]
    assert all(call[1] in {"show", "is-active", "is-enabled"} for call in calls if call[0] == "systemctl")
