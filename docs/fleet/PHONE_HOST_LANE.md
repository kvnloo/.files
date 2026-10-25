# Android phone host lanes

Phones are **not Kubernetes nodes**. Only trusted owner jobs belong here. The default lane runs native Android commands from groot through SDK adb. It does not need Omalauncher, its LinuxService, guest SSH, Python, or Tailscale inside a guest. Omalauncher stays installed to host Hermes/OMP/Tern. Its availability does not control native fleet jobs.

## Default: native adb

```sh
job=$(scripts/fleet run --node s22 --src ./native-payload -- ./worker --output result.bin)
scripts/fleet status s22 "$job"
scripts/fleet logs s22 "$job"
scripts/fleet status s22 "$job" --fetch src/result.bin --dest ./results
scripts/fleet kill s22 "$job"
# Or wait for completion and fetch in the submit call:
scripts/fleet run --node s25 --src ./native-payload --fetch src/result.bin -- ./worker
```

`s25` and `omarchy-phone` name the same device. `s22` names `galaxy-s22plus`.
`scripts/fleet-adb discover PHONE` selects an authenticated transport by
`getprop ro.serialno`, with USB first. It checks all connected adb entries, then
discovers the hardware's `_adb-tls-connect._tcp` mDNS endpoint if necessary.
Neither an old wireless port nor the apparent adb serial is trusted as identity.
The helper uses `~/android/sdk/platform-tools/adb` and groot's server on port5037,
not a guest tunnel or `/usr/bin/adb`. It does not scan ports or pair devices.

Submit copies `--src` (default cwd, use `--no-src` to omit) into
`/data/local/tmp/fleet-jobs/JOB/src/`. `--input FILE:RELATIVE_PATH` stages an
exact extra file there. The working directory is `src`. Each job has private
`home` and `tmp` directories, an independent session/process group, `pid`,
`identity.json`, `stdout`, `stderr`, and an `exit` file. The runner starts through
`adb shell` with `nohup setsid`. `FLEET_JOB_ID` is available to the payload.
Run normally returns the job ID immediately. `--fetch PATH` on run waits for
completion and returns the payload exit code after the pull. Paths are relative
to the job directory, so payload results normally use `src/…`.
`fleet fetch PHONE JOB --fetch PATH --dest DIR` also pulls existing results.
Without `--dest`, results go to `~/.local/state/fleet/runs/JOB/`.

The runner enforces `--timeout` (default 3600 s) and drains its process group on
exit. Kill checks the exact runner path in `/proc/PID/cmdline`, PID start time,
boot ID, and process-group/session ownership before it signals the whole group.
It never uses `pkill`. A reused PID is not a job. Spools stay on the device for
logs, status, and result recovery. The lane makes no reboot-survival guarantee,
retry, lease, isolation, cgroup, Android-root, or Kubernetes Ready claim.

Phones: no agent resource caps; Android manages battery/thermal/RAM.
Enforced by Bend law O10 / z0-guard phone-caps. There is no CPU pinning,
memory ceiling, priority change, thermal gate, or light/worker profile.
The only native resource admission gate refuses a battery **below 2% and not
charging**. Exactly 2% and a charging phone remain available.
Native health reads online identity, `dumpsys battery`, and
`dumpsys thermalservice` through adb only. Thermal readings are informational.
A dead guest cannot pause the native phone lane.

### Native toolbox

Android supplies `/system/bin/sh` and toybox, not a Linux distribution.
It has no Linux Python, Bash, Git, glibc, or guest package toolchain.
The native lane fails before launch if the first command cannot be resolved on
the device or in the payload. Use a static Android-compatible aarch64 binary,
or explicitly select `--guest` for a Linux-userland job.

Put a checksum-verified static aarch64 busybox and other native tools in
`/data/local/tmp/fleet-bin`. The payload directory and this toolbox precede
`/system/bin` on PATH. A Linux/glibc binary is not necessarily Android-compatible.
For inference, reuse EdgeProbe's measured llama.cpp/MNN runtimes already under
`/data/local/tmp`, with their required libraries and model paths. Those model and
runtime directories are not copied into each job or assumed to have a fixed
version. Supply their actual native executable path and environment, for example
through `sh -c 'export LD_LIBRARY_PATH=…; exec /data/local/tmp/…/llama-cli …'`.
Do not invent a toolbox download or silently fall back to a guest.

## Opt-in: SSH Linux guest

```sh
scripts/fleet run --node s22 --guest --src ./linux-project -- python3 worker.py
scripts/fleet kill s22 GUEST_JOB_ID --guest
```

This path retains the existing durable leased PRoot executor. Its Linux tools
and guest service health apply only when explicitly selected. The explicit
`fleet phone` API below also always targets this guest contract.
The existing agentjob/Linux scope and factory/untrusted pod policy are unchanged.

### Guest lifecycle: launcher owns, guest supervises

After owner persistent-host opt-in, Omalauncher's long-lived LinuxService must invoke the following as a foreground guest child, independent of any Activity, terminal window or audio playback:

```sh
python3 /opt/dotfiles-k3s/scripts/fleet-phone-supervisor start \
  --state-dir "$HOME/.local/state/fleet-phone-supervisor" \
  --config "$HOME/.config/fleet/phone-services.json"
```

`stop` persists desired=stopped **before** notification and also sets the existing `~/.config/fleet/no-autostart` switch, so a legacy login/PulseAudio bootstrap cannot undo Stop. `resume` is explicit opt-in: clears the stop switch and enables a subsequent launcher `start`; it does not detach/spawn itself. `status` emits desired, observed, process identity/liveness and each child state. An absent desired file only permits the explicit caller's start; it is not Android consent. A missing/invalid config blocks.

`event --event network-available|network-lost|reconcile` uses a private Unix datagram socket. Android's real connectivity callbacks should deliver these events. They reconcile blocked/circuit-open services; running tailscaled handles its own real network changes. There is no network polling loop or claim that polling keeps Android alive.

Child exits wake `wait()`, with bounded exponential 1..60 s backoff. Five quick failures in 300 s open a circuit until a new explicit event; a 120 s stable run resets the failure budget. Each instance has an exclusive flock, shared with the existing legacy runit tree. Lock descriptors are closed in children. Known existing unmanaged sshd/tailscaled/tern instances block, never get killed or duplicated. After a legacy tree exits, a service/reconcile event can retry. `setpriv --pdeathsig TERM` forwards unexpected parent death through the foreground tree; normal Stop drains owned children. Kernel/PRoot support for that mechanism remains a required device acceptance check.

`config/fleet/phone/services.example.json` reuses the existing foreground run scripts, tailnet state, SSH host keys and Tern configuration, plus the worker executor. It is an **example for the current /root guest**, not a deployment or automatically approved listener configuration. Review installed scripts/paths and listener restrictions before copying it to the active config. Do not invent a new tailscale identity, run tailscale up, regenerate SSH keys or broaden listener/firewall/account privileges on rejoin. No autostart hook is installed or service started by this change. `fleet-phone-setup.sh` copies the APIs when explicitly enrolled, without starting them; legacy run scripts are existing phone setup prerequisites.

### Existing installed launcher: retain runsv

The 2026-10-22 rollout retains `fleet-phone-supervise` and its existing daemon
tree. The newer launcher-owned foreground supervisor is **not activated**: it
needs the persistence APK/lifecycle integration, and replacing the live tree
would interrupt SSH, tailscale and Tern remote. Do not run both supervisors.

`fleet-phone-setup.sh TARGET --port PORT --model MODEL --defer-adb` installs the
adapter plus `~/.local/share/fleet/sv/fleet-worker/{run,finish,log/run}` and updates
the legacy supervisor's service list. It does not restart the running parent.
The new worker joins that same runsv tree on its next approved start; do not
detach a worker from an SSH session and call it persistent. The existing tree
has no service-list reload API. Until that restart, probes report the executor
down and placement refuses jobs.

`--defer-adb` permits installation while self-ADB is unavailable. Self-ADB is
not an execution prerequisite. Setup never rewrites an unverified serial or
changes Android settings. Restore Wireless debugging only when an Android UI
task requires it. No Android power policy, APK, account or app-data changes are
required by this deployment.

Phones: no agent resource caps; Android manages battery/thermal/RAM. Enforced by Bend law O10 / z0-guard phone-caps.

Phones remain available for placement without a light/worker resource profile.
Owner pause and call hooks retain owner intent. Jobs retain timeouts and
process-group cleanup. Host placement is `fleet run`/`fleet-build`, not
Kubernetes autoscaling. Groot has no host lane and is never a no-room fallback.


## Pure-Python suites in a guest

```sh
fleet-build --node s25 --src /path/to/private/repo -- \
  sh -c 'python -m pip install -q pyyaml jsonschema && PYTHONPATH=src python -m pytest -q tests/unit'
# Use --node s22 to pin the other phone, or --node phones to select by health/load.
```

Named phone nodes in `fleet-build` imply the Python guest lane. Android/JDK
builds and Bend/native x86 proofs stay on the MBP. This does not change native
`fleet run --node s25 -- CMD` or the explicit general-purpose `--guest` API.
No CPU/RAM caps are added or accepted by the Python wrapper.
No fixed free-disk threshold gates a phone job. The `--node phones` pool measures
the selected source files and explicit input files. It compares their byte
count with fresh availability on each guest's actual staging filesystem.
The pool skips a guest that cannot hold that payload, before source transfer.
This placement signal depends on the job, not an agent-defined resource budget.
It does not reserve storage or predict venv and dependency growth. An actual
out-of-space error still fails the job normally. Pinned phone jobs remain
explicit placement requests.

Admission requires a fresh native adb health probe and authenticated guest SSH.
A phone below 2% battery charge cannot start a job unless it is charging.
Existing owner-intent and service checks still apply.
Source uses the existing checked tar-over-SSH transfer into a unique
`~/fleet-jobs/<job>/src`, not a package install or a second scheduler. Both tar
ends must succeed. No source is sent to public CI. Each job creates a sibling
`venv` with `python3 -m venv`, installs pytest, and runs the supplied argv with
that venv first on PATH. Install any additional suite dependencies explicitly.
Pip uses the guest owner's persistent `~/.cache/pip`, even though payload HOME
is job-local. No system Python packages, Android settings or app state change.

Logs are `~/.local/state/fleet/runs/<job>-<registry-node>.log` on the controller.
They include command, exit/status, venv setup, command and total elapsed times,
and guest uptime before source transfer and after execution. Uptime comes from
the kernel `CLOCK_BOOTTIME` clock: Omalauncher's `/proc/uptime` can be a frozen
startup snapshot, not a live clock. A kernel boot-ID change, uptime
reset/insufficient coverage, or changed PRoot tracer PID/start
identity makes the result `guest_restarted` (exit76), even if pytest exited0.
Missing final lifetime evidence is `guest_unavailable` (exit255), never success.
The retained source and executor spool are available for diagnosis; no job is
automatically replayed after allocation.

## Shared job API

`fleet run --node s22 --guest -- CMD...` submits the selected guest job to the durable executor, follows status/logs and renews its lease. `fleet kill PHONE JOB --guest` cancels that exact durable ID. Source transfer and artifact fetching use SSH. The guest spool/source remain available for recovery. Linux/MBP execution is unchanged.

Explicit controller API:

```sh
fleet phone s22 submit stable-owner-id < spec.json
fleet phone s22 status stable-owner-id
fleet phone s22 logs stable-owner-id
fleet phone s22 heartbeat stable-owner-id < lease.json
fleet phone s22 lease stable-owner-id
fleet phone s22 recover stable-owner-id
fleet phone s22 cancel stable-owner-id
fleet phone s22 capabilities
```

Guest API is the same commands on `python3 ~/.local/lib/fleet/fleet-phone-worker`, with `serve` as the launcher-supervised foreground executor. `submit` reads a spec from stdin:

```json
{"argv":["python3","-m","unittest","discover"],"cwd":"~/fleet-jobs/stable-owner-id/src","timeout":3600,"idempotent":false,"max_attempts":1}
```

The source directory must already exist beneath `~/fleet-jobs`. One attempt is the default. An optional per-job resource value requires an explicit caller request. An identical ID/spec submission returns the same record. Binding an existing ID to a different spec fails. Transactions use flock + fsync/atomic rename. Only one executor can run. It serially executes already-placed work, not a second fleet scheduler. Payload HOME is a per-job directory, not the owner's credential home. This is convenience, **not isolation from malicious code**.

`submit` and `lease` return an opaque lease token. `heartbeat` takes it only via stdin; status/logs never include it. Guest TTL is 10..600 s (120 default, controller uses 300). Controller copies are mode0600. SSH transport uses BatchMode/identity from the existing fleet helper, but forces strict host checking and disables reused connection masters **before** generic options (OpenSSH uses first value). It never accepts new host pins, shares/rotates private keys, emits raw SSH diagnostics, or substitutes the native Android VPN endpoint for its guest.

## Outage, retry and drain semantics

Availability states are separate: `unavailable` means authenticated SSH/probe failed, `stale` means evidence too old/clock-skewed, `paused` means explicit owner pause/call or stopped service, and `unsupported` means wrong host platform. `ready` means the host lane is reachable and active. Missing device telemetry does not prevent phone jobs. `fleet-polite-run` forwards termination to the payload process group.

A failed probe reports `status: probe_error`, the node name, and its error
message. A nonzero SSH exit is a transport failure, not JSON to parse. Empty
or malformed output also rejects that node without an exception in the
scheduler. Diagnostics preserve known SSH failure causes without raw stderr.

Guest executor checks leases/cancel at most every 5 s. It rechecks owner intent while queued. A controller crash/outage stops renewal. The guest terminates expired work when it can execute. A frozen guest may still hold execution ownership. Lease expiration alone never licenses a second execution elsewhere. Guest reconciliation occurs through the explicit guest API, not default adb-only `fleet health`.

The native adb health probe checks Omalauncher's foreground `LinuxService`.
Missing service reports `guest_down`, while preserving Android's native online
telemetry. Recovery holds `/tmp/<phone>-ui.lock` and launches only with complete
owner-idle evidence: at least 60 seconds since user activity, a same-boot
agent-opened foreground ledger entry newer than that activity, idle telephony,
and normal audio mode. Missing evidence or a busy lock refuses UI interaction.
Launches are recorded in `/tmp/<phone>-agent-opened.json` before `monkey`;
`/tmp/<phone>-guest-restore.json` bounds recovery to two attempts per boot.
No wake key, settings changes, resource caps, or payload replay is performed.
All fleet-adb subprocesses detach stdin, including hardware discovery, so a
probe inside a read loop cannot consume its caller's remaining devices.

Recovery checks boot ID + PID start time, live runner/child and surviving process-group descendants. Live/ambiguous executions cannot be re-leased. Dead non-idempotent executions become `needs-confirmation`, never speculative retries. `fleet run --idempotent` (or explicit spec `idempotent:true,max_attempts:3`) permits bounded retry of the **same ID** only after confirmed interruption/drain. Exactly-once arbitrary side effects cannot be guaranteed across a crash between an external effect and durable completion; idempotent jobs must implement their own effect dedupe using `FLEET_JOB_ID`. A late heartbeat from an expired token cannot renew a replacement generation. Offline cancellation is durable controller intent and is delivered on rejoin without renewing that job.

An unavailable/ambiguous phone run returns255 and retains its source, spool and controller record; this deliberately prevents fleet-build's generic exit75 loop from creating new IDs for an already-started non-idempotent payload. Exit75 is still pre-admission/no-room. There is no relocation or pretend success. No automatic cleanup deletes uncertain records; explicit maintenance after inspection is required.

A job can finish between a status read and its next lease renewal. If that
renewal fails, the controller makes one read-only status check. A confirmed
terminal state supplies the actual exit result and final log. Missing or
nonterminal evidence still returns255. The controller never resubmits the job.

## Verification and platform boundary

Run the focused deterministic suite with `python3 -m unittest discover -s tests -p test_fleet_phone.py -v`; use `fleet-build --node mbp --wait 0 --mem 512M -- ...` for fleet qualification. Tests use temporary homes, fixture children and transport doubles, not a real device. They exercise durable Stop/duplicate-start exclusion, actual child exit/restart/circuit/event behavior, process identities, jobs executed once, lease drain, idempotence/retry, unsupported hosts, strict transport options, health gates and offline/rejoin ownership.

This document does not prove lifecycle reliability. Separate evidence is required for screen-off/other app, daemon death, Android process death, network-loss/rejoin, package update, reboot/unlock and measured overnight availability/outage reasons. Unrooted Android cannot guarantee survival of force-stop, OS/PRoot kills/freezing, radios off, power loss or locked/reboot restrictions. Force-stop requires owner interaction where Android requires it. No Doze/global-freezer/root/MDM changes or daily-phone UI manipulation belong to this adapter.
