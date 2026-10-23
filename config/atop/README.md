# atop telemetry

`atop` is the short-term forensic collector. It writes compressed daily raw
archives to `/mnt/zer0models/hw_monitor/atop` every ten seconds.
`atopacctd` adds records for processes that exit between samples. Keep today's
file and the preceding seven local calendar dates; `LOGGENERATIONS=8` expresses
the native policy, but `verified-retention.conf` removes the package's unsafe
age-only purge. The sole deletion owner is `atop-rollup-retire.service`.

Interactive replay:

```sh
atop -r /mnt/zer0models/hw_monitor/atop/atop_$(date +%Y%m%d)
```

JSON for an LLM or local analyzer (select a narrow time window to keep context
small):

```sh
atop -r /mnt/zer0models/hw_monitor/atop/atop_$(date +%Y%m%d) \
  -b HH:MM -e HH:MM -J CPU,CPL,MEM,SWP,PAG,PSI,DSK,NET,PRG,PRC,PRM,PRD
```

GPU collection is intentionally not enabled by default. `atopgpud` samples the
NVIDIA driver every second; enable `atopgpu.service` and add `-k` to `LOGOPTS`
only if per-process historical GPU attribution is worth that extra polling.

## System-only long-term rollups

`scripts/atop-rollup.py remote --limit 0` converts closed archives one day at a
time **on the MBP via fleet-build**, under the turnstile/quiet locks. Groot only
streams compressed input and receives the small SQLite shard. A matching
cached atop package is staged to the worker; no root package install is needed
for conversion. `--atop-package` selects another explicitly supplied reader.
Missing readers, format errors, changed sources and failed coverage checks
retain the raw source. Today's active file is never read or retired.

The allowlist contains host CPU, load, memory, swap, paging/OOM, PSI, physical
disks (`sd*`, `nvme*n*`, `mmcblk*`) and physical Ethernet/WLAN interfaces.
No process/PID/command/environment, veth, bridge or container series are
exported. At most 300 series are permitted. Byte counters use the reader's
already-normalized bytes; disk sectors are 512 bytes. Interval deltas are
divided by elapsed seconds, never differenced a second time. Disk busy values
above 100% remain visible instead of being silently clamped.

Each daily shard under `hw_monitor/rollups/` has a metric/unit dictionary,
source stat identity/size/mtime, reader version, host, reset/gap/coverage
manifest, and both 60-second and 300-second buckets. Buckets store
duration-weighted mean, minimum, maximum, nearest-rank **sample** p95, sample
count, covered seconds and OOM event count. Both resolutions use the original
samples. Crossing intervals split their coverage and event counts at bucket
boundaries. The first/since-boot sample, overlapping/reset intervals and
intervals longer than 120 seconds are excluded and counted explicitly.
Excessive exclusions block retirement.

One-minute rows last 30 days; five-minute rows last 365 days. Old one-minute
rows are removed in place; no full database vacuum or raw reconversion is
performed. Expired shards are removed only if their raw source is already
retired. The independent `data/telemetry.sqlite3` is never touched.

```sh
# Initial approved backfill (runs heavy conversion only on the MBP):
ionice -c3 nice -n19 python3 scripts/atop-rollup.py remote --limit 0
# Verify a shard / show retirement eligibility without deletion:
python3 scripts/atop-rollup.py verify /mnt/zer0models/hw_monitor/rollups/atop_YYYYMMDD.sqlite
python3 scripts/atop-rollup.py maintain
```

The root setup entrypoint is `scripts/setup-infra-monitor.sh apply`. It installs
root-owned executables/units and the Netdata profiles, then performs only
verified retirement and enables the timer. Each retirement appends source
bytes, aggregate bytes, coverage and before/after filesystem available bytes
to `hw_monitor/rollups/retirement-ledger.jsonl`. Filesystem deltas can include
concurrent work and delayed allocation; source logical bytes are separate.

`atop-rollup.timer` runs daily at 03:15 with up to 20 minutes jitter after daily
rotation. If the MBP is busy, offline or too hot, fleet refuses admission;
no fallback conversion runs on Groot, and no unsuccessful day triggers raw
retirement. The next daily run catches up.

## Netdata alongside atop

`config/netdata/` is the local-only live/history collector for both fleet
hosts. Its dbengine lives on each host's nonrotational system disk, with
size/time-capped 1-second, 1-minute and 1-hour tiers. Netdata can supply future
long-term metric trends, but it does not import historical atop data and cannot
replace recent raw process forensics. Keep the small historical rollups anyway.

Notifications go through a fixed local Unix-socket relay running as Kevin and
`notify-send` on his session bus (Noctalia). They never use the intake-only
Telegram bot. A missing desktop bus is a delivery error, not a successful send.
The root batch also runs `config/netdata/test-alert.py` on each host: it creates
one explicitly labelled transient `system.cpu` health rule, reloads health,
requires an actual local API `WARNING`, and removes/reloads the owned rule in
cleanup. A conflicting preexisting file is never overwritten. This exercises
the native evaluator separately from the notification transport's `--test`.

The optional OMP MCP registration uses the official `nd-mcp` stdio bridge to
`ws://127.0.0.1:19999/mcp`; no Cloud claim or credential is needed for basic
metric discovery/query/alerts. Upstream restricts sensitive logs/live functions
behind claimed-agent authentication; those capabilities are not enabled here.

