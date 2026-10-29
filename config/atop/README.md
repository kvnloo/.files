# atop telemetry

`atop` is the sole persistent collector. It is a native C program and writes
compressed daily raw archives to `/mnt/zer0models/hw_monitor/atop` every ten
seconds. `atopacctd` adds records for processes that exit between samples.

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
