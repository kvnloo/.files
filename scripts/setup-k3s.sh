#!/usr/bin/env bash
# Explicit system operation; deliberately not an onboarding module.
set -euo pipefail

K3S_VERSION='v1.36.5+k3s1'
# Official release tag resolves to this immutable upstream commit.
INSTALLER_COMMIT='3dd98cc58ec34991e7e59b93663eee2e26fc1f65'
INSTALLER_SHA256='46177d4c99440b4c0311b67233823a8e8a2fc09693f6c89af1a7161e152fbfad'
BINARY_SHA256='d73847bcd3c5fccef0115b372e2f9a91f3032dc84bbf71518a4617565294d313'
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULTS="$SCRIPT_DIR/../config/k3s/config.yaml"
CONFIG_DIR='/etc/rancher/k3s'
SERVICE_DIR='/etc/systemd/system'
BIN_DIR='/usr/local/bin'
STATE_FILE='/etc/rancher/k3s/.dotfiles-managed'
PROC_ROOT='/proc'
CGROUP_ROOT='/sys/fs/cgroup'
KUBELET_DIR='/var/lib/kubelet'
HOST_ETC='/etc'
HOST_RUN='/run'
DEFAULT_DATA_DIR='/var/lib/rancher/k3s'
MODE=check
NODE_IP=''
DATA_DIR='/var/lib/rancher/k3s'
FIREWALL_POLICY=''
MANAGED=false

fail() { printf 'K3s preflight: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }
help() {
    cat <<'HELP'
Usage: bash scripts/setup-k3s.sh [--check | --apply] --node-ip PRIVATE_IPV4
                              --firewall-policy ufw-single-node
                              [--data-dir /absolute/directory]

Default/--check is strictly read-only: no downloads, temp files, sudo, service
changes or credential reads. Native Linux/systemd x86_64 only, never Android or
PRoot. Full inspection of protected paths and UFW requires running --check as
root explicitly. --apply also requires explicit root invocation; no sudo prompt
is hidden in this script. Reuse exactly the same flags on every invocation.

API binds ONLY the approved private node IP, never wildcard/public interfaces.
The dedicated UFW API allow is cni0-only. Tailscale's own netfilter rules may
additionally admit private peers: review tailnet ACLs/firewall integration.
Never add public API access. Prefer administering through private SSH:
  sudo /usr/local/bin/k3s kubectl --context default get nodes
No admin kubeconfig is copied to clients; node credentials remain mode 0600.
Node IP must be assigned RFC1918 LAN IPv4 or verified tailscale0 RFC6598 IPv4.
Pod/service networks are 10.42.0.0/16 and 10.43.0.0/16; Docker/kind stay untouched.

UFW must already be active, default deny incoming and allow outgoing, with:
  sudo ufw allow in on cni0 from 10.42.0.0/16 to any port 6443 proto tcp
  sudo ufw allow in on cni0 from 10.42.0.0/16 to any port 10250 proto tcp
  sudo ufw route allow in on cni0 from 10.42.0.0/16
Preserve private SSH before changing firewall policy. Broad inbound allows and
rules opening Kubernetes/NodePort ports are refused; see docs/k3s/ONBOARDING.md.
The script never changes/disables a firewall or lowers kubelet disk thresholds.
Root, kubelet and data filesystems each need >5% free plus a 1 GiB install reserve;
free inodes must exceed 5% plus 1000. A bulk drive cannot cure root disk pressure.
These gates retain the pinned K3s 5% disk eviction defaults (10% minimum reclaim).
Existing host swap is preserved: pinned K3s sets FailSwapOn=false. Need >=2 CPUs,
>=2 GiB total RAM and >=1 GiB currently available; no host swap/sysctl changes.

Pinned release: v1.36.5+k3s1 (single-server SQLite, built-in scheduler, CPU only).
An existing unowned/changed installation is NEVER adopted, upgraded or restarted.
An exact managed rerun performs no writes or restart; an inactive service needs
explicit operator review and `sudo systemctl start k3s`, not a rerun workaround.

Recovery/rollback (DESTRUCTIVE, never automatic): retain needed Job evidence and
back up SQLite + server token securely OUTSIDE Git before changes. Review the
installed /usr/local/bin/k3s-uninstall.sh. To DELETE the cluster, explicitly run:
  sudo env K3S_DATA_DIR=/chosen/data/path /usr/local/bin/k3s-uninstall.sh
Use the exact data-dir from installation (default /var/lib/rancher/k3s). Upstream
uninstall otherwise defaults to /var/lib/rancher/k3s, NOT the config's custom
directory. It removes data, credentials and service; it is not a version rollback
or backup. Its killall helper rewrites host-wide KUBE/CNI chains and Tailscale
advertised routes: review effects on Docker/kind/SSH in a maintenance window.
Restore backups only with their matching version/config; no in-place upgrades or
downgrades here. Remove only the three dedicated UFW rules manually if unused.
HELP
}

parse_args() {
    local selected=''
    while (($#)); do
        case "$1" in
            --help|-h) help; exit 0 ;;
            --check|--apply)
                [[ -z "$selected" || "$selected" == "$1" ]] || fail 'choose only one of --check and --apply'
                selected="$1"; MODE="${1#--}"; shift ;;
            --node-ip|--data-dir|--firewall-policy)
                (($# >= 2)) || fail "missing value for $1"
                case "$1" in
                    --node-ip) NODE_IP="$2" ;;
                    --data-dir) DATA_DIR="$2" ;;
                    --firewall-policy) FIREWALL_POLICY="$2" ;;
                esac
                shift 2 ;;
            *) fail "unknown argument: $1 (use --help)" ;;
        esac
    done
}

check_host() {
    [[ "$(uname -s)" == Linux ]] || fail 'native Linux/systemd required; phone and Mac are clients only'
    local kernel pid1 virtualization controllers memory_total=0 memory_available=0 key value rest
    kernel="$(uname -r)"
    [[ "${kernel,,}" != *android* && -z "${PROOT_TMP_DIR:-}${PROOT_LOADER:-}${ANDROID_ROOT:-}" ]] || fail 'Android/PRoot cannot host K3s; connect to the desktop over private SSH'
    [[ -r "$PROC_ROOT/1/comm" ]] || fail 'cannot inspect PID 1; native systemd required'
    read -r pid1 < "$PROC_ROOT/1/comm"
    [[ "$pid1" == systemd ]] || fail 'PID 1 is not systemd; containers/PRoot are not supported servers'
    [[ "$(uname -m)" == x86_64 ]] || fail 'this pinned bootstrap supports x86_64 desktops only'
    local command_name
    for command_name in systemctl systemd-detect-virt ip ss df getconf python3 sha256sum stat realpath curl install mktemp env ufw; do
        command -v "$command_name" >/dev/null 2>&1 || fail "missing prerequisite command: $command_name"
    done
    virtualization="$(systemd-detect-virt --container 2>/dev/null || true)"
    [[ -z "$virtualization" || "$virtualization" == none ]] || fail "container/PRoot environment unsupported: $virtualization"
    [[ "$(systemctl show --property=Version --value)" != '' ]] || fail 'cannot communicate with systemd'
    [[ -r "$CGROUP_ROOT/cgroup.controllers" ]] || fail 'unified cgroup v2 required'
    read -r controllers < "$CGROUP_ROOT/cgroup.controllers"
    for key in cpu memory pids; do
        [[ " $controllers " == *" $key "* ]] || fail "cgroup v2 controller missing: $key"
    done
    (($(getconf _NPROCESSORS_ONLN) >= 2)) || fail 'at least 2 CPUs required'
    while read -r key value rest; do
        case "$key" in
            MemTotal:) memory_total="$value" ;;
            MemAvailable:) memory_available="$value" ;;
        esac
    done < "$PROC_ROOT/meminfo"
    ((memory_total >= 2 * 1024 * 1024 && memory_available >= 1024 * 1024)) || fail 'need >=2 GiB RAM total and >=1 GiB currently available'
    local swap_lines=0
    while read -r rest; do swap_lines=$((swap_lines + 1)); done < "$PROC_ROOT/swaps"
    if ((swap_lines > 1)); then
        note 'Existing swap preserved; pinned K3s FailSwapOn=false supports host swap (no swapoff or host memory changes).'
    fi
}

check_disk() {
    local path="$1" label="$2" device total used available percent mountpoint output inspected=false
    while [[ ! -e "$path" ]]; do path="$(dirname -- "$path")"; done
    # Parse POSIX df output without locale-dependent headings or rounded percents.
    output="$(df -Pk -- "$path")" || fail "cannot inspect $label disk capacity"
    while read -r device total used available percent mountpoint; do
        [[ "$total" =~ ^[0-9]+$ ]] || continue
        ((total > 0 && available * 100 > total * 5 + 1024 * 1024 * 100)) || fail "$label disk pressure: need >5% free plus 1 GiB install reserve; free storage explicitly, never lower eviction thresholds"
        inspected=true
    done <<< "$output"
    [[ "$inspected" == true ]] || fail "cannot inspect $label disk capacity"
    inspected=false
    output="$(df -Pi -- "$path")" || fail "cannot inspect $label inode capacity"
    while read -r device total used available percent mountpoint; do
        [[ "$total" =~ ^[0-9]+$ ]] || continue
        if ((total == 0)) && [[ "$(stat -f -c %T -- "$path")" == btrfs ]]; then
            note "$label: Btrfs allocates inodes dynamically; no fixed inode percentage applies."
        else
            ((total > 0 && available * 100 > total * 5 + 1000 * 100)) || fail "$label inode pressure: need >5% free inodes plus 1000"
        fi
        inspected=true
    done <<< "$output"
    [[ "$inspected" == true ]] || fail "cannot inspect $label inode capacity"
}

check_paths() {
    [[ "$DATA_DIR" =~ ^/[a-zA-Z0-9_./-]+$ && "$DATA_DIR" != / ]] || fail 'data-dir must be an absolute path without whitespace or shell metacharacters'
    [[ "$(realpath -m -- "$DATA_DIR")" == "$DATA_DIR" ]] || fail 'data-dir must be canonical (no symlinks, trailing slash or ..)'
    local repo
    repo="$(realpath -- "$SCRIPT_DIR/..")"
    [[ "$DATA_DIR/" != "$repo/"* && "$DATA_DIR/" != "$CONFIG_DIR/"* && "$DATA_DIR" != /etc && "$DATA_DIR" != /usr && "$DATA_DIR" != /home && "$DATA_DIR" != /root ]] || fail 'data-dir must be dedicated runtime storage outside the checkout and system configuration'
    check_disk / 'root/nodefs'
    check_disk "$KUBELET_DIR" 'kubelet/nodefs'
    check_disk "$DATA_DIR" 'data/imagefs'
}

check_network() {
    [[ -n "$NODE_IP" ]] || fail 'choose --node-ip from an assigned private LAN/Tailscale IPv4; API binds only this address'
    # Only assigned RFC1918 LAN or verified RFC6598 Tailscale interfaces.
    # Inspect every route/table for pod/service CIDR collisions, including VPNs.
    FLANNEL_IFACE="$(python3 - "$NODE_IP" "$MANAGED" <<'PY'
import ipaddress
import shutil
import json
import re
import subprocess
import sys


def fail(message):
    sys.exit('K3s network preflight: ' + message)


try:
    node = ipaddress.IPv4Address(sys.argv[1])
except ValueError:
    fail('node-ip must be IPv4')
private = [ipaddress.ip_network(cidr) for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
tailnet = node in ipaddress.ip_network('100.64.0.0/10')
if not tailnet and not any(node in network for network in private):
    fail('node-ip must be RFC1918 LAN or verified RFC6598 Tailscale IPv4')
addresses = json.loads(subprocess.check_output(['ip', '-j', '-4', 'address', 'show'], text=True))
matches = [entry['ifname'] for entry in addresses for addr in entry.get('addr_info', []) if addr.get('local') == str(node)]
if len(matches) != 1 or not re.fullmatch(r'[A-Za-z0-9_.-]+', matches[0]):
    fail('node-ip must identify exactly one local interface')
iface = matches[0]
if tailnet:
    if iface != 'tailscale0' or not shutil.which('tailscale'):
        fail('RFC6598 address requires the local tailscale0 interface and tailscale CLI')
    assigned = subprocess.check_output(['tailscale', 'ip', '-4'], text=True).splitlines()
    if str(node) not in assigned:
        fail('node-ip is not verified by local tailscale ip -4')
elif iface.startswith(('lo', 'docker', 'br-', 'veth', 'cni', 'flannel', 'tailscale', 'virbr')):
    fail('choose a real LAN interface, not a container/VPN bridge')
networks = [ipaddress.ip_network(cidr) for cidr in ('10.42.0.0/16', '10.43.0.0/16')]
for entry in addresses:
    for addr in entry.get('addr_info', []):
        network = ipaddress.ip_network(f"{addr['local']}/{addr['prefixlen']}", strict=False)
        if any(network.overlaps(target) for target in networks):
            if sys.argv[2] == 'true' and entry['ifname'] in ('cni0', 'flannel.1'):
                continue
            fail('interface network overlaps pod/service CIDR: ' + str(network))
routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show', 'table', 'all'], text=True))
for route in routes:
    destination = route.get('dst', 'default')
    if destination == 'default':
        continue
    network = ipaddress.ip_network(destination, strict=False)
    if any(network.overlaps(target) for target in networks):
        if sys.argv[2] == 'true' and route.get('dev') in ('cni0', 'flannel.1'):
            continue
        fail('route overlaps pod/service CIDR: ' + str(network))
print(iface)
PY
    )" || fail 'network plan conflicts; review addresses/routes without changing Docker, kind or VPN'
}

check_firewall() {
    [[ "$FIREWALL_POLICY" == ufw-single-node ]] || fail 'explicit --firewall-policy ufw-single-node required; script never modifies the firewall'
    local firewall_service
    for firewall_service in firewalld.service nftables.service; do
        if systemctl is-active --quiet "$firewall_service"; then
            fail "conflicting firewall manager active: $firewall_service; review policy manually"
        fi
    done
    local status added
    status="$(LC_ALL=C ufw status verbose)" || fail 'cannot inspect UFW; run read-only --check explicitly as root'
    [[ "$status" == *'Status: active'* && "$status" == *'deny (incoming)'* && "$status" == *'allow (outgoing)'* ]] || fail 'require active UFW, default deny incoming and allow outgoing; preserve SSH and review docs first'
    added="$(LC_ALL=C ufw show added)" || fail 'cannot inspect UFW rules'
    UFW_ADDED="$added" python3 - <<'PY'
import os
import re
import subprocess
import shlex
import sys

rules = [shlex.split(line) for line in os.environ['UFW_ADDED'].splitlines() if line.startswith('ufw ')]
required = [
    shlex.split('ufw allow in on cni0 from 10.42.0.0/16 to any port 6443 proto tcp'),
    shlex.split('ufw allow in on cni0 from 10.42.0.0/16 to any port 10250 proto tcp'),
    shlex.split('ufw route allow in on cni0 from 10.42.0.0/16'),
]
# UFW moves the protocol option in `show added`. Normalize that pair only,
# preserving source/destination and interface associations. Ignore comments.
def normalized(rule):
    if 'comment' in rule:
        rule = rule[:rule.index('comment')]
    if rule.count('proto') == 1:
        index = rule.index('proto')
        if index + 1 < len(rule):
            rule = rule[:index] + rule[index + 2:] + rule[index:index + 2]
    return tuple(rule)

if not all(any(normalized(rule) == normalized(wanted) for rule in rules) for wanted in required):
    sys.exit('K3s firewall preflight: missing dedicated cni0 kubelet/forwarding rules; see --help')
protected = {6443, 6444, 8472, 10250, *range(30000, 32768)}
for rule in rules:
    if 'comment' in rule:
        rule = rule[:rule.index('comment')]
    if any(normalized(rule) == normalized(wanted) for wanted in required):
        continue
    if not any(action in rule for action in ('allow', 'limit')) or rule[2:3] == ['out']:
        continue
    if 'route' in rule:
        sys.exit('K3s firewall preflight: unrelated forwarding allow needs manual review')
    if rule in (['ufw', 'allow', 'OpenSSH'], ['ufw', 'limit', 'OpenSSH']):
        profile = subprocess.check_output(['ufw', 'app', 'info', 'OpenSSH'], text=True)
        if not re.search(r'\nPorts?:\s*22/tcp\s*$', profile):
            sys.exit('K3s firewall preflight: OpenSSH profile is not exclusively 22/tcp; review explicitly')
        continue
    # Explicit numeric destination ports only; an unknown app or broad source
    # allow can also expose the API, kubelet, VXLAN or NodePorts.
    try:
        if 'to' in rule:
            destination = rule[rule.index('to') + 1:]
            if len(destination) < 3 or destination[1] != 'port':
                raise ValueError()
            spec = destination[2]
        elif len(rule) == 3:
            spec = rule[2]
        else:
            raise ValueError()
        spec = spec.split('/')[0]
        ports = set()
        for part in spec.split(','):
            bounds = [int(value) for value in part.split(':')]
            if len(bounds) == 1:
                ports.add(bounds[0])
            elif len(bounds) == 2 and 1 <= bounds[0] <= bounds[1] <= 65535:
                ports.update(range(bounds[0], bounds[1] + 1))
            else:
                raise ValueError()
        if not ports or any(not 1 <= port <= 65535 for port in ports) or ports & protected:
            raise ValueError()
    except (ValueError, IndexError):
        sys.exit('K3s firewall preflight: broad/app/Kubernetes-port inbound allow needs manual review: ' + shlex.join(rule))
PY
}

render_config() {
    cat -- "$DEFAULTS" || return
    printf '\nbind-address: "%s"\nnode-ip: "%s"\nadvertise-address: "%s"\nflannel-iface: "%s"\ndata-dir: "%s"\n' "$NODE_IP" "$NODE_IP" "$NODE_IP" "$FLANNEL_IFACE" "$DATA_DIR" || return
    # Kubelet binds only the approved private IP, not wildcard/public interfaces.
    printf 'kubelet-arg:\n  - "address=%s"\n' "$NODE_IP"
}

hash_file() { sha256sum -- "$1" | { read -r digest rest; printf '%s' "$digest"; }; }

check_existing() {
    local load_state path
    load_state="$(systemctl show k3s.service --property=LoadState --value)" || fail 'cannot inspect existing service'
    if [[ -e "$STATE_FILE" ]]; then
        [[ -f "$STATE_FILE" && ! -L "$STATE_FILE" && "$(stat -c '%u:%a' "$STATE_FILE")" == '0:600' ]] || fail 'managed state must be a root-owned regular mode-0600 file'
        MANAGED=true
    else
        [[ "$load_state" == not-found ]] || fail 'unowned k3s service exists; refusing adoption/restart'
        for path in "$CONFIG_DIR" "$DATA_DIR" "$DEFAULT_DATA_DIR" "$KUBELET_DIR" "$BIN_DIR/k3s" "$BIN_DIR/k3s-uninstall.sh" "$SERVICE_DIR/k3s.service" "$SERVICE_DIR/k3s.service.env" "$HOST_ETC/rancher/rke2" "$HOST_ETC/kubernetes"; do
            [[ ! -e "$path" && ! -L "$path" ]] || fail "unowned cluster/config/runtime exists at $path; refusing overwrite/adoption"
        done
        ! command -v k3s >/dev/null 2>&1 || fail 'an unowned k3s binary is already on PATH'
    fi
    for path in "$CONFIG_DIR/config.yaml.d" "$SERVICE_DIR/k3s.service.d" "$HOST_RUN/systemd/system/k3s.service" "$HOST_RUN/systemd/system/k3s.service.d" "$HOST_ETC/default/k3s" "$HOST_ETC/sysconfig/k3s"; do
        [[ ! -e "$path" && ! -L "$path" ]] || fail "external configuration override at $path; review manually"
    done
    [[ "$(systemctl show k3s-agent.service --property=LoadState --value)" == not-found ]] || fail 'existing K3s agent service; refusing a second role'
}

verify_managed() {
    local key value config_digest binary_version
    declare -A state=()
    while IFS='=' read -r key value; do
        case "$key" in
            format|version|node_ip|data_dir|config_sha256|binary_sha256|service_sha256|env_sha256|installer_sha256)
                [[ -z "${state[$key]+present}" ]] || fail 'duplicate managed-state field'
                state["$key"]="$value" ;;
            *) fail 'unknown managed-state field; manual review required' ;;
        esac
    done < "$STATE_FILE"
    ((${#state[@]} == 9)) || fail 'incomplete managed state; do not adopt a partial install'
    [[ "${state[format]}" == 1 && "${state[version]}" == "$K3S_VERSION" && "${state[node_ip]}" == "$NODE_IP" && "${state[data_dir]}" == "$DATA_DIR" && "${state[installer_sha256]}" == "$INSTALLER_SHA256" && "${state[binary_sha256]}" == "$BINARY_SHA256" ]] || fail 'managed settings/version conflict; review explicitly, no automatic upgrade or reconfiguration'
    config_digest="$(render_config | sha256sum)"; config_digest="${config_digest%% *}"
    [[ "${state[config_sha256]}" == "$config_digest" ]] || fail 'repository configuration changed since install; manual migration required'
    for key in config binary service env; do
        local path
        case "$key" in
            config) path="$CONFIG_DIR/config.yaml" ;;
            binary) path="$BIN_DIR/k3s" ;;
            service) path="$SERVICE_DIR/k3s.service" ;;
            env) path="$SERVICE_DIR/k3s.service.env" ;;
        esac
        [[ -f "$path" && ! -L "$path" && "$(stat -c %u "$path")" == 0 ]] || fail "missing/unsafe managed $key file"
        [[ "$(hash_file "$path")" == "${state[${key}_sha256]}" ]] || fail "managed $key changed; refusing overwrite/restart"
    done
    [[ "$(stat -c %a "$CONFIG_DIR/config.yaml")" == 600 ]] || fail 'managed config permissions changed'
    binary_version="$("$BIN_DIR/k3s" --version)"
    [[ "$binary_version" == "k3s version $K3S_VERSION "* ]] || fail 'installed K3s version conflicts with pin'
    [[ "$(systemctl show k3s.service --property=FragmentPath --value)" == "$SERVICE_DIR/k3s.service" && -z "$(systemctl show k3s.service --property=DropInPaths --value)" ]] || fail 'service fragment/overrides changed'
    systemctl is-active --quiet k3s.service || fail 'matching managed service is inactive; review journal privately, then explicitly start it (rerun never restarts)'
    systemctl is-enabled --quiet k3s.service || fail 'matching managed service is not enabled; review manually'
    for path in "$CONFIG_DIR/k3s.yaml" "$DATA_DIR/server/token" "$DATA_DIR/server/node-token"; do
        [[ -e "$path" ]] || fail "managed credential missing: $path"
        # node-token can be the upstream symlink to token; only inspect metadata.
        [[ "$(stat -Lc '%u:%a' "$path")" == '0:600' ]] || fail "credential permissions unsafe: $path (expected root:0600)"
    done
}

check_ports_and_kind() {
    local sockets line port
    if [[ "$MANAGED" == false ]]; then
        sockets="$(ss -H -lntu)" || fail 'cannot inspect listening ports'
        while read -r line; do
            for port in 6443 6444 10250 8472; do
                [[ ! "$line" =~ :${port}[[:space:]] ]] || fail "required port $port is already listening; existing services untouched"
            done
        done <<< "$sockets"
    fi
    if command -v kind >/dev/null 2>&1; then
        local clusters
        clusters="$(kind get clusters)" || fail 'cannot inspect kind clusters; restore current Docker access, do not remove kind'
        [[ -z "$clusters" ]] || note "Existing kind clusters preserved: ${clusters//$'\n'/, }"
    fi
}

write_state() {
    local config_digest
    config_digest="$(hash_file "$CONFIG_DIR/config.yaml")"
    {
        printf 'format=1\nversion=%s\nnode_ip=%s\ndata_dir=%s\n' "$K3S_VERSION" "$NODE_IP" "$DATA_DIR"
        printf 'config_sha256=%s\nbinary_sha256=%s\n' "$config_digest" "$BINARY_SHA256"
        printf 'service_sha256=%s\nenv_sha256=%s\ninstaller_sha256=%s\n' "$(hash_file "$SERVICE_DIR/k3s.service")" "$(hash_file "$SERVICE_DIR/k3s.service.env")" "$INSTALLER_SHA256"
    } > "$STATE_FILE"
    chmod 600 "$STATE_FILE"
}

apply_install() {
    local staging installer_url binary_url lock_fd config_staging
    # Never put an installer, binary, credentials or logs in the checkout.
    umask 077
    command -v flock >/dev/null 2>&1 || fail 'explicit install requires flock (util-linux)'
    exec {lock_fd}>"$HOST_RUN/dotfiles-k3s.lock"
    flock --nonblock "$lock_fd" || fail 'another explicit bootstrap is running; no concurrent installation'
    # Close the fresh-install race without adopting a partial/foreign install.
    check_existing
    if [[ "$MANAGED" == true ]]; then
        verify_managed
        note "Matching managed $K3S_VERSION appeared while waiting; no install or restart."
        return
    fi
    staging="$(mktemp -d /var/tmp/dotfiles-k3s.XXXXXXXX)"
    trap "rm -rf -- '$staging'" EXIT
    installer_url="https://raw.githubusercontent.com/k3s-io/k3s/$INSTALLER_COMMIT/install.sh"
    binary_url="https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION/+/%2B}/k3s"
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --output "$staging/install.sh" "$installer_url"
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 --output "$staging/k3s" "$binary_url"
    printf '%s  %s\n%s  %s\n' "$INSTALLER_SHA256" "$staging/install.sh" "$BINARY_SHA256" "$staging/k3s" | sha256sum --check --status || fail 'official installer/binary checksum mismatch; nothing installed'
    # Render successfully before creating host config/runtime directories.
    render_config > "$staging/config.yaml" || fail 'cannot stage configuration; nothing installed'
    # No K3S_URL/token/proxy or other caller environment can leak into the service.
    install -d -m 700 "$CONFIG_DIR" "$DATA_DIR"
    config_staging="$(mktemp "$CONFIG_DIR/.config.yaml.XXXXXXXX")"
    install -o 0 -g 0 -m 600 "$staging/config.yaml" "$config_staging"
    mv -T -- "$config_staging" "$CONFIG_DIR/config.yaml"
    install -m 755 "$staging/k3s" "$BIN_DIR/k3s"
    env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
        INSTALL_K3S_VERSION="$K3S_VERSION" INSTALL_K3S_SKIP_DOWNLOAD=true \
        INSTALL_K3S_SYMLINK=skip INSTALL_K3S_SKIP_ENABLE=true INSTALL_K3S_SKIP_START=true \
        INSTALL_K3S_BIN_DIR="$BIN_DIR" INSTALL_K3S_SYSTEMD_DIR="$SERVICE_DIR" \
        sh "$staging/install.sh" server --config "$CONFIG_DIR/config.yaml"
    # Ownership survives startup/readiness failure: reruns must not adopt or
    # restart a partial installation. Recovery requires explicit operator review.
    write_state
    systemctl enable --now k3s.service
    # Do not print or collect kubeconfigs/tokens. Metadata and API health only.
    local attempt
    for ((attempt=0; attempt<60; attempt++)); do
        if "$BIN_DIR/k3s" kubectl --kubeconfig "$CONFIG_DIR/k3s.yaml" get --raw=/readyz >/dev/null 2>&1; then
            # K3s upstream may create node-token as 0644; require the stricter
            # policy locally, without ever reading the credential contents.
            chmod 600 "$CONFIG_DIR/k3s.yaml" "$DATA_DIR/server/token" "$DATA_DIR/server/node-token"
            verify_managed
            note "Installed $K3S_VERSION; private API ready. Use sudo $BIN_DIR/k3s kubectl --context default get nodes."
            return
        fi
        sleep 2
    done
    fail 'service installed but API not ready after 120s; review sudo journalctl -u k3s locally (may contain secrets); no automatic rollback/restart'
}

main() {
    parse_args "$@"
    check_host
    check_paths
    # No sudo, not even sudo -n: privilege is a visible operator decision.
    [[ "$(id -u)" == 0 ]] || fail 'full read-only inspection needs root; explicitly run sudo bash scripts/setup-k3s.sh --check with the same flags (no escalation attempted)'
    check_existing
    check_network
    check_firewall
    check_ports_and_kind
    if [[ "$MANAGED" == true ]]; then
        verify_managed
        note "Matching managed $K3S_VERSION is active; no changes, downloads or restart."
    elif [[ "$MODE" == apply ]]; then
        apply_install
    else
        note "Preflight passed for $K3S_VERSION. Read-only: no changes made. Explicit --apply with these same flags is required to install."
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
