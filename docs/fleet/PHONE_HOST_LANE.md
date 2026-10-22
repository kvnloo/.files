# Explicit Android PRoot host lane

Phones are **not Kubernetes nodes**. Registry kind `phone` advertises `proot-host-lane`; `fleet` still performs placement and the existing polite-run wrapper still performs battery/thermal/memory admission and drains. No kubelet, cgroups, Android root, network/security isolation, guaranteed RSS limit, or Kubernetes Ready claim is made. Only trusted owner jobs belong here; the existing agentjob/Linux scope and factory/untrusted pod policy are unchanged.

## Lifecycle: launcher owns, guest supervises

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

## Shared job API

Existing `fleet run --node s22 --mem 512M -- CMD...` now submits the selected phone job to the durable executor, follows status/logs and renews its lease. `fleet kill PHONE JOB` cancels that exact durable ID instead of matching process command lines. Source transfer and artifact fetching still use the existing fleet transport. The phone spool/source are retained to support recovery and log inspection. Linux/MBP execution is unchanged.

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
{"argv":["python3","-m","unittest","discover"],"cwd":"~/fleet-jobs/stable-owner-id/src","mem_mb":512,"floor_mb":1200,"timeout":3600,"idempotent":false,"max_attempts":1}
```

The source directory must already exist beneath `~/fleet-jobs`. Defaults are 512 MiB sampled job budget, 1200 MiB owner RAM floor and one attempt. An identical ID/spec submission returns the same record; binding an existing ID to a different spec fails. Transactions use flock + fsync/atomic rename. Only one executor can run; it serially executes already-placed work, not a second fleet scheduler. Payload HOME is a per-job directory, not the owner's credential home; this is convenience, **not isolation from malicious code**.

`submit` and `lease` return an opaque lease token. `heartbeat` takes it only via stdin; status/logs never include it. Guest TTL is 10..600 s (120 default, controller uses 300). Controller copies are mode0600. SSH transport uses BatchMode/identity from the existing fleet helper, but forces strict host checking and disables reused connection masters **before** generic options (OpenSSH uses first value). It never accepts new host pins, shares/rotates private keys, emits raw SSH diagnostics, or substitutes the native Android VPN endpoint for its guest.

## Outage, retry and drain semantics

Availability states are separate: `unavailable` = authenticated SSH/probe failed, `stale` = evidence too old/clock-skewed, `paused` = owner/battery/thermal/memory/service gate, `unsupported` = wrong host platform, and `ready` = fresh host-lane admission only. Missing battery or thermal metrics fail closed. Jobs start only above owner floor **plus** reservation. Existing polite-run samples memory and thermal/battery during execution, drains on gate failure, and now forwards executor termination to its payload group. These checks are measured polling, not lifecycle survival.

Guest executor checks leases/cancel at most every 5 s; admission evidence is rechecked every 30 s while queued. A controller crash/outage stops renewal; the guest drains expired work when it can execute. A frozen guest may still hold execution ownership: lease expiration by itself never licenses a second execution elsewhere. `fleet health` uses its existing measured timer and automatically reconciles only **previously owned** records after strict SSH and fresh healthy probe return. No UI wake or app reopening is invoked.

Recovery checks boot ID + PID start time, live runner/child and surviving process-group descendants. Live/ambiguous executions cannot be re-leased. Dead non-idempotent executions become `needs-confirmation`, never speculative retries. `fleet run --idempotent` (or explicit spec `idempotent:true,max_attempts:3`) permits bounded retry of the **same ID** only after confirmed interruption/drain. Exactly-once arbitrary side effects cannot be guaranteed across a crash between an external effect and durable completion; idempotent jobs must implement their own effect dedupe using `FLEET_JOB_ID`. A late heartbeat from an expired token cannot renew a replacement generation. Offline cancellation is durable controller intent and is delivered on rejoin without renewing that job.

An unavailable/ambiguous phone run returns255 and retains its source, spool and controller record; this deliberately prevents fleet-build's generic exit75 loop from creating new IDs for an already-started non-idempotent payload. Exit75 is still pre-admission/no-room. There is no relocation or pretend success. No automatic cleanup deletes uncertain records; explicit maintenance after inspection is required.

## Verification and platform boundary

Run the focused deterministic suite with `python3 -m unittest discover -s tests -p test_fleet_phone.py -v`; use `fleet-build --node mbp --wait 0 --mem 512M -- ...` for fleet qualification. Tests use temporary homes, fixture children and transport doubles, not a real device. They exercise durable Stop/duplicate-start exclusion, actual child exit/restart/circuit/event behavior, process identities, jobs executed once, lease drain, idempotence/retry, unsupported hosts, strict transport options, health gates and offline/rejoin ownership.

No live deployment/phone tests were performed. Required before reliability claims: parent-managed spare/approved idle tests of screen-off/other app, daemon death, Android process death, network-loss/rejoin, package update, reboot/unlock, and battery/thermal drain, followed by measured overnight availability/outage reasons. Unrooted Android cannot guarantee survival of force-stop, all OS/PRoot kills/freezing, radios off, battery depletion, power loss or locked/reboot restrictions. Force-stop requires owner interaction where Android requires it. No Doze/global-freezer/root/MDM changes or daily-phone UI manipulation belong to this adapter.
