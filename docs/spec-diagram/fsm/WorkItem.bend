# Work-item lifecycle: the transition function (the statechart, as code).
#
# One work item moves Proposed -> Claimed -> Implementing -> Verifying ->
# DraftPR -> Integrated -> Deployed -> Accepted -> Merged, with Blocked,
# Interrupted and Abandoned on the side. docs/fsm/work-item.mmd draws it;
# src/z0int/fsm/work_item.py is the same table in Python (the replay
# checker), kept equal by tests/test_fsm_bend_parity.py.
#
# Each state carries exactly the evidence it needs, so a state that would
# break a law cannot be built by a legal step:
#   au: the author (the actor that claimed or resumed the work)
#   hd: the head SHA under work (abstracted to a Nat)
#   ig: the integration-branch head the item landed in
#   dp: the head the running service actually serves
#   ap: the actor that accepted the deployed result
#
# A step that the guards refuse leaves the item unchanged. The replay
# checker reports every refused event as a violation.

import Base

# Roles follow docs/roles-v0.md (ROLES-v0, 2026-10-20).
type Role is Data:
  Owner{}
  Opus{}
  Sol{}
  Chat{}
  Free{}
  Jev{}
  Slm{}
  Ci{}

type Actor is Data:
  Actor{id: Nat, role: Role}

type Receipt is Data:
  Receipt{sha: Nat, pass: Bool}

type Item is Data:
  Proposed{}
  Claimed{au: Actor}
  Implementing{au: Actor, hd: Nat}
  Verifying{au: Actor, hd: Nat}
  DraftPR{au: Actor, hd: Nat}
  Integrated{au: Actor, hd: Nat, ig: Nat}
  Deployed{au: Actor, hd: Nat, ig: Nat, dp: Nat}
  Accepted{au: Actor, hd: Nat, ig: Nat, ap: Actor}
  Merged{au: Actor, hd: Nat, ig: Nat, ap: Actor}
  Blocked{au: Actor, hd: Nat}
  Interrupted{au: Actor, hd: Nat}
  Abandoned{}

type Ev is Data:
  Claim{a: Actor}
  Start{a: Actor}
  Push{a: Actor, sha: Nat}
  Submit{a: Actor}
  Verify{a: Actor, r: Receipt}
  Integrate{a: Actor, ish: Nat, r: Receipt}
  Deploy{a: Actor, served: Nat}
  Observe{served: Nat}
  Accept{a: Actor}
  Merge{a: Actor}
  Block{a: Actor}
  Unblock{a: Actor}
  Interrupt{}
  Resume{a: Actor}
  Abandon{a: Actor}

# Role table (docs/roles-v0.md)
# -----------------------------
#   Owner  Kevin: taste, physical world, credentials, irreversible approvals
#   Opus   frontier lane: design, verification, hard code, orchestration
#   Sol    Sol on pi/SoL-Pi (MBP) or omp: bulk well-specified coding
#   Chat   ChatGPT app, Grok, Muse: advice and specs, no sandbox, no origin
#   Free   free models: scans, triage, summaries; never code (owner rule)
#   Jev    fast chooser among prevalidated options; never writes
#   Slm    shadow network; shadow-only until promoted; never writes
#   Ci     deterministic code: CI, tests, service-branch checks, replay

# may write code for a work item: Opus or the Sol lane. Chat apps have no
# sandbox; free models, Jev and SLMs pick, rank and gate; none implement.
def coder(r: Role) -> Bool:
  match r:
    case Opus{}:
      True{}
    case Sol{}:
      True{}
    case _:
      False{}

def is_ci(r: Role) -> Bool:
  match r:
    case Ci{}:
      True{}
    case _:
      False{}

def is_owner(r: Role) -> Bool:
  match r:
    case Owner{}:
      True{}
    case _:
      False{}

# may integrate into an integration branch or deploy a service:
# deterministic code (checks-gated) or the Opus orchestrator
def operator(r: Role) -> Bool:
  match r:
    case Ci{}:
      True{}
    case Opus{}:
      True{}
    case _:
      False{}

# may merge to the default branch: the owner, or deterministic code
# acting on the owner's recorded acceptance
def merger(r: Role) -> Bool:
  match r:
    case Ci{}:
      True{}
    case Owner{}:
      True{}
    case _:
      False{}

# may unblock or abandon: the owner or the Opus orchestrator
def steward(r: Role) -> Bool:
  match r:
    case Owner{}:
      True{}
    case Opus{}:
      True{}
    case _:
      False{}

def rid(a: Actor) -> Nat:
  match a:
    case Actor{id, role}:
      id

def rrole(a: Actor) -> Role:
  match a:
    case Actor{id, role}:
      role

# the actor a is the author au
def same(+a: Actor, +au: Actor) -> Bool:
  Nat.is_eq(rid(a), rid(au))

# a gate passed by someone other than the author
def other(+a: Actor, +au: Actor) -> Bool:
  Bool.not(Nat.is_eq(rid(a), rid(au)))

# Guarded outcomes. Each takes its guard as a parameter so the proofs can
# split on it.
# -------------------------------------------------------------------------

def pick(ok: Bool, x: Item, y: Item) -> Item:
  match ok:
    case True{}:
      x
    case False{}:
      y

# Verifying + Verify: the gate (a CI actor that is not the author) decides
# whether the receipt counts at all; then a passing receipt bound to the
# head opens the draft PR, and anything else sends the work back.
def verify_out(gate: Bool, good: Bool, +au: Actor, +hd: Nat) -> Item:
  match gate:
    case True{}:
      pick(good, DraftPR{au, hd}, Implementing{au, hd})
    case False{}:
      Verifying{au, hd}

def verify_gate(+a: Actor, +au: Actor) -> Bool:
  Bool.and(is_ci(rrole(a)), other(a, au))

def receipt_good(r: Receipt, +hd: Nat) -> Bool:
  match r:
    case Receipt{sha, pass}:
      Bool.and(pass, Nat.is_eq(sha, hd))

def integrate_gate(+a: Actor, +au: Actor) -> Bool:
  Bool.and(operator(rrole(a)), other(a, au))

def accept_gate(+a: Actor, +au: Actor) -> Bool:
  Bool.and(is_owner(rrole(a)), other(a, au))

# Per-state transition tables
# ---------------------------

def from_proposed(e: Ev) -> Item:
  match e:
    case Claim{+a}:
      pick(coder(rrole(a)), Claimed{a}, Proposed{})
    case Abandon{+a}:
      pick(steward(rrole(a)), Abandoned{}, Proposed{})
    case _:
      Proposed{}

def from_claimed(+au: Actor, e: Ev) -> Item:
  match e:
    case Start{+a}:
      pick(same(a, au), Implementing{au, 0n}, Claimed{au})
    case Interrupt{}:
      Interrupted{au, 0n}
    case Abandon{+a}:
      pick(steward(rrole(a)), Abandoned{}, Claimed{au})
    case _:
      Claimed{au}

def from_implementing(+au: Actor, +hd: Nat, e: Ev) -> Item:
  match e:
    case Push{+a, sha}:
      pick(same(a, au), Implementing{au, sha}, Implementing{au, hd})
    case Submit{+a}:
      pick(same(a, au), Verifying{au, hd}, Implementing{au, hd})
    case Block{a}:
      Blocked{au, hd}
    case Interrupt{}:
      Interrupted{au, hd}
    case _:
      Implementing{au, hd}

def from_verifying(+au: Actor, +hd: Nat, e: Ev) -> Item:
  match e:
    case Verify{+a, r}:
      verify_out(verify_gate(a, au), receipt_good(r, hd), au, hd)
    case Block{a}:
      Blocked{au, hd}
    case Interrupt{}:
      Interrupted{au, hd}
    case _:
      Verifying{au, hd}

def integrate_out(gate: Bool, +au: Actor, +hd: Nat, +ish: Nat) -> Item:
  match gate:
    case True{}:
      Integrated{au, hd, ish}
    case False{}:
      DraftPR{au, hd}

def from_draft(+au: Actor, +hd: Nat, e: Ev) -> Item:
  match e:
    case Integrate{+a, +ish, r}:
      integrate_out(Bool.and(integrate_gate(a, au), receipt_good(r, ish)), au, hd, ish)
    case _:
      DraftPR{au, hd}

def deploy_out(ok: Bool, +au: Actor, +hd: Nat, +ig: Nat, +served: Nat) -> Item:
  match ok:
    case True{}:
      Deployed{au, hd, ig, served}
    case False{}:
      Integrated{au, hd, ig}

def from_integrated(+au: Actor, +hd: Nat, +ig: Nat, e: Ev) -> Item:
  match e:
    case Deploy{+a, +served}:
      deploy_out(Bool.and(operator(rrole(a)), Nat.is_eq(served, ig)), au, hd, ig, served)
    case _:
      Integrated{au, hd, ig}

# Deployed + Observe: a service found serving anything but the integrated
# head is no longer deployed; the item drops back to Integrated.
def observe_out(ok: Bool, +au: Actor, +hd: Nat, +ig: Nat, +dp: Nat) -> Item:
  match ok:
    case True{}:
      Deployed{au, hd, ig, dp}
    case False{}:
      Integrated{au, hd, ig}

def accept_out(ok: Bool, +au: Actor, +hd: Nat, +ig: Nat, +dp: Nat, +a: Actor) -> Item:
  match ok:
    case True{}:
      Accepted{au, hd, ig, a}
    case False{}:
      Deployed{au, hd, ig, dp}

def from_deployed(+au: Actor, +hd: Nat, +ig: Nat, +dp: Nat, e: Ev) -> Item:
  match e:
    case Observe{+served}:
      observe_out(Nat.is_eq(served, ig), au, hd, ig, dp)
    case Accept{+a}:
      accept_out(accept_gate(a, au), au, hd, ig, dp, a)
    case _:
      Deployed{au, hd, ig, dp}

def from_accepted(+au: Actor, +hd: Nat, +ig: Nat, +ap: Actor, e: Ev) -> Item:
  match e:
    case Merge{+a}:
      pick(merger(rrole(a)), Merged{au, hd, ig, ap}, Accepted{au, hd, ig, ap})
    case _:
      Accepted{au, hd, ig, ap}

def from_blocked(+au: Actor, +hd: Nat, e: Ev) -> Item:
  match e:
    case Unblock{+a}:
      pick(steward(rrole(a)), Implementing{au, hd}, Blocked{au, hd})
    case Abandon{+a}:
      pick(steward(rrole(a)), Abandoned{}, Blocked{au, hd})
    case _:
      Blocked{au, hd}

# Interrupted leaves only by Resume (a coder takes the pushed head over and
# becomes its author) or by Abandon (a steward's explicit decision).
def from_interrupted(+au: Actor, +hd: Nat, e: Ev) -> Item:
  match e:
    case Resume{+a}:
      pick(coder(rrole(a)), Implementing{a, hd}, Interrupted{au, hd})
    case Abandon{+a}:
      pick(steward(rrole(a)), Abandoned{}, Interrupted{au, hd})
    case _:
      Interrupted{au, hd}

def step(s: Item, e: Ev) -> Item:
  match s:
    case Proposed{}:
      from_proposed(e)
    case Claimed{au}:
      from_claimed(au, e)
    case Implementing{au, hd}:
      from_implementing(au, hd, e)
    case Verifying{au, hd}:
      from_verifying(au, hd, e)
    case DraftPR{au, hd}:
      from_draft(au, hd, e)
    case Integrated{au, hd, ig}:
      from_integrated(au, hd, ig, e)
    case Deployed{au, hd, ig, dp}:
      from_deployed(au, hd, ig, dp, e)
    case Accepted{au, hd, ig, ap}:
      from_accepted(au, hd, ig, ap, e)
    case Merged{au, hd, ig, ap}:
      Merged{au, hd, ig, ap}
    case Blocked{au, hd}:
      from_blocked(au, hd, e)
    case Interrupted{au, hd}:
      from_interrupted(au, hd, e)
    case Abandoned{}:
      Abandoned{}

# replay a tape of events from s (the tape shrinks, so this terminates)
def run(es: List<&2, Ev>, s: Item) -> Item:
  match es:
    case Nil{}:
      s
    case e <> t:
      run(t, step(s, e))

# Owner availability and the batched "needs Kevin" queue
# -------------------------------------------------------
# Kevin's attention is the bottleneck (docs/roles-v0.md): deep work comes in
# 90-180 min blocks, and he is not available around the clock. An event the
# owner must perform is held while he is off: the item waits in the batched
# queue, and nothing else waits with it.

type Avail is Data:
  DeepWork{}
  LowEnergy{}
  Off{}

def is_off(av: Avail) -> Bool:
  match av:
    case Off{}:
      True{}
    case _:
      False{}

# the event is an action the owner performs
def owner_event(e: Ev) -> Bool:
  match e:
    case Claim{a}:
      is_owner(rrole(a))
    case Start{a}:
      is_owner(rrole(a))
    case Push{a, sha}:
      is_owner(rrole(a))
    case Submit{a}:
      is_owner(rrole(a))
    case Verify{a, r}:
      is_owner(rrole(a))
    case Integrate{a, ish, r}:
      is_owner(rrole(a))
    case Deploy{a, served}:
      is_owner(rrole(a))
    case Observe{served}:
      False{}
    case Accept{a}:
      is_owner(rrole(a))
    case Merge{a}:
      is_owner(rrole(a))
    case Block{a}:
      is_owner(rrole(a))
    case Unblock{a}:
      is_owner(rrole(a))
    case Interrupt{}:
      False{}
    case Resume{a}:
      is_owner(rrole(a))
    case Abandon{a}:
      is_owner(rrole(a))

# the item is in the batched "needs Kevin" queue: its next move is an owner
# decision (acceptance of a deployed result)
def needs_kevin(s: Item) -> Bool:
  match s:
    case Deployed{au, hd, ig, dp}:
      True{}
    case _:
      False{}

def astep.go(hold: Bool, s: Item, e: Ev) -> Item:
  match hold:
    case True{}:
      s
    case False{}:
      step(s, e)

# one step under the owner's availability: an owner action while he is off
# is held (the item stays queued), everything else steps as usual
def astep(av: Avail, s: Item, +e: Ev) -> Item:
  astep.go(Bool.and(is_off(av), owner_event(e)), s, e)

# A board is every live work item. An event addresses one item by index;
# the others are untouched.
def board_step(xs: List<&2, Item>, i: Nat, av: Avail, +e: Ev) -> List<&2, Item>:
  match xs i:
    case Nil{} j:
      Nil{}
    case x <> t 0n:
      astep(av, x, e) <> t
    case x <> t 1n+k:
      x <> board_step(t, k, av, e)

# the i-th item, Abandoned past the end (Abandoned absorbs every event)
def nth(xs: List<&2, Item>, i: Nat) -> Item:
  match xs i:
    case Nil{} j:
      Abandoned{}
    case x <> t 0n:
      x
    case x <> t 1n+k:
      nth(t, k)
