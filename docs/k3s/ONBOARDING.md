# One private, CPU-only K3s server

Implements [.files #23](https://github.com/kvnloo/.files/issues/23), sharing identities with [Factory #127 / PR #128](https://github.com/kvnloo/oss-factory/pull/128). This is opt-in machine setup, not a scheduler, worker-claim service, GitOps deployment, or authorization source. Factory retains global six-worker claims, registry, work orders and HITL. A manifest annotation is **not** a claim or permission for an upstream action.

| Start here | Role | Install locally? |
| --- | --- | --- |
| [S25 Ultra](#phone-first) | Existing OmaLauncher → Tern/OMP controller | **No** K3s, root, systemd, Home Manager or Termux requirement |
| [Groot desktop](#desktop-server) | CachyOS single server, SQLite, built-in scheduler | Explicit approval only |
| [MacBook](#macbook-client) | CachyOS/Arch SSH/client tools | Client only, no join |
| [Second PC](#optional-worker-later) | Deferred CPU capacity experiment | Agent only, later |

**Live acceptance is not complete (2026-10-16).** The last private desktop inspection found an enabled, active K3s `v1.37.1+k3s1` service without this implementation's `.dotfiles-managed` marker. It differs from the `v1.36.5+k3s1` pin and has not been accepted as this issue's managed deployment. **Do not adopt, restart, replace, uninstall, or count it as acceptance without owner-approved investigation.** The earlier storage blocker has cleared, but privileged authentication and an approved K3s context remain unavailable; the existing user context is for kind. Node health, CPU Job logs, quota, network isolation and TTL cleanup are unverified. Host addresses, capacity snapshots and runtime evidence remain private; see the current status on [issue #23](https://github.com/kvnloo/.files/issues/23). Discover and preserve any dirty desktop checkout rather than resetting or pulling over it. No broad cleanup, Docker/kind pruning, swap changes or reduced eviction thresholds are authorized.

## Phone first

Use the **existing** Tern/OMP shell in OmaLauncher's Arch ARM/proot environment. Do not install another terminal or attempt K3s inside Android/proot.

```sh
command -v git
command -v ssh
# In an existing checkout, inspect its remote instead of cloning over it:
git remote -v
# Only if a checkout does not yet exist, choose a user-owned path:
git clone https://github.com/kvnloo/.files.git
```

Review the implementation branch/commit supplied by the setup session before executing scripts. Keep Android Tailscale signed in; inspect its device list/admin-approved MagicDNS name and compare with Tern's saved Hosts picker. An Android VPN does not imply the proot guest has the Tailscale CLI: `tailscale status` is optional when installed. Preserve saved host-key pins; do not disable checking or replace keys to make a failed connection pass.

If key-auth SSH is actually provisioned, set the **discovered** endpoint, then verify desktop identity:

```sh
: "${DESKTOP:?Set DESKTOP to the private hostname verified in Tern/Tailscale}"
ssh "kvn@$DESKTOP" 'hostname; id; pwd'
```

If SSH fails, stop that path without changing the host or copying admin credentials. The **proven alternative** is Tern's existing **Hosts** picker → saved desktop connection → a desktop terminal/OMP session. Commands below execute in that desktop session; `hostname` must identify `groot`, not the phone. This uses existing Tern authentication, not an assertion that SSH worked. Provisioning a new SSH key/host policy requires normal host-side approval; retain the working Tern connection while doing so.

Discover the actual desktop checkout (`pwd`, `git remote -v`); do not assume the phone's path or silently create a second checkout. In that directory:

```sh
./scripts/onboard status --json
./scripts/onboard doctor
bash scripts/setup-k3s.sh --help
```

For a confirmed checkout at `~/workspace/.files`, the SSH equivalent is:

```sh
ssh "kvn@$DESKTOP" 'cd ~/workspace/.files && ./scripts/onboard status --json && ./scripts/onboard doctor && bash scripts/setup-k3s.sh --help'
```

These are preliminary nonmutating onboarding/usage checks, **not** the K3s prerequisite preflight. The actual privileged read-only `--check` requires explicit desktop authentication, a discovered node IP and firewall policy; run the complete command in [Desktop server](#desktop-server) only after its storage/network review. Do not invoke sudo on the phone. Stop on missing connectivity or failed gates. Phone-first completion means remote status, intentional **approved** bootstrap, node status and retained smoke logs can all be read from the phone—not that this repository has deployed anything already.

## Desktop server

Normal `./install`, `onboard --all`, existing Home Manager profiles and working desktop services remain unchanged. Reuse existing onboarding status; `nix-home` and `tailnet-ssh` are optional, separately approved modules, not prerequisites for using bundled K3s kubectl.

1. Review `config/k3s/config.yaml` and `scripts/setup-k3s.sh`. Bootstrap pins **v1.36.5+k3s1**, verifies upstream installer/release assets, supports native systemd CachyOS x86_64 only, and refuses unsafe existing state. SQLite and the built-in scheduler remain; Traefik/ServiceLB are disabled because the desktop already uses port 443. Docker/kind remain independent; do not change their contexts or prune their storage.
2. Review storage **with the owner**, keeping the pinned K3s release's defaults rather than assuming upstream kubelet defaults. Its nodefs/imagefs hard-eviction thresholds are both **5%**, with **10% minimum reclaim**; bootstrap requires root/kubelet and the selected data filesystem each remain above 5% free with at least 1 GiB reserve, plus 5% free inodes and 1,000 available inodes. Recheck actual capacity immediately before applying; free bulk storage does not exempt `/var/lib/kubelet` or root. An explicitly approved dedicated path can use `--data-dir /workspace/k3s` on a separately verified persistent filesystem. For a fresh install the directory must **not already exist**; inspect its parent mount, ownership and backups first. Pinned K3s sets `FailSwapOn=false`: preserve existing swap, never run swapoff to satisfy a fabricated prerequisite. Bootstrap requires at least 2 CPUs, 2 GiB total RAM and 1 GiB available RAM.

   Fixed-inode filesystems must satisfy both the inode percentage and reserve gates. Btrfs dynamically allocates inodes and can report zero inode totals: bootstrap explicitly detects Btrfs and reports the percentage as not applicable while still enforcing byte-space gates.
3. Discover the desktop's assigned private IPv4 (`ip -4 addr` and `ip route`); choose its actual RFC1918 LAN address or an RFC6598 address in `100.64.0.0/10` assigned to **tailscale0 and confirmed by `tailscale ip -4`** for `NODE_IP`. Never use a public/unassigned address. Pod/service defaults are `10.42.0.0/16` and `10.43.0.0/16`; resolve conflicts with existing Docker/kind/LAN/VPN networks first. The API is **bound and advertised only at approved private `NODE_IP:6443`**, never wildcard/public. The required API allow rule is cni0-only; no remote API rule is added. **Do not infer tailnet isolation from UFW:** Tailscale-managed netfilter chains can accept traffic before UFW. Review tailnet ACLs and actual netfilter ordering; private peers may reach the endpoint but still require TLS credentials. Loopback-only binding with a private advertise address breaks the in-cluster Kubernetes Service, so it is not used. Never add remote/public 6443/6444/10250, VXLAN UDP 8472 or NodePort 30000–32767 firewall rules.
4. UFW is not disabled or automatically edited. Preserve working private SSH/Tern access and inspect existing numeric/profile rules **before** approving any change. The supported single-node policy requires active UFW, deny incoming/allow outgoing and these narrow rules:

   ```sh
   # Operator-approved host policy changes ONLY; never blindly reset UFW.
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow in on cni0 from 10.42.0.0/16 to any port 10250 proto tcp
   sudo ufw allow in on cni0 from 10.42.0.0/16 to any port 6443 proto tcp
   sudo ufw route allow in on cni0 from 10.42.0.0/16
   sudo ufw status verbose
   sudo ufw show added
   ```

   Bootstrap rejects broad inbound allows/protected port exposure and unknown application profiles requiring review. `OpenSSH` is accepted only after `ufw app info OpenSSH` confirms it contains exclusively `22/tcp`; never trust an application profile name alone. Existing host services may need operator-approved narrower rules; do not remove working rules merely to pass a check. UFW forwarding permits cluster networking; the worker namespace's enforcing K3s NetworkPolicy controller must still deny worker traffic. Default-deny policy existence alone proves nothing.
5. After storage/network review, inspect privileged **read-only** preflight using a real host password/authorized root session. No passwordless-sudo bypass:

   ```sh
   NODE_IP=<discovered-private-desktop-ipv4>
   sudo bash scripts/setup-k3s.sh --check --node-ip "$NODE_IP" --firewall-policy ufw-single-node
   # Only after explicit host-side installation approval:
   sudo bash scripts/setup-k3s.sh --apply --node-ip "$NODE_IP" --firewall-policy ufw-single-node
   ```

   Add the same approved `--data-dir` to both commands if changing storage. `--check` verifies installation prerequisites, including download/staging tools, but does not use them to download or write. Fresh apply verifies both downloaded assets and renders configuration in private staging before creating host config/runtime directories; the root-owned mode-0600 config is published by a same-directory atomic rename. A staging/write failure stops before installer execution or service startup; no automatic host-state cleanup or adoption is attempted. Repeat `--check` after setup; repeated `--apply` with unchanged managed state is idempotent, not a reinstall. Changed/foreign state must be inspected; do not overwrite another cluster to force convergence.

### Access and manifests

Keep `/etc/rancher/k3s/k3s.yaml` mode **0600 on the desktop**. Keep node tokens, kubeconfigs, registry/GitHub credentials, auth keys and runtime evidence **outside Git**. Prefer bundled kubectl over private SSH/Tern; do not copy cluster-admin kubeconfig to Android or MacBook. No public API listener is needed.

```sh
sudo /usr/local/bin/k3s kubectl --context default get nodes -o wide
sudo /usr/local/bin/k3s kubectl --context default apply --dry-run=server -f config/k3s/manifests/boundary.json
sudo /usr/local/bin/k3s kubectl --context default apply -f config/k3s/manifests/boundary.json
sudo /usr/local/bin/k3s kubectl --context default create --dry-run=server -f config/k3s/manifests/cpu-example-job.json
```

`boundary.json` reuses Factory's `oss-factory-jobs`, `oss-factory-worker`, `worker-guardrail` and `deny-all-worker-traffic`; do not apply a competing identity set. ResourceQuota **`pods: 6` counts nonterminal Pods**, unlike `count/pods`; finished Jobs retain a separate `count/jobs.batch: 64` cap. Quota is defense in depth, never global claim authority. LimitRange defaults/caps do not replace per-Job bounds. The service account has no granted RBAC and token automount is off. Namespace PSA is `restricted` and both ingress and egress default-deny, including DNS/API access. Untrusted upstream code requires stronger isolation (a separate VM/host); these Pods are not a sandbox guarantee.

### Bounded smoke and evidence

Dependencies: desktop Python 3, Git and working bundled kubectl. Reserve a **quiet namespace maintenance window**: the helper refuses existing nonterminal Pods, does not evict workers, and cannot prevent a concurrently starting dispatcher. Pause submissions through the existing Factory authority first; do not create another worker lease.

The helper requires **`--context`**, even for bundled K3s; it never uses an accidental kind/default context. `--kubectl` accepts a single executable path, not a shell string. Create a private local wrapper outside Git:

```sh
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/k3s-kubectl-private" <<'SH'
#!/bin/sh
exec sudo /usr/local/bin/k3s kubectl "$@"
SH
chmod 700 "$HOME/.local/bin/k3s-kubectl-private"
sudo -v  # deliberate desktop authentication; never put the password in a command
mkdir -p "$HOME/.local/state/k3s-smoke"
umask 077
set -o pipefail
bash scripts/smoke-k3s.sh --context default --kubectl "$HOME/.local/bin/k3s-kubectl-private" \
  | tee "$HOME/.local/state/k3s-smoke/$(date -u +%Y%m%dT%H%M%SZ).jsonl"
```

Use an authenticated desktop terminal, including one opened from the phone's Tern session. For working key-auth SSH, open a private interactive session (`ssh -t "kvn@$DESKTOP"`) and run the **same desktop commands**. Do not stream a sudo password, export an admin kubeconfig, or treat a failed connection as execution evidence. Wrapper sudo timestamps can expire; if privilege reauthentication interrupts a run, retain failure evidence and inspect only named leftovers before another approved attempt.

Each invocation uses new names: it **creates**, never silently reapplies an immutable/completed example Job. It:

- Records source commit, dirty-checkout flag, exact SHA256 of script/manifests and explicit context. A dirty checkout is evidence of a dirty checkout, **not** proof the commit contains those bytes.
- Verifies the live shared ResourceQuota **and LimitRange**, restricted namespace label, token-free service account and default-deny policy before creating probes. Missing or drifted limits invalidate the run.
- Holds six scheduling-gated nonterminal Pods and requires the seventh Pod's admission to fail specifically on `worker-guardrail` Pod quota; it then deletes only its six named probes.
- Creates bounded non-root server/client Pods with **temporary narrowly selected ingress and egress allow policies**, proves a real TCP connection, then tests each direction independently while the other direction remains allowed. Each negative control requires timed-out connections to the still-running server; restoring the scoped allowance must restore connectivity. This tests same-namespace TCP denial, not every protocol, external destination or arbitrary malicious code. Unexpected allow policies/CNI behavior cause failure rather than an isolation claim.
- Runs the CPU Job, waits for Job Complete, captures timestamped logs, complete Job/Pod status, actual container `imageID`, exit code, node and timing. Every captured Pod must supply successful container results; Job Complete without those records is not acceptance. The live Job TTL must match the reviewed fixture before the helper waits for Job and dependent Pod disappearance without deleting them itself. The receipt records the configured TTL; this observes cleanup under that configuration, not an exclusive-cause audit of the TTL controller.
- Uses deadlines, capped resources, no retries, UID/GID 65532, ALL capabilities dropped, RuntimeDefault seccomp, read-only rootfs and a bounded writable `/tmp`; no host mounts or injected credentials. On failure it records available diagnostics and gracefully deletes only names it successfully created. It never deletes the namespace, unrelated resources or force-kills Pods.

The image is pinned to the real Docker Hub `library/python:3.12-alpine` multi-platform index digest **`sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4`**, resolved from the registry API and independently SHA256-checked against the received manifest bytes during implementation. This is an immutable infrastructure fixture, not a signed supply-chain attestation or test of an OSS contribution. Future updates must resolve a real registry digest and rerun acceptance. A real contribution test requires its own reviewed source commit/image plus existing Factory authorization and evidence receipt.

Offline checks for the integrator: `pytest -q tests/test_setup_k3s.py tests/test_k3s_manifests.py`, `bash -n scripts/setup-k3s.sh scripts/smoke-k3s.sh`, and Nix evaluation with the option both disabled/enabled. Behavioral fixtures cover unchanged managed bootstrap reruns and repeated smoke entrypoint failures through an unreachable API or an SSH-backed kubectl wrapper: failed initial connectivity must not create, apply or delete cluster resources. The SSH transport is simulated; this is not proof that a phone/laptop can authenticate or that a successful live smoke rerun works. Offline checks do not establish API/CNI/quota/TTL/runtime acceptance; run server dry-runs and this smoke only on the approved healthy host, then repeat the smoke to exercise unique-name cleanup end to end. Compare the same workload on explicit kind and K3s contexts **sequentially**, never as duplicate worker claims. kind's default CNI may fail the network control; report that limitation, do not suppress it.

## MacBook client

The 2015 MacBook currently runs CachyOS/Arch; reuse its existing `kvn@mbp` Home Manager profile and optional Linux tailnet-SSH setup. No NixOS or macOS service assumptions. Existing SSH is enough. For user CLI tools, explicitly add `my.k3sClient.enable = true;` to the existing tracked host configuration **`config/nix/hosts/mbp.nix`** and perform the normal reviewed Home Manager switch. This is an intentional configuration edit; preserve any existing checkout changes. The imported option defaults **false** and adds **only `kubectl` and `k9s`**, no services, runtimes, drivers or cluster join. Profiles remain unchanged unless explicitly enabled.

For the verified existing checkout, the reviewed MacBook switch is `home-manager switch --flake "path:$PWD/config/nix#kvn@mbp"` from the repository root after explicitly enabling the option in that host's configuration. Do not run the desktop bootstrap on the laptop.

On a different OS, use its normal user-level SSH/Kubernetes client package path; do not install a K3s server there. Prefer desktop-side `sudo k3s kubectl --context default ...` over confirmed private SSH/Tern. Native remote kubectl needs separately provisioned **scoped RBAC** and a private configuration outside Git, plus reviewed private transport such as an authenticated SSH tunnel. Review Tailscale ACL/netfilter integration rather than assuming UFW blocks private peers; never distribute desktop cluster-admin credentials. Completion is reading desktop node/Job status and logs, not joining the laptop.

## Optional worker later

Defer the RTX 2080 Super PC until useful single-node CPU work and measured capacity justify it. Verify actual OS/network/storage first; explicitly join a version-compatible **agent**, never a second standalone server. Current single-node firewall design must be deliberately redesigned for private inter-node traffic before joining. Keep join tokens local/outside Git. Start CPU-only; NVIDIA runtime/device plugin and exclusive GPU scheduling require separate compatibility/benchmark approval. No GPU fractioning, KAI, vCluster or alternate scheduler is introduced.

For an approved future agent: stop new assignments through existing Factory control, wait for owned work, use explicit node-targeted `kubectl drain <verified-node>` with reviewed disruption policy, stop/uninstall that agent using its host-local K3s agent uninstall script, and delete only its verified Node object. Do not use drain/force/emptyDir deletion flags blindly. Retain target node, commit, tests, timing and resource evidence.

## Recovery and rollback

- Connectivity failure: retain working Tern access, inspect Tailscale identity, saved host key and desktop remote-service status; no firewall reset/auth bypass. Missing sudo: obtain approved host authentication, not credential copies.
- Preflight failure: fix the specific approved storage/network/host issue and rerun read-only check. Existing cluster drift: inspect before action; no forced overwrite/reinstall.
- Startup/readiness failure after installation deliberately retains `.dotfiles-managed` as an ownership record, not a health/success receipt. Do not delete it to force a fresh install. Reruns never restart an inactive service or adopt a partial installation. Inspect `sudo journalctl -u k3s` privately (it may contain secrets), service/config metadata and the original approved flags; resolve the actual cause with the owner. Only after review, explicitly approve `sudo systemctl start k3s` if inactive, then rerun the same privileged `--check` and inspect API readiness before claiming recovery. Missing/incomplete ownership state or drift requires manual review, not automatic reconciliation.
- Smoke failure: read captured diagnostics and named-resource cleanup failures. Inspect `kubectl --context default -n oss-factory-jobs get ...` **only for the emitted run names**. Do not delete other workers or the shared namespace to clear a quota.
- To stop K3s temporarily, explicitly approve `sudo systemctl stop k3s`; this is not an uninstall. For rollback, inspect the installed `/usr/local/bin/k3s-uninstall.sh`, back up required cluster data/config **outside Git**, and stop workloads through Factory authority. Review **both killall and uninstall** in a maintenance window: upstream cleanup changes host-wide KUBE/CNI chains and can affect Docker/kind networking or Tailscale-advertised routes. Only after explicit destructive teardown approval, use `sudo env K3S_DATA_DIR=/the/exact/approved/data-directory /usr/local/bin/k3s-uninstall.sh` (default data directory is `/var/lib/rancher/k3s`). Omitting `K3S_DATA_DIR` for custom storage can target the wrong default path. This deletes local cluster state and installed components; never use uninstall to fix a smoke failure. Review selected storage afterward rather than blindly `rm -rf`-ing it. Restore only approved K3s-specific UFW changes, preserving prior host access, Docker/kind and Tailscale.
- Removing shared namespace manifests is destructive to all workloads in that namespace. Do not use namespace deletion as routine smoke cleanup. Disable the optional Nix option through the normal Home Manager switch if client packages are no longer wanted.

No runtime success, deployment, Factory authorization or performance improvement is claimed until the corresponding commands and controls actually run and their evidence is retained outside the checkout.
