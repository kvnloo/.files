# Ops plane: the owner's operating rules as decision functions (the gates, as code).
#
# Today (2026-10-21) several operating rules lived only in markdown or prompts
# and were broken anyway. This file writes each rule as a small pure decision
# function or state machine; LAWS.bend states what each must guarantee and
# PROOF.bend proves it. src/z0int/fsm/ops.py is the same table in Python (the
# gates that real tools call: fleet-build, z0-guard, git hooks, the z0live
# broker, the install wrapper, the fleet health checker, supervise), kept equal
# by src/z0int/fsm/ops_parity.py and tests/test_fsm_ops.py.
#
# Every input here is already decided by the caller (a job class, whether a
# path is private-marked, a remote's visibility, ...). How a real command,
# path, config line or adb dump maps to these inputs is the Python side's
# heuristic and is not proven.
#
# Constructor names are global in Bend, so every one here carries a prefix.

import Base

# ------------------------------------------------------------------ O1
# Compute placement. Heavy classes run on a non-groot worker lane (the MBP or
# a phone); groot admits only gpu | bend | lean | service | agent-process |
# tiny (< 10 s). With no room the job waits; it never falls back to groot.

type Cls is Data:
  CTest{}
  CMutation{}
  CTypecheck{}
  CGradle{}
  CBundle{}
  CEval{}
  CShot{}
  CGpu{}
  CBend{}
  CLean{}
  CService{}
  CAgent{}
  CTiny{}

type Lane is Data:
  LGroot{}
  LMbp{}
  LPhone{}

type Place is Data:
  RunOn{l: Lane}
  Wait{}

def groot_class(c: Cls) -> Bool:
  match c:
    case CGpu{}:
      True{}
    case CBend{}:
      True{}
    case CLean{}:
      True{}
    case CService{}:
      True{}
    case CAgent{}:
      True{}
    case CTiny{}:
      True{}
    case _:
      False{}

# may lane l run a job of class c?
def admits(l: Lane, c: Cls) -> Bool:
  match l:
    case LGroot{}:
      groot_class(c)
    case _:
      True{}

def place_phone(p: Bool) -> Place:
  match p:
    case True{}:
      RunOn{LPhone{}}
    case False{}:
      Wait{}

# off groot: the MBP when it has room, else a phone with room, else wait
def place_off(m: Bool, p: Bool) -> Place:
  match m:
    case True{}:
      RunOn{LMbp{}}
    case False{}:
      place_phone(p)

def place_by(g: Bool, m: Bool, p: Bool) -> Place:
  match g:
    case True{}:
      RunOn{LGroot{}}
    case False{}:
      place_off(m, p)

# where a job of class c goes, given room on the MBP (m) and on a phone (p)
def place(c: Cls, m: Bool, p: Bool) -> Place:
  place_by(groot_class(c), m, p)

def runs_on_groot(x: Place) -> Bool:
  match x:
    case RunOn{l}:
      match l:
        case LGroot{}:
          True{}
        case _:
          False{}
    case Wait{}:
      False{}

# ------------------------------------------------------------------ O2
# Served worktree. A worktree holding a live-service lease accepts no edit,
# commit, checkout, stash or merge, except `merge --ff-only` inside the guarded
# rollout transaction (txn: the caller holds the rollout lease token), and that
# same transaction's automatic rollback to the revision it replaced (O3b).

type GitOp is Data:
  GEdit{}
  GCommit{}
  GCheckout{}
  GStash{}
  GMerge{}
  GMergeFF{}
  GRollback{}

def served_allows(op: GitOp, txn: Bool) -> Bool:
  match op:
    case GMergeFF{}:
      txn
    case GRollback{}:
      txn
    case _:
      False{}

def wt_allows(served: Bool, op: GitOp, txn: Bool) -> Bool:
  match served:
    case True{}:
      served_allows(op, txn)
    case False{}:
      True{}

# ------------------------------------------------------------------ O3 (+O2, O5)
# Device rollout. One transaction: precheck, then merge --ff-only, idle-checked
# restart, device launch check, and automatic rollback when the check fails.
#   clean    the candidate was built from a non-served worktree       (O3a)
#   ff       the merge is a fast-forward                             (O2)
#   gated    the PR is marked review-gated
#   receipt  an orchestrator review receipt exists                   (O3c)
#   call     a z0live call is live: O5 refuses device work, so the
#            launch check cannot run; the rollout is deferred        (O3 x O5)
#   idle     the service is idle (no request in flight)              (O2)
# check: the device launch check on the real runtime passed           (O3b)

type Req is Data:
  Req{clean: Bool, ff: Bool, gated: Bool, receipt: Bool, call: Bool, idle: Bool}

type Out is Data:
  ORefused{}
  ODeferred{}
  OPromoted{}
  ORolledBack{}

def review_ok(gated: Bool, receipt: Bool) -> Bool:
  Bool.or(Bool.not(gated), receipt)

def pre_ok(clean: Bool, ff: Bool, gated: Bool, receipt: Bool) -> Bool:
  Bool.and(clean, Bool.and(ff, review_ok(gated, receipt)))

def ready(call: Bool, idle: Bool) -> Bool:
  Bool.and(Bool.not(call), idle)

def finish(check: Bool) -> Out:
  match check:
    case True{}:
      OPromoted{}
    case False{}:
      ORolledBack{}

def go(r: Bool, check: Bool) -> Out:
  match r:
    case True{}:
      finish(check)
    case False{}:
      ODeferred{}

def decide(ok: Bool, r: Bool, check: Bool) -> Out:
  match ok:
    case True{}:
      go(r, check)
    case False{}:
      ORefused{}

def rollout(q: Req, check: Bool) -> Out:
  match q:
    case Req{clean, ff, gated, receipt, call, idle}:
      decide(pre_ok(clean, ff, gated, receipt), ready(call, idle), check)

def promoted(x: Out) -> Bool:
  match x:
    case OPromoted{}:
      True{}
    case _:
      False{}

# the transaction ran: it merged and restarted the service
def touched(x: Out) -> Bool:
  match x:
    case OPromoted{}:
      True{}
    case ORolledBack{}:
      True{}
    case _:
      False{}

# ------------------------------------------------------------------ O4
# Privacy boundary. A private-marked artifact is pushed only to a remote known
# to be private; an unknown visibility fails closed.

type Vis is Data:
  VPublic{}
  VPrivate{}
  VUnknown{}

def vis_private(v: Vis) -> Bool:
  match v:
    case VPrivate{}:
      True{}
    case _:
      False{}

def push_allows(private: Bool, v: Vis) -> Bool:
  match private:
    case True{}:
      vis_private(v)
    case False{}:
      True{}

# ------------------------------------------------------------------ O5
# Owner phone touch. A UI input needs an explicit owner phone-operation intent
# and the expected app in the foreground. Installing or restarting an app in
# the active call chain is refused while a z0live call is live.

type PAct is Data:
  PTap{intent: Bool, fg: Bool}
  PInstall{chain: Bool}
  PRestart{chain: Bool}

def phone_allows(a: PAct, call: Bool) -> Bool:
  match a:
    case PTap{intent, fg}:
      Bool.and(intent, fg)
    case PInstall{chain}:
      Bool.not(Bool.and(chain, call))
    case PRestart{chain}:
      Bool.not(Bool.and(chain, call))

# ------------------------------------------------------------------ O6
# Accessibility preservation. After an install, every accessibility service
# enabled before it is still enabled, unless the owner removed it.

def mem(+x: Nat, l: List<&2, Nat>) -> Bool:
  match l:
    case Nil{}:
      False{}
    case h <> t:
      Bool.or(Nat.is_eq(h, x), mem(x, t))

def a11y_ok(pre: List<&2, Nat>, +post: List<&2, Nat>, +rm: List<&2, Nat>) -> Bool:
  match pre:
    case Nil{}:
      True{}
    case +h <> t:
      Bool.and(Bool.or(mem(h, post), mem(h, rm)), a11y_ok(t, post, rm))

# ------------------------------------------------------------------ O7
# Provider routing. No role routes to a cancelled provider; visual/UX design
# roles never route to Sol.

def route_ok(cancelled: Bool, sol: Bool, design: Bool) -> Bool:
  Bool.and(Bool.not(cancelled), Bool.not(Bool.and(design, sol)))

# ------------------------------------------------------------------ O8
# Node health. A worker node unhealthy for longer than `lim` emits exactly one
# owner notification per unhealthy episode; a strike past the limit with no
# notification is the violation.

type NSt is Data:
  NHealthy{}
  NBad{since: Nat}
  NNotified{since: Nat}

type NEv is Data:
  NProbe{ok: Bool, now: Nat}

def late(now: Nat, base: Nat, lim: Nat) -> Bool:
  Nat.is_gt(now, Nat.add(base, lim))

def npick(ok: Bool, x: NSt, y: NSt) -> NSt:
  match ok:
    case True{}:
      x
    case False{}:
      y

def from_healthy(e: NEv) -> NSt:
  match e:
    case NProbe{ok, now}:
      npick(ok, NHealthy{}, NBad{now})

def from_bad(+s: Nat, e: NEv, lim: Nat) -> NSt:
  match e:
    case NProbe{ok, +now}:
      npick(ok, NHealthy{}, npick(late(now, s, lim), NNotified{s}, NBad{s}))

def from_notified(+s: Nat, e: NEv) -> NSt:
  match e:
    case NProbe{ok, now}:
      npick(ok, NHealthy{}, NNotified{s})

def nstep(s: NSt, e: NEv, lim: Nat) -> NSt:
  match s:
    case NHealthy{}:
      from_healthy(e)
    case NBad{since}:
      from_bad(since, e, lim)
    case NNotified{since}:
      from_notified(since, e)

def bad_eff(s: Nat, e: NEv, lim: Nat) -> Bool:
  match e:
    case NProbe{ok, now}:
      Bool.and(Bool.not(ok), late(now, s, lim))

# does this probe emit the owner notification?
def neff(s: NSt, e: NEv, lim: Nat) -> Bool:
  match s:
    case NBad{since}:
      bad_eff(since, e, lim)
    case _:
      False{}

def notified(s: NSt) -> Bool:
  match s:
    case NNotified{since}:
      True{}
    case _:
      False{}

# ------------------------------------------------------------------ O9
# Gateway restart. When the gateway hosting headless runs restarts, every
# dependent active run becomes Interrupted, never silently Failed, and leaves
# Interrupted only by a resume from its session or an explicit report.

type RSt is Data:
  RActive{gw: Nat}
  RInterrupted{gw: Nat}
  RFailed{}
  RDone{}
  RResumed{}
  RReported{}

type REv is Data:
  GwRestart{gw: Nat}
  RunError{}
  RunDone{}
  ResumeRun{session: Bool}
  ReportRun{}

def rpick(ok: Bool, x: RSt, y: RSt) -> RSt:
  match ok:
    case True{}:
      x
    case False{}:
      y

def ract(+g: Nat, e: REv) -> RSt:
  match e:
    case GwRestart{x}:
      rpick(Nat.is_eq(x, g), RInterrupted{g}, RActive{g})
    case RunError{}:
      RFailed{}
    case RunDone{}:
      RDone{}
    case _:
      RActive{g}

def rint(+g: Nat, e: REv) -> RSt:
  match e:
    case ResumeRun{session}:
      rpick(session, RResumed{}, RInterrupted{g})
    case ReportRun{}:
      RReported{}
    case _:
      RInterrupted{g}

def rstep(s: RSt, e: REv) -> RSt:
  match s:
    case RActive{g}:
      ract(g, e)
    case RInterrupted{g}:
      rint(g, e)
    case RFailed{}:
      RFailed{}
    case RDone{}:
      RDone{}
    case RResumed{}:
      RResumed{}
    case RReported{}:
      RReported{}

def rfailed(s: RSt) -> Bool:
  match s:
    case RFailed{}:
      True{}
    case _:
      False{}
