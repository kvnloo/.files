# Interactive desktop admission

CPU-only builds, tests, renders and encodes belong on MBP or a worker-only Kueue flavor. Unsafe/unavailable workers return 75 or remain queued; they do not authorize a groot fallback. A `render` label is not proof of GPU use.

## Installed seams

- `fleet run` checks persisted pause state even for `--node`; fresh thermal/health/memory admission happens before transfer and again on MBP after transfer. Missing/nonfinite thermal readings fail closed. The fleet health timer closes `z0.dev/cpu-admit` on the first unsafe sample, independent of cordon strike hysteresis.
- `factory` and `lanes` have only `node-mbp` CPU placement. Its flavor requires `z0.dev/cpu-admit=true`. `45-interactive-cpu-placement.yaml` denies unpinned/groot CPU-heavy pods in factory/lanes/z0. Real NVIDIA resource allocation permits GPU placement on groot with explicit bounded CPU and memory. A <=200m/64Mi one-container infrastructure exception preserves the existing gateway.
- `hermes-worker-.scope.d` is a systemd dashed-prefix drop-in for future tool scopes. It does NOT match Hermes gateway/core services. Workers enter `agent.slice` at launch, inheriting limits before children execute. The classifier is recovery for recognized agent descendants, not the primary admission path; desktop/browser/audio and CLI control roots are excluded.
- `/dev/sdb` is an SSD. Agent IO has no `io.max` bandwidth cap, because an 8/4 MB/s cap stalled every agent tool and MCP server. Memory uses only hard `MemoryMax` limits, because `MemoryHigh` throttling livelocks over-budget jobs. Tool scopes carry `RuntimeMaxSec=8h`, so forgotten background jobs are reaped.
- `z0-worker-supervision` keeps its existing timer. Operational mode reads a primary-key-bounded message window, performs no repository discovery/status scans, and carries older unresolved evidence as explicit holds. Full replay remains an on-demand operation. This is bounded replay, not a fully incremental historical index.

## Install and verify

Run from the intended isolated integration tree; the installer symlinks exact owned files and backs up replaced targets. It does not merge, push, restart the gateway/compositor/k3s, or install ctx's staged restart configuration.

```sh
python3 scripts/install-desktop-admission --apply --receipts /mnt/zer0models/workspace/zer0/data/operations/desktop-lag/20261022
KUBECONFIG=$HOME/.kube/k3s.yaml kubectl apply -f config/k3s/manifests/45-interactive-cpu-placement.yaml
KUBECONFIG=$HOME/.kube/k3s.yaml kubectl apply -f config/k3s/kueue/queues.yaml
python3 scripts/verify-desktop-admission
fleet-build --node mbp --wait 0 -- python3 tests/test_desktop_admission.py
```

Inspect `/sys/fs/cgroup/.../cpu.max` and `io.max`, not just configured systemd properties. API dry runs prove admission, not running pods. Check real Job `spec.nodeName`, completion and logs separately. Never uncordon a hot worker just to get green evidence.

The placement binding covers every namespace selectable by the configured
ClusterQueues: `factory`, `lanes`, `fleet-mbp`, and `z0`. The z0 `cpu` flavor
deliberately has no node labels so its CPU quota can accompany the GPU flavor;
it does not bypass pod admission. The verifier exercises all seven placement
cases in each namespace plus full MBP lane acceptance and GPU/nodeName bypass
rejection (30 server dry runs). The trusted
`fleet-mbp` namespace retains its Kueue-owned 4-CPU/10441814016-byte budget only
when explicitly selecting MBP; groot's per-container limits remain unchanged.
Factory's GPU case is denied by its zero-GPU ResourceQuota. Keep queue namespace
selectors and this binding aligned when adding queues.

## Canonical film continuation

`fleet-fframes-delivery --out NEW_DIRECTORY --wait 0` uses the canonical script and exact picture/soundtrack input files. It extends existing `fleet-build` with exact `--input FILE:RELATIVE_PATH`, retains the remote job with `--keep`, and fetches only final encodes/logs. It refuses to overwrite the paused source artifact tree. Direct canonical `deliver_v2.py encode` fails with 75 on groot; MBP execution must prove an effective fleet scope CPU/memory ceiling. Genuine GPU film rendering remains local within the agent envelope.

Do not resume an old in-memory delivery parent locally: its imported functions predate the guard. Coordinate the original task owner, preserve partial files, and use a new remote output directory. A transport failure after source transfer can leave a retained partial job; inspect its exact ID before retrying. Do not blindly replay a job that already received an ID.

## Limits

This is owned-workflow admission, not a same-user security sandbox: a user/admin can deliberately bypass wrappers or create workloads in other namespaces. Kube-system/control-plane services are not throttled by this policy. Health labels are observations, not continuous thermal guarantees for already-running jobs. Prefix limits protect native Hermes scopes only while its systemd backend is available; classifier recovery is best-effort for other launch paths. No sustained no-lag claim follows from a short probe.

The ctx resource policy is owned by `config/systemd/user/ctx.service.d/50-resource-policy.conf`.
Install it with `python3 scripts/apply-ctx-policy --apply` from the intended
integration tree. The installer backs up and removes only its five exact
`user.control` property overrides, links an immutable content-stamped drop-in,
and reloads systemd without restarting ctx. It leaves ctx's generated unit,
supervisor environment, source databases and indexing mode untouched.
The hard ceiling remains 5 GiB resident/cgroup memory plus 2 GiB swap; there is
no `MemoryHigh` reclaim throttle. `OOMPolicy=stop` and a bounded restart rate
prevent a partial daemon or rapid crash loop. This budget is a desktop safety
ceiling, not a guarantee that every corpus fits. Do not raise it without a
measured refresh peak and host headroom.

The older single-preparation-worker drop-in remains staged and is not installed
by this policy: ctx 2.2.8 already defaults to one preparation worker. Its
`ExecStart` override is not needed for the resource fix. Preserve the generated
`env -i` launch contract rather than installing that redundant override.

## Foreground activation gate (do not call this complete early)

Native background terminal tools were exercised inside `agent.slice` with CPU max
`100000 100000`. Native foreground calls were independently found still launching
inside `hermes-core.scope` without a CPU ceiling: the prefix drop-in alone is NOT
proof of complete protection. The isolated Hermes branch
`repair/foreground-resource-admission-20261022` carries the small
`LocalEnvironment._run_bash` entry hook. It calls installed `agent-tool-run` before
payload execution. The wrapper owns its conservative shell parser in this
checkout and uses the native systemd scope manager; it needs no external z0int
checkout or private home state. It holds known CPU builds/tests/encodes, exempts
explicit single interactive application/CLI launches from workload throttling,
and never falls back to direct execution if parsing or scope creation fails.

`python3 scripts/verify-hermes-foreground-entry` exercised the exact patched method
body in isolation using real subprocesses and kernel cgroups; only environment
resolvers were injected. It observed an immediate 1-CPU agent scope and a cargo
build hold (75). It is NOT a live-gateway turn test. The parent must integrate the
Hermes source patch, checkpoint active sessions, perform its owned gateway restart,
and re-run the actual foreground terminal cgroup probe before declaring all future
launches protected. Do not throttle the gateway/core to hide that activation gap.
