# Host optimization: operated system, not a promise of universal autotuning

## Ownership and trigger

`.files` owns host collection, systemd policy and K3s bootstrap. This extension reuses the existing fleet steward (original `.files` PR 46, source `383a59f5`), fleet logs and health observations. It does not install the old branch's fleet scheduler/toolchain changes or create a second scheduler, raw trace database or LLM gateway.

`host-optimizer.path` activates a bounded oneshot when the existing fleet health history or canonical job spool changes. The existing health timer supplies observations; there is no new polling timer. Native Hermes/OMP/Claude/Codex/Pi/T3 processes remain native. K3s/Kueue remain physical allocation authorities. Kerdoios remains placement-only. Harnesses retain their session ownership.

## What actually runs

1. Sample host PSI, available RAM, disk space, and numeric CPU/memory/OOM accounting for user services and native scopes. CPU deltas require the same boot and a fresh interval. Parent/child cgroups overlap and must never be summed.
2. Read only numeric derived session signals from the existing local AgentsView database, across agent/machine groups. Do not read prompts, messages, tool arguments, screenshots, credentials or activity titles. These parser signals are not independent failure verification or per-tool latency evidence.
3. Read Kubernetes pod status/restart/termination counters without changing pods, quotas or admission. Lifetime restarts are not current restart rates.
4. Refresh the original fleet steward from legacy plus canonical bulk-spool logs. Keep missing timing data unknown. Coalesce expensive historical parsing to at most once per five minutes when jobs change; refresh unchanged history after 30 minutes, and expose its observation age and pending source changes.
5. Rank source-backed recurring problems and retain at most seven days/5,040 aggregate observations. Candidate lessons, learned per-repo parameters and capacity projection stay in the existing steward format.
6. Reset only the explicitly approved legacy `agent.slice` two-core ceiling and `hermes-worker-*.scope` one-core ceilings. No changes to memory protections, security policy, session placement, CPU power profiles or arbitrary services.
7. At most once daily, when CPU/memory/I/O gates permit, compare a fixed two-process CPU replay under a one-core cap versus uncapped. Six matched pairs alternate order. Both digests must match; failures and partial runs cannot win. Checkpoint before launch and after each arm, back off after a crash, recheck host pressure each pair, and bound every scope to 15 seconds/192 MiB. This validates one CPU-policy lever; it is NOT a production task speedup benchmark or a general autonomous code-writing loop.

No model/API spending occurs. There is no automatic cache deletion, global cache flush, root mutation, service restart, arbitrary command execution, interactive-session migration or new resource scheduler.

## Install and operate

```sh
python3 scripts/apply-agent-oom --host-optimizer           # dry run
python3 scripts/apply-agent-oom --host-optimizer --apply   # content-stamped closure; enable .path; initial tick
host-optimizer status
host-optimizer pause                                      # durable marker, no automatic re-enable
host-optimizer resume                                     # next source event resumes work
systemctl --user status host-optimizer.path
journalctl --user -u host-optimizer.service -n 10
```

The narrow installer touches only its three owned links; it does not reapply unrelated host policy or restart shared gateways. Installer receipts preserve prior targets. `config/host/groot.toml` declares the links and complete closure. The source `.path` uses the current groot bulk-spool location; storage moves must update it with `config/fleet/storage.toml`.

Private outputs live under the established SFT-SVLM activity telemetry root, in `host-optimizer/`, not Git. `latest.json` carries freshness/coverage, `history.json` contains bounded numeric observations, `experiments.json` is a ranked proposal queue, `cpu-experiment.json` retains the most recent fixed experiment, and `fleet-steward/` holds the reused evidence products. Require the canonical bulk mount before writing. Missing sources remain explicitly unavailable.

Pause prevents new actuation/experiments; a currently executing bounded arm may finish. To stop immediately: pause, then `systemctl --user stop host-optimizer.service host-optimizer.path`. This stops only the optimizer, not any user's harness. To retire login activation: `systemctl --user disable --now host-optimizer.path`; preserve private evidence and the install receipt. Restore previous links from that receipt, daemon-reload, and do not delete source data.

## Why earlier attempts did not meet the ask

Observed on 2026-11-03:

- `.files` PR 46 is still an open draft. Its own body explicitly says it does not change the live checkout, timer, cluster or installed tools. Green fixtures were reported, but cutover/native provisioning was deferred.
- The AgentSys council produced a two-week experiment plan and local commits. Its host recorder was an experiment to start, not an installed continuous recorder. Raw tool timings were incomplete across harnesses.
- Host controls and cluster controls were conflated: lifting the aggregate CPU quota alone left per-worker and launch-argument quotas. A runtime-only change did not codify the default.
- The live fleet-health unit now uses a newer stamped entry, while its base description still names an old worktree. The primary checkout and fleet worktree trail deployment branches. Branch/PR/docs status is not deployed-byte evidence.
- The live health unit repeatedly fails because it reports low root disk space and a Boat probe JSON parse error. A failed aggregate health result does not mean every worker is offline. The learner is triggered by written observations even when the producer returns failure.
- This thread repeatedly stopped at optional decisions and final reports instead of delivering an operated loop. A future research plan and a running deterministic learner are different artifacts.

## Honest remaining scope

This is a running first closed path: observe, learn recurring patterns, test one fixed lever when safe, and repair that approved policy's regressions. General automatic optimization of all harnesses is not complete. Per-tool critical-path joins, measured disk/host-placement comparisons, skill-card and wait-primitive A/Bs, quality gates for new actuators, and an approved bounded research-agent continuation remain separate work. `experiments.json` is explicitly labelled proposals, not executed improvements. No universal performance gain may be claimed until paired accepted-task results support it.

For further levers: use the saved AgentSys council protocol, each owning repository's contribution rules, z0evals for frozen evaluation, and Tokenomics for neutral timing. Promote only evidence-backed candidates with rollback; do not ask a continuously running LLM to mutate the host at will or bypass a provider refusal/quota to keep it busy.
