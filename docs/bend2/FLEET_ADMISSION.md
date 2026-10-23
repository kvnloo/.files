# Fleet admission law: pure decision, host adapters and next proof slices

Scope: **kvnloo/.files only**. This is the law slice for [z0intelligence #199](https://github.com/kvnloo/z0intelligence/issues/199), built on [.files #38](https://github.com/kvnloo/.files/pull/38). It preserves the second parent from [context/bend2-laws](https://github.com/kvnloo/.files/pull/47). No new registry, queue, scheduler, store, host activation, phone interaction, or default-branch write.

## Actual implementation and limits

- The production host command is 'scripts/fleet run', using 'config/fleet/nodes.yaml' to select a registered worker. 'scripts/fleet-build' is the wrapper; 'z0-guard' remains the separate owner ops gate from z0intelligence #192. No parallel router exists.
- 'scripts/fleet_admission.py:decide' is an effect-free reducer. Its inputs classify the *selected* target (missing / groot / remote), qualification, observed availability, available lane room and source-transfer state. Its outputs are typed 'Refuse(reason)', 'Prepare' and 'Admit'. The only admitted target is a qualified, available remote with room and completed transfer or explicit '--no-src'.
- The reducer is wired into the real 'scripts/fleet' before remote preparation and before invoking a runtime command; it is checked after both tar production and extraction return successfully. An unavailable, unqualified, unknown, missing or groot pin ends with **exit 75** and a nonempty 'Refuse[REASON]'; source-transfer failure ends with the pre-existing nonzero operational class **exit 1**, now with 'Refuse[SOURCE_TRANSFER_FAILED]'. Unrelated SSH setup errors and runtime exits are NOT converted into admission retry codes. The old 'fleet-build --node groot' early refusal remains exit **2** (now invariant even with 'Z0_GUARD_O1=off|report'). The shell preserves the reason and only retries a typed 'NO_ROOM' refusal.
- Tests cannot tell that a real SSH peer is the intended physical worker, that source bytes after extraction have been independently attested, that a remote toolchain is trustworthy, or that a real job finished correctly. 'source_semantics_attested=false'. The Bend proof and these replay/test inputs are **not permission**. Runtime permission, privacy scope and owner consent remain at their native boundaries.

## Four owner laws, exact status and verification path

### F1 — no groot fallback (implemented, pure proof)

**Bend proposition**: for every qualification boolean q, availability a, capacity r and transfer state t,

    MODEL.decide(FGroot, q, a, r, t) = FRefuse(RGrootForbidden).

A missing pin refuses independently. Remote qualification/availability/capacity failures produce typed refusals, never an alternate target. The proof obligation is 'LAWS.never_groot_fallback', plus 'missing_remote_refuses', 'unqualified_refuses', 'unavailable_refuses', and 'no_room_refuses'; 'PROOF.bend' imports those exact signatures. Positive remote cases are proven separately.

**CI**: actual pinned 'bend PROOF.bend --verdict'; all 96 finite-domain Bend↔Python cases; mocked 'fleet cmd_run' refuses a groot pin before constructing SSH; POSIX shell checks explicit groot refusal under O1 enforce/report/off. Check both producer/extractor failure cases do not attempt fallback.

**Concolic boundary plan**: instrument branch predicates 'pin_known', 'role==worker', 'qualified', 'probe_valid', 'capacity_ok'. Symbolically solve 'role!=worker ∧ qualified ∧ probe_valid ∧ capacity_ok', then negate 'role==worker' in the observed path to exercise a poisoned registry with a server accidentally labeled lane-enabled. Execute concrete solutions against the isolated process mocks; assert no SSH/runtime calls and no target re-selection. Random fuzzing alone does not satisfy this plan.

### F2 — every exit-75 admission refusal carries a typed reason (host fixture, pure proof for the reasons)

**Bend proposition**: an unqualified selected remote always returns 'FRefuse(RUnqualified)', an unavailable one 'FRefuse(RUnavailable)', and a room-starved one 'FRefuse(RNoRoom)', universally over all later transfer states. Missing and groot have their own explicit reason constructors. The sum type has no empty-reason constructor. 'Prepare' is not an admission refusal and no 'Admit' has an exit-75 translation.

**Proof obligation**: those five named laws in 'LAWS.bend'; separately establish the adapter implication 'return_code=75 ⇒ Refuse[nonempty typed Reason]'. The latter is a **Python/shell integration assertion**, not a Bend theorem about exit(75). User command errors and remote runtime return code 75 must not be falsely relabeled; a remote job exit 75 is opaque and unchanged.

**CI**: exhaustive 96-state table, shell 'fleet-build --node nonexistent-worker --wait 0 --class build -- echo ...' and mocked CLI; assert code 75, reason label, and no worker process launched. Existing early shell refusal of explicit groot retains code 2.

**Concolic boundary plan**: collect a symbolic path condition for each of 'unknown pin', 'wrong class', 'paused worker', 'bad probe', and 'insufficient MiB'. Flip one predicate at a time with an SMT solver while holding the earlier branch predicates; replay the corresponding concrete case through the stubbed CLI. Observe 'exit_status' and 'stderr' together; assert stable enum labels and nonempty explanation, never infer success from text alone.

### F3 — failed source transfer refuses execution (implemented, pure proof)

**Bend proposition**:

    MODEL.decide(FRemote, True, True, True, TFailed) = FRefuse(RSourceFailed)

and a pending transfer returns 'FPrepare', not 'FAdmit'. A completed transfer or explicit no-source transfer admits a qualified remote (the two positive liveness cases). This models the **same decision** that guards the real SSH remote-run boundary.

**Proof obligation**: 'source_transfer_fails_closed', 'source_pending_cannot_execute', 'delivered_remote_admits' and 'no_source_remote_admits'. Archive producer and remote extractor exit statuses must both be zero before the adapter supplies 'TComplete'. Actual source fidelity is not attested by exit status alone.

**CI**: mocked tar producer exit 1 / extractor exit 0, inverse, both failing, and remote runtime exit 23; no real SSH, tar, device or build effects. Bend/Python parity and the deliberate MODEL 'no room ⇒ Admit' mutation must not pass the unchanged owner LAWS/PROOF. The CI reference must pass before a mutation failure counts.

**Concolic boundary plan**: instrument the transfer boundary's symbolic flags 'has_git', 'tar_spawn_ok', 'extract_spawn_ok', 'tar_exit', 'extract_exit'; use an SMT solver to negate the observed 'tar_exit==0 ∧ extract_exit==0' branch while retaining the prefix that selected a qualified remote. Replay solver-generated concrete nonzero producer, extractor and broken-pipe paths into mock Popen objects; assert that no runtime Popen occurs. Also flip to both-zero as a required positive case.

### F4 — eviction minimum reclaim within common capacity (design only, no activation)

Registry 'config/fleet/nodes.yaml' currently has kubelet soft/hard 'memory.available' thresholds (e.g. 1536Mi soft, 1Gi hard), but **no reviewed fleet-level minimum-reclaim policy**. Do not reinterpret these thresholds as an existing Bend eviction gate. Propose a future separate 'EvictInput' with 'pressure_threshold_mib', 'minimum_reclaim_mib', 'capacity_mib' and 'target_mib', all validated **integer MiB** derived from a named capacity basis. Unknown quantities, nonintegral units, negative values, overflow, 'threshold + reclaim > capacity', or inconsistent capacity references yield 'Refuse(ConfigUnknownOrImpossible)'.

**Bend proposition**: for every admitted input 'x', 'target_mib(x) >= pressure_threshold_mib(x) + minimum_reclaim_mib(x)' and 'target_mib(x) <= capacity_mib(x)'; no overflow/wrapping. For every unknown or impossible input, 'Evict(x)' returns a typed refusal. A future PROOF must quantify over bounds, including equalities; no proof is claimed here.

**Proof obligation**: unit-normalization and capacity lineage at the kubelet/host boundary are separate adapter duties; the pure Bend law establishes only inequalities and fail-closed arithmetic over bounded Nat inputs. Never evict a real worker based on an unreviewed sample.

**CI plan**: future pure fixtures at 0, threshold-1, threshold, threshold+reclaim-1, threshold+reclaim, capacity and capacity+1; mismatched MiB/GiB, malformed/unknown config, overflow and impossible target are refused. No live eviction, cordon or job effects.

**Concolic boundary plan**: symbolically collect constraints 'known ∧ same_capacity_basis ∧ threshold>=0 ∧ reclaim>=0 ∧ threshold+reclaim<=capacity ∧ target>=threshold+reclaim'; flip the target lower-bound and sum upper-bound separately. SMT models become concrete fixture values at equality and +/-1 edges. Run only against the future pure adapter before any kubelet connector exists. Fuzzing is supplemental, not concolic execution.

## Verifier, boundaries and OMP commands

Toolchain manifest: 'bend/fleet_admission/toolchain.json', pinned to upstream Bend 2.0.34 **linux-x64** release SHA-256 '78106a97af242429dcc057258eb8d10f69cddebcd5e263022185a52d003e09bf'. This digest and URL were read from the upstream GitHub release; CI checks exact bytes, unpacks, refuses missing executables, invokes the actual kernel via 'bend PROOF.bend --verdict' and requires 'ALL PROOFS CHECK'. CI does not skip verification when download or execution fails. Do not pass through an ambient 'BENDTT' override. The tool's '--verdict' is a kernel recheck, *not* a source→runtime compiler equivalence claim. No external Lean binary or unchecked kernel URL is invented.

For OMP on the **Intel MBP**, an independently published Bend 2.0.34 'darwin-x64' archive has SHA-256 '066d4a07a1871a2946be8f42f926582bfda5f13ff728c234ffe79635bd240650'. Use the exact upstream release URL with that platform suffix and check the digest before unpacking. Run in a **scratch checkout**, never on an active served worktree:

~~~sh
python3 -m venv .venv-admission
. .venv-admission/bin/activate
python -m pip install 'PyYAML==6.0.2'
python -m unittest discover -s tests -p 'test_fleet_admission.py' -v

# Set BEND to the SHA-256-verified 2.0.34 executable (not a PATH fallback).
(cd bend/fleet_admission && env -u BENDTT "$BEND" PROOF.bend --verdict)
python tests/fleet_admission_parity.py
python tests/fleet_admission_mutation.py
~~~

No commands above were run by this ChatGPT worker. OMP must collect actual outputs, kernel version and CI job URL; an unrun proof is not green.

## Ordered follow-up file ownership (not implemented)

1. **OMP MBP qualification:** verify the pinned executable's packaging and kernel invocation, run the three test commands and record an actual signed/verifiable CI receipt. Owners: 'bend/fleet_admission/toolchain.json', '.github/workflows/bend2-fleet-admission.yml', tests. Fail closed on an unknown binary location or missing kernel.
2. **Fleet adapter independent attestation:** prove extracted tree digest, observed selected peer and source revision at the host boundary; do not convert an archive exit code into cryptographic fidelity. Owners: 'scripts/fleet', 'tests/test_fleet_admission.py'; reuse existing state/receipt paths, no new store.
3. **Admission exit-class hardening:** verify additional transfer/SSH failure injection and remote runtime 75 opacity with a controlled shell adapter harness. Owners: 'scripts/fleet-build', 'scripts/fleet', 'tests/test_fleet_admission.py'. Preserve the typed reason from the run process.
4. **Eviction law owner review:** agree pressure/reclaim policy and memory capacity basis; only then introduce 'bend/fleet_admission/EVICTION_MODEL.bend', its owner 'LAWS' and proof, and pure 'scripts/fleet_eviction.py' tests. Owners: 'config/fleet/nodes.yaml', 'bend/fleet_admission/', 'scripts/fleet_eviction.py', 'tests/'; explicit config unknown/impossible must refuse. No live host activation.
5. **Concolic expansion:** implement symbolic path-constraint capture + SMT-guided branch flipping for F1–F4, replaying into existing pure adapters; owner 'tests/' and 'bend/fleet_admission/'. Random fuzzing alone is not accepted evidence.

Evidence ownership remains: z0 capability registry; .files host intent; z0intelligence cognitive/memory contracts; z0bridge transport; kerdoios capacity; oss-factory worker coordination; harness native seams. No old memory/approval can grant execution. No contribution or credit from the existing #34/#36/#37/#38 or Victor Taelin's Bend work is appropriated.
