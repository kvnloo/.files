# Interactive desktop admission

CPU-only builds, tests, renders and encodes belong on MBP or a worker-only Kueue flavor. Unsafe/unavailable workers return 75 or remain queued; they do not authorize a groot fallback. A `render` label is not proof of GPU use.

## Installed seams

- `fleet run` checks persisted pause state even for `--node`; fresh thermal/health/memory admission happens before transfer and again on MBP after transfer. Missing/nonfinite thermal readings fail closed. The fleet health timer closes `z0.dev/cpu-admit` on the first unsafe sample, independent of cordon strike hysteresis.
- `factory` and `lanes` have only `node-mbp` CPU placement. Its flavor requires `z0.dev/cpu-admit=true`. `45-interactive-cpu-placement.yaml` denies unpinned/groot CPU-heavy pods in factory/lanes/z0. Real NVIDIA resource allocation permits GPU placement on groot with explicit bounded CPU and memory. A <=200m/64Mi one-container infrastructure exception preserves the existing gateway.
- `hermes-worker-.scope.d` is a systemd dashed-prefix drop-in for future tool scopes. It does NOT match Hermes gateway/core services. Workers enter `agent.slice` at launch, inheriting limits before children execute. The classifier is recovery for recognized agent descendants, not the primary admission path; desktop/browser/audio and CLI control roots are excluded.
- The HDD runs mq-deadline, so IOWeight is not an I/O ceiling. The aggregate agent budget also uses actual per-device `io.max` bandwidth limits.
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

## Canonical film continuation

`fleet-fframes-delivery --out NEW_DIRECTORY --wait 0` uses the canonical script and exact picture/soundtrack input files. It extends existing `fleet-build` with exact `--input FILE:RELATIVE_PATH`, retains the remote job with `--keep`, and fetches only final encodes/logs. It refuses to overwrite the paused source artifact tree. Direct canonical `deliver_v2.py encode` fails with 75 on groot; MBP execution must prove an effective fleet scope CPU/memory ceiling. Genuine GPU film rendering remains local within the agent envelope.

Do not resume an old in-memory delivery parent locally: its imported functions predate the guard. Coordinate the original task owner, preserve partial files, and use a new remote output directory. A transport failure after source transfer can leave a retained partial job; inspect its exact ID before retrying. Do not blindly replay a job that already received an ID.

## Limits

This is owned-workflow admission, not a same-user security sandbox: a user/admin can deliberately bypass wrappers or create workloads in other namespaces. Kube-system/control-plane services are not throttled by this policy. Health labels are observations, not continuous thermal guarantees for already-running jobs. Prefix limits protect native Hermes scopes only while its systemd backend is available; classifier recovery is best-effort for other launch paths. No sustained no-lag claim follows from a short probe.

The ctx single-preparation-worker drop-in is staged separately because its ExecStart uses `env -i` and the shared service restart belongs to the parent/operator. Validate the post-restart environment and active preparation worker count; do not assume an Environment= directive survived env -i.
