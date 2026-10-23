# Boat agent jobs

## Scope and availability

Boat is a cheap **Linux parallel-job backend**, not a native cross-OS backend.
The [base-image documentation](https://docs.boat.dev/machines/tools) offers one
Ubuntu 24.04 LTS x86_64 image. There are no native Windows or macOS images, no
custom base images, and no GPU. Wine is not a Windows OS test. On 2026-10-23 the
live smoke VM reported Ubuntu **24.04.4**, kernel **7.0.0-38-generic**; this differs
from the documentation's Linux 6.8 description.

[Boat's published regions](https://boat.dev) are Germany, Finland and France.
The public create API does not offer a region selector; placement is automatic.
Nested KVM is available on standard hosts, not guaranteed on fallback hosts.

[Prices](https://docs.boat.dev/pricing), USD, per running hour, billed per second:

| Size | vCPU / RAM / writable disk | Price | Trial |
| --- | --- | --- | --- |
| small | 2 / 4 GB / 12 GB | $0.018/h | yes |
| default | 4 / 8 GB / 50 GB | $0.036/h | yes |
| large | 8 / 16 GB / 125 GB | $0.072/h | no |
| xlarge | 16 / 32 GB / 251 GB | $0.200/h | no; $100+ plan |

The [trial](https://docs.boat.dev/free-trial) is seven days, card required,
25 compute hours total, **two** simultaneous VMs, starts 5/minute, 25/hour,
75/day, and auto-stop at most two hours. Saved named snapshots are unavailable
during the trial; automatic stop snapshots and forks work. Paid plans start at
$20/month, credited as compute time. We do not change plans, buy credits or touch
billing. Trial currently ends **2026-10-30 22:23:28 UTC**. `limits` is the authority;
the account's nominal 555.56 balance hours are **not** the 25-hour trial allowance.

## Installed clients and credentials

- CLI: `~/.ascii/bin/boat`, version 1.0.67 at qualification. Downloaded using the
  [documented static-binary method](https://docs.boat.dev/cli-reference), without
  installer shell edits, browser login or persisting a CLI token.
- Python SDK: `boat-sdk==1.11.0` in `~/.local/share/boat/venv`.
  Recreate with `uv venv ~/.local/share/boat/venv` and
  `uv pip install --python ~/.local/share/boat/venv/bin/python boat-sdk==1.11.0`.
- Wrapper: Python 3 stdlib; secret jobs also need `age` on the trusted host. The
  wrapper installs Ubuntu's `age` inside each secret VM before receiving secrets.
- Run `scripts/bws-apply-local-secrets.sh` to populate `BOAT_API_KEY` in the existing
  Hermes and OMP local env files. It is deliberately excluded from CodexBar.
  The wrapper reads only this named key; do not source entire env files.
- The account key has sandbox/exec/file/SSH/desktop/host/snapshot/environment
  permissions and `account.read`, **not** `account.admin` or a wildcard.
  Never run `boat login --key-stdin`: it would persist another secret copy.

## Use

During Draft review the live checkout is `/workspace/boat-setup`; the installed
entry point is `~/.local/bin/omp-boat`. After merge, repoint that symlink to the
canonical checkout's `scripts/boat`. Do not bypass the wrapper with raw create,
resume or fork calls during normal agent work.

```sh
omp-boat limits
omp-boat run unit-tests -- bash -lc 'uname -a; python3 -c "assert 6 * 7 == 42"'
# Two independent Linux jobs; Boat trial admits at most two, not three.
omp-boat run job-a -- python3 -c 'import time; time.sleep(5); print(42)' &
omp-boat run job-b -- python3 -c 'import time; time.sleep(5); print(84)' &
wait
# Local control/SDK callback, not a persistent VM. Exiting the callback deletes it.
omp-boat create inspect -- sh -c 'echo "$BOAT_SANDBOX_ID"'
omp-boat delete bx_23456789  # only an existing omp-* sandbox; irreversible
omp-boat reap               # delete omp-* resources older than 600 seconds
```

Options precede the job name: `run --type default job-name -- COMMAND ...`.
Names always get `omp-`; creates are serialized through a host-user lock and
preflight checks count **all** active sandboxes, not just ours. The provider
sets concurrency, currently two VMs. The common host lock coordinates agents
on Groot. It is not a distributed account lock. Do not create independently
from other hosts or keys.

Each lease has a 600-second provider auto-stop, readiness deadline 120 seconds,
remote ordinary command timeout at most 500 seconds, and deletion in `finally`
on success, error, SIGINT, SIGTERM and SIGHUP. Secret jobs get a 300-second
systemd runtime cap. TTL stops billing if the host is killed; it does not delete
the disk. The periodic reaper deletes it, including automatic snapshots.
A failed deletion is reported as an error, not silently accepted.

The wrapper is deliberately **trial-only**. The approved guard is three compute
hours per rolling 24 hours, plus the provider's 90,000-second total trial cap.
Before every create, it reserves 600 seconds for each live VM and the new VM.
It includes reported live usage conservatively in both checks. It refuses
paid or expired access and never changes billing.

## Secret jobs: encrypted delivery, default deny

No job gets any secret by default. `noEnv=true`, `snapshots=false` and
`monitoring=false` are set **when the sandbox is created**, before it can accept
secrets. No inherited account repositories, environment files or credentials are
requested. Never pass the Boat account key or BWS access token to a sandbox.
Provider-owned internal sandbox control credentials are outside this wrapper's
control; `noEnv` is not a claim that Boat has no internal machine credentials.

`config/boat/secret-allowlist.json` is an intentionally empty name-to-BWS-UUID map.
An operator may add only **dedicated, short-lived, least-privilege, low-limit job
keys** from the Hermes BWS project. Do not enroll existing general-purpose agent
keys just to make a job work. No token minting, rotation or billing API is called
by this wrapper. Expiration, spend limits and provider scopes must be set when
the operator provisions each dedicated credential.

```sh
# After the operator maps this dedicated name to its BWS secret UUID:
omp-boat run --secret MY_SCOPED_JOB_KEY api-test -- python3 job.py '{secret_file}'
```

The job reads a JSON file at the substituted `{secret_file}` argument. The argument
contains a **path**, never a value. Adapt clients to read the named value from
this file; do not export it, pass it as an argv argument, or put it in a command.
Do not use `--env-file` for host processes: it would put secrets in their process
environment. JSON-file consumption is the supported path here.

Delivery sequence:

1. Groot's keyring bootstrap supplies BWS authentication **only to the local BWS
   subprocess**. Only requested allowlisted UUIDs are fetched with `bws secret
   get`; no whole-vault list is used for job delivery. Name/project are checked.
   BWS output and plaintext bundle remain in trusted-host memory, not files.
2. The sandbox disables swap and creates a fresh age identity on a private
   `tmpfs` mount with `noswap,nodev,nosuid,noexec`. Only its public key is fetched.
3. Groot pipes the selected JSON directly to `age -r PUBLIC_KEY`; only ciphertext
   is uploaded. Decryption goes straight to a mode-0600 tmpfs file owned by the
   dedicated `ompjob` user; the private key is mode 0600 owned by root.
4. One unprivileged `systemd-run` job reads the file. `NoNewPrivileges`, a
   read-only root/home view, private devices, no core dumps, tmpfs-only working
   and temporary directories prevent accidental disk writes by that process.
   All job stdout/stderr goes to `/dev/null`; secrets must not enter logs.
   Secret-job output is intentionally unavailable; exit status is returned.
5. The bundle and private key are overwritten/unlinked, the tmpfs work is
   removed and unmounted, then the entire VM is deleted. An interrupted host is
   covered by provider TTL and the host reaper. No resume/fork/snapshot surface
   is exposed by the wrapper. Prepare and snapshot **separate, secret-free**
   sandboxes only; never snapshot or fork a secret-loaded sandbox.

A missing age binary, failed BWS lookup, unavailable `noswap`, failed isolation,
or failed cleanup is an error; there is no plaintext fallback.

### Threat model and remaining limits

This reduces opportunistic env-file harvesting, `/proc/*/environ` discovery,
plaintext argv/history leaks, disk residue and snapshot/log retention. Only
ciphertext crosses the host-to-sandbox file API. The unprivileged job cannot
write its secret to normal persistent files or elevate through sudo.

**It does not protect a live secret from a compromised VM root, provider,
hypervisor, kernel, privileged platform daemon, or the authorized job itself.**
Root can read the age identity, tmpfs and process memory. A compromised job can
exfiltrate its own allowed credentials over the network. Age transport encryption
is not confidential computing. Use revocable short-lived keys and low spend caps;
for zero cloud plaintext exposure use a host-side scoped API broker instead.
Python/age process memory is not securely zeroized. `shred` on tmpfs is hygiene,
not a guarantee against prior RAM copies. The trusted host and BWS/keyring remain
part of the trust boundary. Do not send secrets to unreviewed repository code.

### Qualification

The secretless Linux smoke cloned `kvnloo/cua` commit
`6e74bfadd82790312f0ab46ae7ed48027f8aca56` and ran
`python3 -m unittest discover -s .github/scripts/tests -p test_get_pyproject_version.py -v`:
**19 tests passed**. Create took 1.127 s, ready from request 2.882 s, exec 3.008 s.
`uname -a` and `/etc/os-release` identified the live Ubuntu/kernel above.
Boat reported 2 billed-equivalent seconds, **$0.00002** list-price usage.

A separate secret-free VM created in 0.772 s, ready in 1.165 s. The desktop API
returned a private URL (never logged). An actual X11 capture produced a
640x480 PNG (4,826 bytes; SHA256
`ee217a18bda38527ddfdce1e275f8e03200a72c3098abc5f2ab9e7d7c03c0e81`).
Stop captured the disk in 2.297 s; snapshot list contained two automatic captures.
Fork created in 1.186 s and became ready in 3.066 s. Its real exec confirmed the
persisted `snapshot-proof` file and a Python sum assertion. Source usage was
$0.00008; fork $0.00037. All their deletion operations completed.
A transient quoted-Python syntax error in the fork test was corrected before the
successful assertion; it was not reported as a provider/OS failure.

The dummy secret transport qualification uses a generated random canary, not a
real key and not a new BWS secret. It scans readable files on the root filesystem
and process environments before/after the job, checks tmpfs `noswap`, swap off,
file ownership/0600, no retained snapshots and disabled command history. The
job separately checks its own environment and reads the file. This exercises
real age encryption, file upload, RAM decryption, isolated execution and cleanup;
it does not prove a provider cannot inspect RAM or exercise a real provider API
credential. Real BWS allowlist lookup remains default-denied until an operator
provisions a dedicated key.

Final dummy run **passed**, job exit 0: create 1.454 s, ready 1.824 s,
0 environment matches, 0 readable-rootfs matches before/after, no snapshots,
command-history API refused with `monitoring_off`, and tmpfs cleanup succeeded.
Meter at cleanup: 95 equivalent seconds / $0.00095. An initial isolated job
failed with systemd CHDIR (exit 200): the base home directory lacked traversal
permission for `ompjob`. Granting directory traversal, not secret-file access,
fixed it; that failed VM was deleted too.

Two simultaneous wrapper jobs were observed in account limits; a third was
refused before creation. SIGTERM of one lease still completed deletion; the
other returned 42 and exited successfully. A request for `--secret BOAT_API_KEY`
was rejected before any VM was created.

After all runs: account.read reported **195 metered seconds**, zero live usage,
zero active VMs and an empty full sandbox inventory. This is **$0.00195** at list
price, covered by the trial (no payment), approximately **0.217%** of the
90,000-second trial compute cap. These account totals include failed setup/test
iterations and deletion overhead; per-VM figures read before deletion are not a
final bill. Receipt: `/tmp/omp-boat-smoke-receipt.json`; screenshot:
`/tmp/omp-boat-desktop.png`. No desktop URLs or credentials are in either file.
The original setup run passed eight local policy tests. Current policy coverage is:
`python3 -m unittest discover -s tests -p test_boat.py -v` (11 tests).
They exercise default-deny keys, trial/concurrency/budget refusal, reaper scope,
snapshotless create payloads, failed-command exit status and unconditional deletion.

```sh
omp-boat run --dummy-secret-test canary -- python3 -c \
 'import json,os,pathlib; v=json.loads(pathlib.Path("{secret_file}").read_text())["BOAT_SMOKE_DUMMY"]; assert all(v not in x for x in os.environ.values()); assert v.startswith("omp-dummy-")'
```

## Fleet integration qualification (2026-10-23)

`~/.local/bin/fleet-build` now points to the compiled and tested scratch worktree
at `/workspace/boat-fleet`. The entrypoint and `omp-boat` symlinks were replaced
atomically. The existing phone and MBP admission policies remain unchanged.
The reaper uses the updated wrapper through its existing installed entrypoint.

Three jobs were submitted together through `fleet-build --node boat`.
Each uploaded a reviewed Git-source tarball, ran real tests, fetched `result.txt`,
returned exit 0 and completed its deletion operation. Provider concurrency held
at two. The third submission returned pre-admission 75, waited 60 seconds, and
then ran without replaying an allocated job.

| Suite | Tests | Test runtime | Total invocation wall | Fleet job | Deleted VM |
| --- | ---: | ---: | ---: | --- | --- |
| CUA release-version validation | 19 | 0.002 s | 11.420 s | `20261023-175619-cb9a2675` | `bx_8w9cdkyh` |
| Real phone lane wrapper regression | 8 | 20.621 s | 32.377 s | `20261023-175619-01c2d1ef` | `bx_z6wjx7f4` |
| Factory z0evals memory replay | 11 | 1.217 s | 78.978 s, including queue | `20261023-175723-0b9a4e8a` | `bx_qtpwyrta` |

Boat reported `x86_64`, Python 3.12.3. The factory replay source is pinned to
[`16b0b133df865d46b2b1a789f68936c189d88f41`](https://github.com/kvnloo/z0evals/commit/16b0b133df865d46b2b1a789f68936c189d88f41).
It exercises synthetic, privacy-safe replay contracts. It does not prove live
memory retrieval, provider inference or a production learning loop.
The CUA snapshot came from local revision `5f653d5e48a143828621303526850115486fc5e4`.

All payloads printed SHA-256 before testing:

| Source file | SHA-256 |
| --- | --- |
| CUA `get_pyproject_version.py` | `6105d27f52e96a3f2db9161e1bb4753e6b14874d08120047e655d0b9ab35ad70` |
| CUA `test_get_pyproject_version.py` | `1b72a894341c148b04f307037b117171dbc401acd40e6aecf3d9af646fb11a4f` |
| Fleet `fleet-polite-run` | `d44ad6da0a61a4b78e3fab95ffc109a99d74df83b2f9af8c81f2859594b4aaa9` |
| Fleet `test_fleet_phone_lane.py` | `28140676e82c236c7e3e06a55b9fb183c05b36324c56b905405a87ecf2249427` |
| z0evals `memory_query_replay.py` | `7bd8ac0dcd1e5aa9e95f567145c72211f0211f6217aafb52bc5625ef98f6eec1` |
| z0evals `test_memory_query_replay.py` | `e8741484a7a34bdae28c6472cd7a2c762c9ef7566e371be523d32a155e07a0c9` |

### Comparison with existing workers

New MBP runs used the same source hashes and commands, requested 512 MiB and
one CPU, and used `--wait 0` inside the canonical shared quiet lock.
Both passed and fetched their outputs. MBP reported Python 3.14.7.

| Suite | Boat wall | MBP wall | MBP test runtime | MBP job |
| --- | ---: | ---: | ---: | --- |
| CUA 19 tests | 11.420 s | 2.510 s | 0.009 s | `20261023-175740-1d9d` |
| z0evals 11 tests | 78.978 s including 60 s queue | 6.923 s | 4.548 s | `20261023-175740-ae91` |

New S25 comparisons did not execute. Each exhausted eight pre-admission
attempts because root free space was 4.7–4.9 GiB, below its 5 GiB floor.
Observed waits were 189.593 s for z0evals and 185.670 s for CUA. Both exited 75
without job IDs. No disk floor was weakened and no user files were removed.
These are admission waits, not test runtime measurements.

The earlier phone qualification in [README.md](README.md) used the exact same
two fleet source hashes. Its eight-test invocation walls were S25 **33.124 s**,
S22 **55.319 s**, and MBP **87.870 s**, including its external lock wait.
Boat's matching suite took **32.377 s**. The corresponding test runtimes were
25.704 s, 45.526 s, 25.384 s and 20.621 s respectively.
The suite contains wait-based tests. Python versions and CPU allocations differ.
These figures compare observed latency, not normalized CPU performance.

### Budget and local checks

The account moved from **195 to 210 provider-metered seconds** during the
three Boat jobs: **15 seconds added**, including deletion accounting.
At that receipt, active VMs and live usage were both zero. Total usage was
**0.233% of 90,000 seconds**, leaving **89,790 seconds** of the trial.
Rolling-24h usage was 210 seconds, leaving 10,590 before new lease reservations.
List-price equivalent was $0.00210 total, $0.00015 incremental, trial-covered.
This is a qualification snapshot, not the account's future usage after other agents run.

Compilation and Bash syntax checks passed. Executed behavioral coverage totals
42 tests: Boat policy 11, Boat transfer/routing 16, phone lane 8, phone policy 7.
The transfer/routing cases include source and output traversal, capacity races,
private-data routing, original failed-command status with missing artifacts,
and successful-command failure when a requested artifact cannot be fetched.
The artifact diagnostic correction was tested in an isolated scratch copy
and installed atomically. It did not require repeating the successful VM suites.

Raw receipts: `/tmp/boat-fleet-evidence/{boat-results,all-results}.json`.
Per-job logs and fetched outputs remain in that directory and under
`~/.local/state/fleet/runs/`. The all-results receipt records the two S25 holds
as failures. It must not be described as seven successful jobs.
Usage and budget rules were broadcast to all 21 available peer agents.

## Periodic reaper installation

The user timer is installed and enabled on Groot. Definitions live in
`config/systemd/user/boat-reaper.{service,timer}`; it runs `omp-boat reap` every
minute. Normal creates also reap expired `omp-*` sandboxes first.

```sh
ln -s "$PWD/scripts/boat" ~/.local/bin/omp-boat
ln -s "$PWD/config/systemd/user/boat-reaper.service" ~/.config/systemd/user/
ln -s "$PWD/config/systemd/user/boat-reaper.timer" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now boat-reaper.timer
```

The timer requires a live user systemd manager and network. During a full host
outage the provider TTL stops billing, and deletion resumes when the host returns.
Definitions are codified here; shared `fleet.toml` was intentionally not changed.

## Native Windows/macOS alternatives (research only)

No accounts were opened and no resources were purchased. Prices are indicative,
checked 2026-10-23; taxes/storage/IP/network may be additional.

| Provider | Real OS and fit | Rough price / trial |
| --- | --- | --- |
| [GitHub Actions](https://docs.github.com/en/billing/reference/actions-runner-pricing) | Windows and macOS VMs; best first choice for short CI assertions. Not a general interactive desktop rental; hosted macOS GUI/TCC limitations matter for CUA. | Standard Windows $0.010/min (~$0.60/h), macOS $0.062/min (~$3.72/h). [Standard public-repo jobs free](https://docs.github.com/en/billing/concepts/product-billing/github-actions); private repos have plan-included minutes. No special signup trial needed for public OSS. |
| [AWS EC2](https://aws.amazon.com/ec2/instance-types/mac/) | Windows Server VMs and native Apple-silicon/Intel Mac dedicated hosts; flexible networking, more setup. | Small Windows VM order-of-magnitude ~$0.04–0.10/h (estimate; quote the chosen region/AMI). M1 Mac approximately $0.65/h ([indicative comparison](https://macrun.dev/ec2-mac-alternative)), **24-hour minimum** (~$15.60), plus EBS/IP. [New-customer offer](https://aws.amazon.com/free/): $100 initially, earn up to another $100, up to 6 months; Free plan has restricted services, do not assume Mac Dedicated Hosts qualify. |
| [Scaleway Apple silicon](https://www.scaleway.com/en/pricing/apple-silicon/) | Native macOS dedicated Mac mini, Paris; promising low-cost interactive Mac capacity. | M1 €0.11/h (€75/month), M2 €0.17/h, M4 €0.22/h, before VAT. [24-hour minimum lease](https://www.scaleway.com/en/docs/apple-silicon/faq/) means M1 minimum €2.64. [Mac signup page](https://www.scaleway.com/en/mac-mini-signup/) advertises €100 credit for new **Business** accounts; confirm eligibility/voucher terms, not an assumed personal free tier. |
| [MacStadium](https://macstadium.com/pricing) | Native dedicated Macs; Orka for VM pools, useful for sustained parallel Mac work rather than a five-minute smoke. | M2 8 GB $109/month; M4 16 GB $149/month. No individual-host free trial; large migrations may request a sales proof of concept. |
| [Cua Spaces](https://cua.ai/pricing) | Current page is **bring your own** Mac/Linux/Windows computers; Windows preview. It does not currently advertise rentable VMs. Historical 2025 cloud Windows/macOS posts are not proof of a current rental product. | Free relay: 2 live sessions / 20 remote hours monthly. Pro $18/month, Teams $30/seat/month; underlying compute billed by the provider you bring. Current page explicitly says no trial and “Cua doesn't rent them.” |

Recommendation: keep Boat for parallel Linux tests; use existing public GitHub
Actions runners first for native Windows/macOS CI. For interactive macOS CUA,
price Scaleway's 24-hour lease against MacStadium monthly capacity. Obtain a
current Cua cloud quote only if they offer rental compute again; do not sign up
based on an old blog post.
