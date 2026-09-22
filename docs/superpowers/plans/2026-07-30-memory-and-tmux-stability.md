# Memory and tmux Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent global OOM freezes and tmux pane loss by correcting the swap topology, containing agent workloads in killable cgroups, and preserving the tmux shell when an agent is reclaimed.

**Architecture:** RAM, bounded zram, and NVMe swap form a finite latency hierarchy. Every agent and its browser/dev-server descendants run in `agent.slice`, where `MemoryHigh`, `MemoryMax`, swap, task-count, and systemd-oomd policies apply; the lightweight tmux server and pane shell remain outside that reclaimable scope. Earlyoom remains a final pre-kernel-OOM backstop with thresholds consistent with the real swap topology.

**Tech Stack:** Linux PSI and cgroup v2, systemd user slices/scopes, systemd-oomd, earlyoom, zram-generator, tmux 3.7, Python/pytest, Bash.

## Global Constraints

- Never inspect or record pane output, shell history, command arguments, clipboard contents, or raw ActivityWatch events.
- Do not kill an active process or disable swap during implementation without explicit user approval at that step.
- Preserve the compositor, terminal, tmux server, audio graph, networking, and SSH under pressure.
- Prefer terminating one bounded agent scope over allowing global reclaim or kernel OOM.
- Never automatically restart a scope that exceeded its memory limit; that creates a crash loop.
- Keep the existing NVMe swap partition as the only disk-backed working swap tier.
- Retain the 128 GiB emergency swap file on disk for rollback, but do not activate it by default.
- Zram resize and final topology verification require a controlled reboot.

---

## Evidence and Root Cause

Observed on 2026-07-30:

- Physical RAM: 15.5 GiB; MemAvailable: 1.30 GiB.
- Active swap: 24 GiB zram + 32 GiB NVMe + 128 GiB SATA/Btrfs emergency file.
- Zram held 11.76 GiB of original pages using 7.10 GiB of physical RAM, only a 1.66:1 effective ratio—not the configured 2.7:1 assumption.
- Current `app.slice`: 3.67 GiB resident plus 11.26 GiB swap.
- Seven `tmux-spawn-*` scopes contained up to 408 tasks each; the largest retained 1.75 GiB resident plus 3.80 GiB swap.
- Kernel memory PSI showed `full avg300=2.63`, meaning all runnable work was stalled on memory for 2.63% of the previous five minutes.
- Six kernel OOM kills occurred during the current boot: three Chrome, two Chromium, and one Claude process. Every victim was inside a `tmux-spawn-*` scope.
- At the latest OOM, 158.7 GiB of disk swap was still free while zram consumed about 10.5 GiB of physical memory. Linux does not automatically spill already-swapped zram pages into a lower-priority swap device.
- `earlyoom` requires both memory and swap thresholds. Its `-m 5 -s 65` policy could not trigger because the 128 GiB emergency file kept aggregate free swap above 65%.
- `performance-mode.sh` changes `agent.slice`, but the observed workloads lived in `app.slice`; `agent.slice` was inactive. Its memory safeguards therefore protected nothing.
- Performance mode disabled visual effects but did not contain, reclaim, or stop the workloads creating memory pressure.

Primary failure chain:

```text
unbounded pane workloads
  → browser/dev-server descendants accumulate
  → high-priority 24 GiB zram consumes ~7–11 GiB physical RAM
  → 128 GiB emergency swap prevents earlyoom's percentage gate
  → agent.slice limits do not apply because workloads are in app.slice
  → global reclaim and PSI stalls
  → kernel OOM kills Chrome/Claude inside tmux scopes
  → agent command exits and the tmux pane appears dead
```

---

### Task 1: Make Memory Policy Testable and Topology-Aware

**Files:**
- Create: `scripts/memory-policy.py`
- Create: `tests/test_memory_policy.py`
- Modify: `scripts/apply-memory-latency-policy.sh`

**Interfaces:**
- Produces: `MemoryPolicy` dataclass and `render_sysctl()`, `render_zram()`, `render_earlyoom()`, and `diagnose(snapshot)` functions.
- Produces CLI: `memory-policy status --json` and `memory-policy render --format {sysctl,zram,earlyoom}`.
- Consumes only aggregate `/proc/meminfo`, `/proc/pressure/memory`, `/proc/swaps`, `/sys/block/zram0/mm_stat`, and systemd property values; never process arguments.

- [ ] **Step 1: Write failing policy tests**

Cover these observable contracts:

```python
def test_zram_capacity_is_half_of_16gib_ram():
    assert MemoryPolicy.for_ram_gib(16).zram_gib == 8


def test_emergency_swap_is_not_enabled_by_default():
    assert MemoryPolicy.for_ram_gib(16).enable_emergency_swap is False


def test_diagnosis_rejects_large_zram_with_poor_compression():
    result = diagnose(Snapshot(ram_gib=16, zram_capacity_gib=24,
        zram_original_gib=11.76, zram_physical_gib=7.10,
        emergency_swap_active=True, emergency_swap_gib=128))
    assert "zram-self-pressure" in result.causes
    assert "earlyoom-denominator-dilution" in result.causes
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest -q tests/test_memory_policy.py`

Expected: import failure because `scripts/memory-policy.py` does not exist.

- [ ] **Step 3: Implement the pure policy and diagnostic functions**

Use these fixed policy values for this 16 GiB host:

```text
zram capacity: 8 GiB
zram algorithm: zstd
zram priority: 200
NVMe swap priority: 50
emergency file: inactive by default
vm.swappiness: 100
vm.page-cluster: 0
vm.vfs_cache_pressure: 50
vm.watermark_scale_factor: 125
vm.overcommit_memory: 0
```

`status --json` must report current topology, zram effective ratio, zram physical cost, MemAvailable, PSI, cgroup totals, and policy deviations without changing the machine.

- [ ] **Step 4: Make the installer consume rendered policy**

Replace duplicated heredoc values in `apply-memory-latency-policy.sh` with output from `memory-policy render`. Add `--check` and `--apply` modes; default to `--check`. `--apply` must print the required reboot and must not call `swapoff` on a device with nonzero use.

- [ ] **Step 5: Verify GREEN and commit**

Run: `pytest -q tests/test_memory_policy.py`

Run: `python3 scripts/memory-policy.py status --json | jq -e '.causes | length > 0'`

Commit: `fix(memory): make pressure policy topology-aware`

---

### Task 2: Bound Zram and Remove the Swap-Denominator Trap

**Files:**
- Modify: `scripts/apply-memory-latency-policy.sh`
- Modify: `scripts/setup-freeze-guard.sh`
- Test: `tests/test_memory_policy.py`

**Interfaces:**
- Consumes Task 1 policy renderers.
- Produces `/etc/systemd/zram-generator.conf`, `/etc/sysctl.d/99-z-memory-latency.conf`, `/etc/default/earlyoom`, and an `/etc/fstab` proposal after explicit root approval.

- [ ] **Step 1: Add failing rendered-configuration tests**

Assert that rendered zram is `min(ram / 2, 8192)`, emergency swap is absent from active fstab output, and earlyoom no longer depends on a 192 GiB aggregate percentage denominator.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_memory_policy.py -k 'render or earlyoom or emergency'`

Expected: current render still emits 24 GiB zram and activates the emergency file.

- [ ] **Step 3: Implement the corrected hierarchy**

Generate:

```ini
[zram0]
zram-size = min(ram / 2, 8192)
compression-algorithm = zstd
swap-priority = 200
options = discard
```

Keep the existing 32 GiB NVMe partition at priority 50. Remove the 128 GiB emergency file from automatic activation, but preserve the file and create a documented one-command rollback entry.

Generate earlyoom thresholds using absolute KiB values derived from the expected 40 GiB active swap topology: send SIGTERM below 12% available RAM once free swap falls below 30 GiB; send SIGKILL below 6% available RAM once free swap falls below 24 GiB. Retain the existing avoid/prefer process classes and enable a 60-second memory report so interventions are auditable.

- [ ] **Step 4: Apply only after explicit root-operation approval**

Back up every target file. Install generated files. Do not resize active zram in place. Schedule a controlled reboot.

- [ ] **Step 5: Verify after reboot**

Run:

```text
swapon --show --bytes
cat /sys/block/zram0/mm_stat
sysctl vm.swappiness vm.page-cluster vm.watermark_scale_factor
systemctl status earlyoom --no-pager
```

Expected: 8 GiB zram, 32 GiB NVMe swap, no active 128 GiB emergency file, and earlyoom running with absolute thresholds.

- [ ] **Step 6: Commit**

Commit: `fix(memory): bound compressed swap and activate freeze guard`

---

### Task 3: Put Every Agent Workload in `agent.slice`

**Files:**
- Create: `scripts/agent-scope.sh`
- Modify: `scripts/tmux-agent-launcher.sh`
- Modify: `config/systemd/user/agent.slice`
- Modify: `scripts/onboard`
- Create: `tests/test_agent_scope.py`

**Interfaces:**
- Produces CLI: `agent-scope run --name NAME -- COMMAND [ARG...]`.
- `agent-scope` invokes `systemd-run --user --scope --collect --slice=agent.slice` with per-scope properties.
- The tmux launcher waits for the scope to exit and then returns to an interactive shell; it does not `exec` over the durable pane shell.

- [ ] **Step 1: Write failing launcher and slice tests**

Assert:

```python
def test_agent_scope_uses_agent_slice_and_limits():
    command = build_scope_command("claude", ["claude"])
    assert "--slice=agent.slice" in command
    assert "MemoryHigh=2G" in command
    assert "MemoryMax=3G" in command
    assert "MemorySwapMax=4G" in command
    assert "TasksMax=512" in command


def test_tmux_launcher_does_not_exec_over_pane_shell():
    assert launcher_command("claude").returns_to_shell
```

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_agent_scope.py`

Expected: missing module/command builder and current launcher uses `exec systemd-run`.

- [ ] **Step 3: Implement the scope wrapper**

Per-agent scope properties:

```text
MemoryHigh=2G
MemoryMax=3G
MemorySwapMax=4G
TasksMax=512
CPUWeight=50
IOWeight=25
OOMScoreAdjust=300
OOMPolicy=stop
```

Aggregate `agent.slice` properties:

```text
MemoryHigh=6G
MemoryMax=8G
MemorySwapMax=8G
CPUWeight=50
IOWeight=25
ManagedOOMMemoryPressure=kill
ManagedOOMMemoryPressureLimit=60%
```

The wrapper must propagate the child exit status, display whether the scope was OOM-killed, and return control to the existing pane shell.

- [ ] **Step 4: Route every supported launcher through the wrapper**

Replace direct `systemd-run` assembly in `tmux-agent-launcher.sh`. Update fleet/dashboard launch paths that start Claude, Grok, Codex, OMP, or browser-backed harnesses. Do not wrap unrelated interactive shells.

- [ ] **Step 5: Verify with a safe transient cap**

Start a disposable scope with `MemoryMax=128M` and a Python process that requests 192 MiB. Assert that the scope fails, the invoking shell remains alive, `tmux list-panes` still reports the pane, and no kernel global-OOM record is added.

- [ ] **Step 6: Commit**

Commit: `fix(tmux): contain agents without killing pane shells`

---

### Task 4: Make Pressure Control Act on Real Workloads

**Files:**
- Modify: `scripts/performance-pressure.py`
- Modify: `scripts/performance-mode.sh`
- Modify: `config/systemd/user/performance-pressure.service`
- Create: `tests/test_performance_pressure.py`

**Interfaces:**
- `Sampler.sample()` adds `agent memory`, `agent swap`, and `agent tasks` scores from aggregate `agent.slice` properties.
- Performance mode adjusts only the already-active `agent.slice`; absence of an active slice is reported as a configuration fault.
- systemd-oomd performs scope selection and termination; the Python monitor never selects or kills processes itself.

- [ ] **Step 1: Write failing pressure tests**

Use fixture snapshots proving that 6 GiB agent memory, 6 GiB agent swap, or more than 1500 tasks triggers pressure even when CPU/GPU are idle. Assert that an inactive `agent.slice` produces a visible `containment missing` cause rather than silently succeeding.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_performance_pressure.py`

Expected: current sampler has no cgroup metrics and silently writes properties to an inactive slice.

- [ ] **Step 3: Implement cgroup-aware scoring**

Read aggregate properties through `systemctl --user show agent.slice`. Keep visual degradation, but treat it as secondary. Notifications must distinguish visual performance mode from cgroup reclaim and identify whether a scope was terminated by systemd-oomd.

- [ ] **Step 4: Enable systemd-oomd only for the bounded agent hierarchy**

Enable `systemd-oomd.service` and its socket at the system level. Do not enable pressure-based killing on `user.slice`, `app.slice`, or the desktop session. Verify that only `agent.slice` advertises `ManagedOOMMemoryPressure=kill`.

- [ ] **Step 5: Verify and commit**

Run: `pytest -q tests/test_performance_pressure.py`

Run: `scripts/performance-pressure.py --once`

Commit: `fix(performance): react to agent cgroup pressure`

---

### Task 5: Preserve and Explain tmux Pane Failure State

**Files:**
- Modify: `config/.tmux.conf`
- Create: `scripts/tmux-pane-health.sh`
- Create: `tests/test_tmux_pane_health.py`

**Interfaces:**
- `tmux-pane-health record PANE_ID` records only pane ID, exit status, scope result, and timestamp—never output or command arguments.
- A `pane-died` hook displays the exit reason and recovery key.
- Existing prefix+`R` remains the explicit respawn action.

- [ ] **Step 1: Write failing isolated-tmux tests**

Create a temporary tmux server, run a pane that exits nonzero, and assert the pane remains visible with a failure reason and `R: respawn` guidance. Assert that an OOM-reclaimed agent returns to the pane shell instead of producing a dead pane.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_tmux_pane_health.py`

Expected: no health hook or structured failure state exists.

- [ ] **Step 3: Implement explicit recovery behavior**

Keep `remain-on-exit failed`. Add a nonblocking `pane-died` hook. Do not auto-respawn; repeated memory failure must require an explicit user action. Update `R` to respawn in the previous working directory and clear the recorded failure only after successful startup.

- [ ] **Step 4: Verify and commit**

Run: `pytest -q tests/test_tmux_pane_health.py`

Commit: `fix(tmux): preserve pane state after workload failure`

---

### Task 6: Prevent Browser and Dev-Server Accumulation

**Files:**
- Create: `scripts/agent-scope-audit.py`
- Modify: `scripts/agent-scope.sh`
- Modify: `config/systemd/user/performance-pressure.service`
- Create: `tests/test_agent_scope_audit.py`

**Interfaces:**
- `agent-scope-audit --json` reports scope age, aggregate memory, swap, task count, active harness state, and pressure status without command arguments.
- Audit mode never kills anything.
- Cleanup occurs automatically only when the owning scope ends; active-scope termination remains systemd-oomd policy or an explicit user action.

- [ ] **Step 1: Write failing lifecycle tests**

Model an agent that launches a browser and dev server, then exits. Assert all descendants leave with the collected scope. Model a still-active scope and assert audit reports it without terminating it.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_agent_scope_audit.py`

Expected: no lifecycle auditor exists and current descendants can remain under long-lived pane scopes.

- [ ] **Step 3: Implement audit and scope cleanup**

Use cgroup membership and Workspace Copilot semantic harness state only. Never inspect pane output or process arguments. Surface scopes above 1.5 GiB memory, 2 GiB swap, 400 tasks, or 12 hours old. Ensure transient scope collection removes browser/dev-server descendants when the agent exits.

- [ ] **Step 4: Add advisory pressure notification**

Performance pressure may notify with the scope ID and aggregate evidence. It must not synthesize arbitrary kill commands or automatically terminate an active scope outside systemd-oomd policy.

- [ ] **Step 5: Verify and commit**

Run: `pytest -q tests/test_agent_scope_audit.py`

Commit: `feat(performance): expose agent scope lifecycle leaks`

---

### Task 7: End-to-End Freeze and Recovery Verification

**Files:**
- Modify: `tests/test_memory_policy.py`
- Modify: `tests/test_agent_scope.py`
- Modify: `tests/test_tmux_pane_health.py`

**Interfaces:**
- Consumes all previous tasks.
- Produces recorded evidence from a controlled pressure scenario and rebooted topology.

- [ ] **Step 1: Run focused regression suites**

Run:

```text
pytest -q tests/test_memory_policy.py tests/test_agent_scope.py tests/test_performance_pressure.py tests/test_tmux_pane_health.py tests/test_agent_scope_audit.py
```

Expected: all pass.

- [ ] **Step 2: Validate installed configuration without mutation**

Run `memory-policy status --json` and require:

```text
zram capacity <= 8 GiB
zram physical use bounded by configured capacity
emergency swap inactive
agent.slice active while an agent runs
all supported agents below agent.slice
every agent scope has finite MemoryHigh/MemoryMax/MemorySwapMax/TasksMax
earlyoom thresholds consistent with active swap
systemd-oomd kill policy absent from desktop/app slices
```

- [ ] **Step 3: Exercise controlled pressure**

Inside a disposable agent scope, allocate memory progressively above its 128 MiB test limit. Confirm the scope is reclaimed, the tmux pane shell survives, Hyprland/Kitty remain responsive, and `/proc/pressure/memory` returns toward baseline. Do not test by exhausting global RAM.

- [ ] **Step 4: Observe a normal work interval**

During at least one representative multi-agent interval, record aggregate PSI, MemAvailable, zram physical cost, NVMe swap use, agent-slice memory/swap/tasks, earlyoom actions, and kernel OOM count. Acceptance requires zero new global OOM kills and no dead panes caused by agent reclamation.

- [ ] **Step 5: Final review and commit**

Review every generated system file and rollback path. Commit: `test(performance): verify bounded agent pressure recovery`

---

## Rollback

1. Stop new agent launches.
2. Restore timestamped `/etc` backups created by the installer.
3. Disable `ManagedOOMMemoryPressure` on `agent.slice` if it reclaims healthy workloads.
4. Restore the previous zram file only during a controlled reboot.
5. Reactivate the emergency swap file only if NVMe swap is unavailable and the user explicitly accepts severe latency.
6. The tmux launcher can bypass `agent-scope` temporarily while preserving the durable-shell behavior.

## Acceptance Criteria

- No new kernel global-OOM kills during representative multi-agent operation.
- The desktop remains interactive before and during agent-scope reclamation.
- Zram cannot consume more than the bounded 8 GiB uncompressed capacity.
- The 128 GiB emergency file no longer suppresses earlyoom or permits hours of swap thrash.
- Every launched agent and its browser/dev-server descendants belongs to `agent.slice`.
- `agent.slice` is aggregate-bounded and individual scopes are finite.
- Reclaimed agents return control to a live pane shell or leave an explicit, recoverable failure pane.
- No automatic crash/restart loop is introduced.
- Privacy-safe diagnostics expose aggregate causes without pane content or command arguments.
