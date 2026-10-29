#!/usr/bin/env bash
# Opt-in K3s setup for the fleet. Never run by ./scripts/onboard.
#
#   sudo scripts/setup-k3s.sh server        install/refresh the server on this host (desktop)
#   sudo scripts/setup-k3s.sh gpu           enable NVIDIA containers + device plugin on this node
#   sudo scripts/setup-k3s.sh agent <ip>    join this host as an agent of the server at <ip>
#        scripts/setup-k3s.sh apply         apply config/k3s/manifests (as the desktop user)
#   sudo scripts/setup-k3s.sh firewall [server|agent]  open k3s ports on tailscale0 only (ufw)
#        scripts/setup-k3s.sh admit <node>  prove isolation on a new node, then let it take work
#        scripts/setup-k3s.sh kueue         install pinned Kueue + config/k3s/kueue queues (as the desktop user)
#        scripts/setup-k3s.sh status        node, pod and GPU status
#        scripts/setup-k3s.sh check         offline validation of this script and manifests
#   sudo scripts/setup-k3s.sh uninstall --yes
#
# Re-running server/agent/gpu is safe: same version + same config = no restart.
set -euo pipefail

K3S_VERSION="${K3S_VERSION:-v1.37.1+k3s1}"
# Bump both together; the hash is of the release's manifests.yaml.
KUEUE_VERSION=v0.20.2
KUEUE_SHA256=1ab14ecd590575ac57f50fa4cbcf529766bc2c32ba974bda1614381281ec52b4
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="$REPO/config/k3s"
ETC=/etc/rancher/k3s
# Cluster data (images, sqlite) stays off the root disk when /workspace exists.
if [ -d /workspace ]; then K3S_DATA="${K3S_DATA:-/workspace/k3s-data}"; else K3S_DATA="${K3S_DATA:-/var/lib/rancher/k3s}"; fi

die() { echo "setup-k3s: $*" >&2; exit 1; }
say() { echo "==> $*"; }
need_root() { [ "$(id -u)" -eq 0 ] || die "run with sudo"; }
desktop_user() { echo "${SUDO_USER:-$USER}"; }

ts_ip() {
  local ip
  ip=$(tailscale ip -4 2>/dev/null | head -1)
  [ -n "$ip" ] || die "tailscale is not up (no tailnet IPv4)"
  echo "$ip"
}

preflight() {
  command -v systemctl >/dev/null || die "systemd required"
  [ -f /sys/fs/cgroup/cgroup.controllers ] || die "cgroup v2 required"
  ip link show tailscale0 >/dev/null 2>&1 || die "tailscale0 interface missing"
  command -v curl >/dev/null || die "curl required"
}

# Render a config template; install it only when it changed. Prints "changed" or "same".
install_config() {
  local tmpl=$1 out=$ETC/config.yaml tmp
  tmp=$(mktemp)
  sed -e "s/@TS_IP@/$(ts_ip)/g" -e "s/@HOSTNAME@/$(hostname)/g" \
      -e "s/@SERVER_IP@/${SERVER_IP:-}/g" -e "s|@K3S_DATA@|$K3S_DATA|g" "$tmpl" >"$tmp"
  install -d -m 0755 $ETC
  if [ -f $out ] && cmp -s "$tmp" $out; then rm -f "$tmp"; echo same; return; fi
  [ -f $out ] && cp -a $out "$out.bak.$(date +%Y%m%d%H%M%S)"
  install -m 0600 "$tmp" $out; rm -f "$tmp"; echo changed
}

installed_version() { k3s --version 2>/dev/null | awk 'NR==1{print $3}'; }

# Official installer, pinned version; it verifies the binary's sha256 itself.
run_installer() {
  local exec=$1 dl
  dl=$(mktemp -d)
  curl -fsSL https://get.k3s.io -o "$dl/install.sh"
  INSTALL_K3S_VERSION="$K3S_VERSION" INSTALL_K3S_EXEC="$exec" sh "$dl/install.sh"
  rm -rf "$dl"
}

cmd_server() {
  need_root; preflight; open_firewall server
  local changed svc=k3s
  changed=$(install_config "$CFG/server.yaml")
  if [ "$(installed_version)" != "$K3S_VERSION" ]; then
    say "installing k3s $K3S_VERSION (server)"; run_installer server
  elif [ "$changed" = changed ]; then
    say "config changed; restarting $svc"; systemctl restart $svc
  else
    say "k3s $K3S_VERSION already installed, config unchanged"
  fi
  systemctl enable --now $svc >/dev/null
  # Owner-only kubeconfig for the desktop user. Never commit it.
  local u home; u=$(desktop_user); home=$(getent passwd "$u" | cut -d: -f6)
  install -d -m 0700 -o "$u" "$home/.kube"
  install -m 0600 -o "$u" $ETC/k3s.yaml "$home/.kube/k3s.yaml"
  say "kubeconfig: $home/.kube/k3s.yaml  (export KUBECONFIG=\$HOME/.kube/k3s.yaml)"
  say "join token (root-only): ${K3S_DATA}/server/node-token"
}

# Cluster traffic is allowed on tailscale0 only: API (server), kubelet, flannel VXLAN.
# ufw ignores rules it already has, so re-running is a no-op.
open_firewall() {
  command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q '^Status: active' || return 0
  local role=$1
  [ "$role" = server ] && ufw allow in on tailscale0 to any port 6443 proto tcp comment k3s-api >/dev/null
  ufw allow in on tailscale0 to any port 10250 proto tcp comment k3s-kubelet >/dev/null
  ufw allow in on tailscale0 to any port 8472 proto udp comment k3s-flannel >/dev/null
  say "ufw: k3s ports open on tailscale0 ($role)"
}

cmd_agent() {
  need_root; preflight; open_firewall agent
  SERVER_IP=${1:-}; [ -n "$SERVER_IP" ] || die "usage: setup-k3s.sh agent <server-tailnet-ip>"
  [ -s $ETC/join-token ] || die "copy the server's node-token to $ETC/join-token (mode 0600) first"
  chmod 0600 $ETC/join-token
  local changed; changed=$(install_config "$CFG/agent.yaml")
  if [ "$(installed_version)" != "$K3S_VERSION" ]; then
    say "installing k3s $K3S_VERSION (agent)"; run_installer agent
  elif [ "$changed" = changed ]; then
    systemctl restart k3s-agent
  else
    say "agent already installed, config unchanged"
  fi
  systemctl enable --now k3s-agent >/dev/null
}

cmd_gpu() {
  need_root
  command -v nvidia-smi >/dev/null || die "NVIDIA driver not found"
  if ! command -v nvidia-ctk >/dev/null; then
    say "installing nvidia-container-toolkit"; pacman -S --needed --noconfirm nvidia-container-toolkit
  fi
  # K3s detects the nvidia runtime on start and writes it into its containerd config.
  local svc=k3s; systemctl is-active -q k3s || svc=k3s-agent
  if ! grep -q nvidia ${K3S_DATA}/agent/etc/containerd/config.toml 2>/dev/null; then
    say "restarting $svc so containerd picks up the nvidia runtime"; systemctl restart $svc
  fi
  grep -q nvidia ${K3S_DATA}/agent/etc/containerd/config.toml || die "nvidia runtime not detected by k3s"
  say "nvidia runtime registered; now run: scripts/setup-k3s.sh apply"
}

kc() { KUBECONFIG="${KUBECONFIG:-$HOME/.kube/k3s.yaml}" kubectl "$@"; }

cmd_apply() {
  [ "$(id -u)" -ne 0 ] || die "run apply as your user, not root"
  kc apply -f "$CFG/manifests/"
  kc -n kube-system rollout status ds/nvidia-device-plugin --timeout=180s || true
}

cmd_kueue() {
  [ "$(id -u)" -ne 0 ] || die "run kueue as your user, not root"
  local tmp; tmp=$(mktemp); trap 'rm -f "$tmp"' RETURN
  curl -fsSL "https://github.com/kubernetes-sigs/kueue/releases/download/$KUEUE_VERSION/manifests.yaml" -o "$tmp"
  echo "$KUEUE_SHA256  $tmp" | sha256sum -c --quiet - || die "kueue $KUEUE_VERSION manifest hash mismatch"
  kc apply --server-side --force-conflicts -f "$tmp" >/dev/null
  kc -n kueue-system rollout status deploy/kueue-controller-manager --timeout=300s
  # The admission webhook can lag the rollout by a few seconds.
  local i; for i in 1 2 3 4 5 6; do kc apply -f "$CFG/kueue/" && return 0; sleep 10; done
  die "kueue queues did not apply"
}

# Run the isolation smoke pinned to <node> (tolerating the onboarding taint) and
# remove the taint only when it prints ISOLATION_OK. Retries while the node's
# policy controller finishes its first sync. Safe to re-run.
cmd_admit() {
  [ "$(id -u)" -ne 0 ] || die "run admit as your user, not root"
  local node=${1:-}; [ -n "$node" ] || die "usage: setup-k3s.sh admit <node>"
  kc wait --for=condition=Ready "node/$node" --timeout=300s >/dev/null
  local i job spec
  for i in 1 2 3 4 5; do
    spec=$(python3 - "$CFG/smoke/isolation-job.yaml" "$node" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
s = d["spec"]["template"]["spec"]
s["nodeSelector"] = {"kubernetes.io/hostname": sys.argv[2]}
s["tolerations"] = [{"key": "z0.dev/onboarding", "operator": "Exists", "effect": "NoSchedule"}]
print(yaml.safe_dump(d))
PY
)
    job=$(echo "$spec" | kc create -f - -o name)
    kc -n factory wait --for=condition=complete "$job" --timeout=150s >/dev/null 2>&1 || true
    if kc -n factory logs "$job" 2>/dev/null | grep -qx ISOLATION_OK; then
      kc taint node "$node" z0.dev/onboarding- >/dev/null 2>&1 || true
      say "$node admitted: ISOLATION_OK on attempt $i"; return 0
    fi
    say "$node: isolation not enforced yet (attempt $i), retrying in 20s"; sleep 20
  done
  kc -n factory logs "$job" || true
  die "$node stays tainted: isolation failed"
}

cmd_status() {
  kc get nodes -o wide
  kc get pods -A
  kc get nodes -o custom-columns='NODE:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
}

cmd_check() {
  bash -n "$0" && say "script syntax ok"
  for f in "$CFG"/manifests/*.yaml "$CFG"/smoke/*.yaml "$CFG"/kueue/*.yaml; do
    python3 -c 'import sys,yaml; list(yaml.safe_load_all(open(sys.argv[1])))' "$f" || die "bad yaml: $f"
  done
  say "manifests parse"
  python3 "$REPO/services/phone-queue/render-configmap" --check
  if kc version >/dev/null 2>&1; then kc apply --dry-run=server -f "$CFG/manifests/" >/dev/null && say "server dry-run ok"; fi
}

cmd_uninstall() {
  need_root
  [ "${1:-}" = "--yes" ] || die "this deletes the cluster and its data; re-run with --yes"
  if [ -x /usr/local/bin/k3s-uninstall.sh ]; then /usr/local/bin/k3s-uninstall.sh; fi
  if [ -x /usr/local/bin/k3s-agent-uninstall.sh ]; then /usr/local/bin/k3s-agent-uninstall.sh; fi
}

case "${1:-}" in
  server) cmd_server ;;
  agent) shift; cmd_agent "$@" ;;
  gpu) cmd_gpu ;;
  apply) cmd_apply ;;
  kueue) cmd_kueue ;;
  admit) shift; cmd_admit "$@" ;;
  firewall) need_root; open_firewall "${2:-server}" ;;
  status) cmd_status ;;
  check) cmd_check ;;
  uninstall) shift; cmd_uninstall "$@" ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
