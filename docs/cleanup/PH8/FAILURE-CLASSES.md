# PH8 failure classes and existing coverage

Observed 2026-11-05. This is phase A, not a claim that all hosts are healed. Sources below are existing owner tools, not a new survey. `none` means no applicable detector found in the reused sources. Presence does not prove a timer works. Groot's `fleet-health` and `artifact-leases` services were failed at observation time. [state]

| Host | Failure class | Existing detector and cadence | Existing bounded repair and receipt, or gap |
|---|---|---|---|
| groot | Root disk pressure | `fleet-health.timer`, every 2 minutes, judges free disk and Kubernetes pressure | Report-only for groot. `zer0-storage-autotier.timer` uses existing tiering policy. Do not invoke its broad apply mode here. [fleet] [state] |
| groot | Bulk disk fills after offload | No direct bulk reserve check in the reused fleet judge. Tiering alone does not reclaim this sink. | New `host-cleanup-pressure.timer` checks `/mnt/zer0models` hourly. Bulk prune remains forbidden. [prune] [new] |
| groot | Stale fetched sources | `fleet-source-retention.timer`, daily | Existing script requires terminal evidence, expired lease, old descendants, same filesystem, and no process references. It archives without deleting source data. Not invoked here. [source-retention] [state] |
| groot | Stale worktrees and scratch | `worktree-reaper.service` and `artifact-leases.timer` exist | Existing reaper runs `z0-guard worktrees --daily`. Artifact reporting is failed in the snapshot. Neither authorizes deletion of dirty or receipt-less trees. [reaper] [state] [disk-rules] |
| groot | OOM, swap and desktop pressure | Running `agent-oom-guard.service`, `memory-drift.timer` | Guard is the existing sole OOM-score writer. No new process kills, caps, swap changes, or restarts. Journal and drift reports are existing receipts. [oom] [memory] [cleanup-skill] |
| groot | Failed units, restart loops, stale timers or heartbeat | `service-watch.service` and `service-watch-heartbeat.timer` | Existing watcher reports anomalies. It is not permission to restart shared services. [watch] [state] |
| groot | Hermes memory growth, recall drift | `memory-heal.timer`, `memory-recall-check.timer`, `memory-drift.timer` | Existing memory mechanisms own repair and receipts. No memory-store pruning. Z07 still requires recall and false-deletion proof. [state] [Z07] |
| groot | OS package/update debt | Existing manual `cleanup-cachyos.sh`; R09 owns native update work | No broad `--yes` run. That script mixes package removal, journal deletion, privileged operations, and unqualified environment deletion. These are outside this run. [cleanup] [R09] |
| MBP | Disk pressure and admission hold | `fleet-health.timer` on groot plus kubelet disk conditions | Existing health logic controls admission and owned cordon recovery. R11 owns archive/reclaim recovery. No threshold change, uncordon, or MBP fleet-state access here. [fleet] [nodes] [R11] |
| MBP | Stale terminal stages | `fleet-stage-retention.timer` on groot, hourly | Existing retention requires terminal, fetch/export, lease and liveness proof. `/home/agentjob/.local/state/fleet` is explicitly excluded from this run. [stage-retention] [state] |
| MBP | Low memory, heat, battery, core service loss | `fleet-health.timer` on groot | Existing judge checks memory, temperatures, battery, core services and Kubernetes conditions. Admission hold is the safe response, not an automatic restart. [fleet] [nodes] |
| MBP | Arbitrary stuck user unit | none for a general user-unit detector in the reused host probe | Read-only `systemctl --user --failed` returned zero failed units. This cannot detect an active-but-stuck unit. A functional probe requires the exact unit and expected output. Repair would require restart approval. [probes] |
| S25 | Disk pressure | none in the native fleet judge, which returns after battery/transport checks | New hourly disk detector verifies hardware identity and reads `df -kP /data`. Live receipt shows 2,258,890,752 bytes available. No approved phone-cache repair exists in the reused cleanup scripts. [fleet] [new] [fixed] |
| S22 | Disk pressure | none in the native fleet judge | Same new detector. Live receipt shows 11,148,210,176 bytes available. No phone deletion or UI input. [fleet] [new] [fixed] |
| S25 | ADB transport loss, low battery | `fleet-health.timer` detects native probe failure | Native fleet discovery checks hardware serial and can reconnect advertised transports. No S25-specific keeper timer found in reused units. Re-pairing or adbd reconfiguration is not authorized here. [adb] [fleet] [state] |
| S22 | ADB transport loss after Wi-Fi roam | Existing `phone-adb-keeper.timer`, every 2 minutes | Existing keeper writes last/JSONL receipts and tries bounded connects. It also uses `adb tcpip`, so it was not invoked here under the no-restart rule. [keeper] [state] |
| S25 and S22 | Linux guest/service unavailable | Existing guest admission probe in `fleet-build` detects `guest_down` | Both attempts reported `Omalauncher LinuxService missing`. The deployed probe can invoke automatic app restoration. Both waiting commands were stopped with signal 15 when this was found. No pre-action restore marker was present. Native ADB being healthy does not prove the Linux guest is healthy. [test-s25] [test-s22] [probe-safety] |
| S22 | Sender stalls | Existing `s22-stall-alarm.timer`, every 5 minutes | Existing alarm only. No send, app launch, or UI repair in this run. [state] |
| S25 | Sender-specific stall | none in reused timer inventory | No sender-specific functional probe supplied. Do not reuse S22's alarm against an unverified S25 sender. Implementation remains open. [state] |
| S25 and S22 | Stale native job stages without terminal ownership proof | No qualified automatic cleanup detector established for both phones. Artifact lease reporting includes S22, not S25. | Metadata-only candidate list. Preserve receipts and unknown jobs. A disk detector is not a stale-stage detector. [state] [phone-candidates] [disk-rules] |
| S25 and S22 | Android OOM or active-but-stuck apps | none for a retained per-app OOM/stall detector in reused native health checks | Android owns RAM management. Do not add phone caps, kill apps, or infer OOM from a missing Linux service. A named app and read-only functional probe are still needed. [fleet] [nodes] |

## New timer limits

`host-cleanup-pressure.py` adds measurements only where needed, without replacing fleet health or retention. It marks pressure below 15 GiB available or 10% free. These are alert thresholds, not fleet admission changes. It scans at most eight existing authenticated ADB transports, with eight-second calls. Missing or malformed measurements are unknown, never healthy. Android bind-mount aliases are accepted because the command explicitly queries `/data`. [new] [fixed]

The optional repair is at most one 20-second `uv cache prune --offline --no-config --cache-dir <explicit>` call, only if the cache shares a pressured measured device. It preserves the existing bulk-prune prohibition. It writes and fsyncs a receipt before any prune. In this run uv repair was skipped, all phone repair was `none_authorized`, and no bytes were deliberately removed. The timer is not installed or enabled. Tests are authored but fleet admission is blocked. [new] [prune] [fixed] [test-s25] [test-s22]

## Existing organization and ownership decisions

Keep the existing `zer0` taxonomy. Do not create `/workspace/products`, `/workspace/agents`, or `/workspace/labs`. Preserve runtime paths, dirty checkouts, model assets, and the distinction between relocation and deletion. The older plans contain proposals and historical measurements, not current cleanup authorization. [old-plan] [recovered-plan]

## Sources

All `logs/` paths below are relative to this operation folder, `/mnt/zer0models/workspace/zer0/data/operations/intent-analyzer-20261104/ayo-runs/exec-PH8`. The same document is copied into the isolated owner worktree under `docs/cleanup/PH8/`.

- [state] `logs/existing-detectors.log`, `logs/baseline.log`, `logs/candidate-sizes-policy.log`.
- [probes] `logs/candidates-probes.log`, MBP storage and user-unit probe.
- [fixed] `logs/disk-receipts-fixed/20261105T060725Z-8d5973698c974761bffdd5ccf660a743.jsonl:1-3`.
- [phone-candidates] `logs/phone-candidates.log`.
- [test-s25] `logs/tests-fleet.log`.
- [test-s22] `logs/tests-fleet-s22.log`.
- [probe-safety] `logs/fleet-safety-audit.log`; `/mnt/zer0models/releases/host-storage/1650568ad1d371bdbf431794dcfe7dbdf9241088/scripts/fleet-adb:81-133,135-160`. The recovery code writes `/tmp/<phone>-guest-restore.json` before its app-start command.
- [new] `/mnt/zer0models/worktrees/files-ayo-PH8/scripts/host-cleanup-pressure.py:1-157` and `config/systemd/user/host-cleanup-pressure.service`, `config/systemd/user/host-cleanup-pressure.timer` in that worktree.
- [fleet] `/mnt/zer0models/releases/files-live/1611c2a190e95c91d6da8bb5ad6bfa61914875bc36b07c802eae5b5476e43d3c/scripts/fleet:138-174,217-289,292-368`.
- [nodes] `/mnt/zer0models/releases/files-live/1611c2a190e95c91d6da8bb5ad6bfa61914875bc36b07c802eae5b5476e43d3c/config/fleet/nodes.yaml:49-175`.
- [adb] `/mnt/zer0models/releases/files-live/1611c2a190e95c91d6da8bb5ad6bfa61914875bc36b07c802eae5b5476e43d3c/scripts/fleet-adb:26-68`.
- [keeper] `/mnt/zer0models/releases/phone-adb-keeper/18b1286b88e60cfdc44381fca3cbe02247cfaaa1/phone-adb-keeper:23-26,86-140`.
- [prune] `/mnt/zer0models/releases/host-storage/1650568ad1d371bdbf431794dcfe7dbdf9241088/scripts/zer0_storage_autotier.py:105-110,431-433,603-624`.
- [source-retention] `/mnt/zer0models/releases/host-storage/1650568ad1d371bdbf431794dcfe7dbdf9241088/scripts/fleet-source-retention.py:1-75`.
- [stage-retention] `/mnt/zer0models/releases/host-storage/1650568ad1d371bdbf431794dcfe7dbdf9241088/scripts/fleet-stage-retention.py:1-69` and its installed unit in `logs/existing-detectors.log`.
- [reaper] `/home/kvn/.config/systemd/user/worktree-reaper.service:1-10`.
- [oom] `/home/kvn/.config/systemd/user/agent-oom-guard.service:1-17`.
- [memory] `/home/kvn/.config/systemd/user/memory-drift.service:1-10`.
- [watch] `/home/kvn/.local/bin/service-watch:1-49`, `/home/kvn/.config/systemd/user/service-watch-heartbeat.service:1-15`.
- [cleanup] `/workspace/.files/scripts/cleanup-cachyos.sh:102-188,191-267,306-313`, `/workspace/.files/scripts/host-cleanup-review.sh:1-6,31-57`.
- [cleanup-skill] `/workspace/hermes-home/profiles/clean/skills/root-pressure-safe-cleanup/SKILL.md:10-26`.
- [disk-rules] `/workspace/hermes-home/profiles/clean/skills/root-pressure-safe-cleanup/references/disk-reclaim.md:23-39`.
- [R09] `/mnt/zer0models/workspace/zer0/data/operations/owner-message-audit-20261104/ASK-LEDGER.md:52-56`.
- [R11] Same ledger, `:64-68`. Existing Reliability owner retains this work.
- [Z07] Same ledger, `:268-272`.
- [old-plan] `/mnt/zer0models/z0-wt/salvage/pc-reorg/FINAL-PLAN-from-omp-session-20260917.md:99-164`.
- [recovered-plan] `/mnt/zer0models/z0-wt/salvage/pc-reorg/RECOVERED-PLAN.md:36-54,80-88`.
