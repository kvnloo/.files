# Groot storage layout

Large mutable outputs and immutable release bytes belong on the mounted bulk disk, not the 132 GiB root partition. Small configuration, ledgers, and state remain under the home directory.

## Releases

The single release convention is `/mnt/zer0models/releases/<name>/<sha>` for the physical release tree, including its virtual environment and fetched dependencies. `~/.local/lib/<name>/<sha>` is a compatibility symlink; `~/.local/lib/<name>/current` selects a stamped release. Deployment remains serialized by the owning deploy lock. Do not relocate running release trees: adopt this layout when staging the next release. The next z0int-shadow activation must follow the storage step in `operations/policy-pipeline/SLM-RELEASE-HANDOFF.md` in the operations data repository.

## Fleet

`config/fleet/storage.toml` selects the bulk run directory per hostname. Every host-side transport resolves it through `scripts/fleet_paths.py`; an explicit `FLEET_RUNS` or isolated `FLEET_STATE` override remains supported. On groot, the default refuses to write when `/mnt/zer0models` is not mounted rather than filling the underlying root mountpoint. Fleet health and admission state stay in `~/.local/state/fleet`.

The bulk run directory is `/mnt/zer0models/host-offload/home_kvn_.local_state_fleet_runs`, preserving the existing offload destination and receipts. Old home spool symlinks are migration artifacts, not the new write-path configuration. Existing detached clients may still use their original paths until completion.

`fleet-source-retention.timer` retires fetched `src/` copies after seven days into the adjacent `fleet-source-archive` directory. This is deliberately archive-only, not destructive garbage collection: all bytes and receipts are retained. It requires an expired valid tool spool lease, an unambiguous terminal receipt, idle descendants, and known absence of live references. Unknown state keeps the source. It never retires the whole job directory, receipt, log, or other fetched outputs. This bounds the active spool, not total bulk-disk use; any later destructive archive retention requires separate policy and law-G checks.

## Other home data

Do not delete or relocate `.actual` session/user data as cache. Running z0int-runtime trees remain in place until the next stamped release cutover. Tool caches (`.npm/_cacache`, `.cargo/registry`, `go/pkg/mod`, `.gradle/caches`, `.elan/toolchains`) may be offloaded only when idle and not in use, preserving symlink compatibility for tools without configurable roots. Newly staged release environments and build payloads must use the bulk disk directly.

Autotier targets a 20 GiB root reserve; fleet-health retains its lower 15 GiB admission threshold, leaving a 5 GiB intervention margin. Exit 75 means the reserve remains breached with no safe allowed candidates; it is an actionable capacity failure, not an exit code to suppress.

The autotier implementation and tests are owned here in `.files`. Its old chief-of-staff script path is superseded, not a second deployment source. Provenance: chief-of-staff `72ecfc4` preserved the pre-existing live policy (uncommitted since at least 2026-08-29); `23159f4` introduced managed idle-cache policy. `scripts/install-host-storage.sh --activate` stages the committed `.files` tree under the `host-storage` release name and installs both managed timers under `/tmp/files-live-deploy.lock`.
