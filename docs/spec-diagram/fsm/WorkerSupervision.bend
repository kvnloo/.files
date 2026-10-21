# Worker supervision: the transition functions (the statechart, as code).
#
# Loop 2 of the statechart-then-verify layer. One delegated worker moves
#   Dispatched -> Running (heartbeats) -> {Completed | Interrupted | Stalled}
#   -> Resumed | Abandoned | Integrated
# with Overdue for an interrupted worker left past the limit (it is then in
# the batched needs-Kevin queue). docs/fsm/worker-supervision.mmd draws it;
# src/z0int/fsm/worker_supervision.py is the same table in Python (the
# replay checker and `supervise`), kept equal by tests/test_fsm_worker_supervision.py.
#
# Beside the worker machine there are two small shared resources:
#   Lease  one owner per worktree or branch at a time; the same mutex is the
#          phone install lock (installs to the owner's phone are serialized)
#   Phone  the owner's S25: input is typed only into the app last observed in
#          the foreground, and every input needs a fresh look
#
# A step that the guards refuse leaves the state unchanged; the replay
# checker reports every refused event as a violation.
#
# Times (heartbeats, interruptions, the clock) are abstract Nat seconds; the
# limit `lim` is a parameter of `step`, so every law holds for every limit.

import Base

# where a worker runs: groot (the memory-starved desktop), the MBP, a phone
type Host is Data:
  Groot{}
  Mbp{}
  Phone{}

type Load is Data:
  Light{}
  Heavy{}

# a declared reason to run heavy work on groot anyway
type Exc is Data:
  NoExc{}
  Gpu{}
  Toolchain{}

# a worker: its id, the worktree/branch it leases, its load and exception
type W is Data:
  W{id: Nat, wt: Nat, load: Load, exc: Exc}

# bg: background processes the worker has left running
type St is Data:
  Dispatched{w: W}
  Running{w: W, h: Host, hb: Nat, bg: Nat}
  Stalled{w: W, h: Host, hb: Nat, bg: Nat}
  Interrupted{w: W, at: Nat, bg: Nat}
  Overdue{w: W, at: Nat, bg: Nat}
  Completed{w: W, bg: Nat}
  Resumed{w: W, by: Nat, bg: Nat}
  Abandoned{w: W}
  Integrated{w: W}

type Ev is Data:
  Start{h: Host, t: Nat}
  Beat{t: Nat}
  Spawn{}
  Reap{}
  Tick{now: Nat}
  Finish{}
  Interrupt{t: Nat}
  Resume{by: Nat, log: Bool}
  Abandon{}
  Integrate{}

def pick(ok: Bool, x: St, y: St) -> St:
  match ok:
    case True{}:
      x
    case False{}:
      y

def heavy(l: Load) -> Bool:
  match l:
    case Heavy{}:
      True{}
    case Light{}:
      False{}

def declared(x: Exc) -> Bool:
  match x:
    case NoExc{}:
      False{}
    case _:
      True{}

def on_groot(h: Host) -> Bool:
  match h:
    case Groot{}:
      True{}
    case _:
      False{}

def wload(w: W) -> Load:
  match w:
    case W{id, wt, load, exc}:
      load

def wexc(w: W) -> Exc:
  match w:
    case W{id, wt, load, exc}:
      exc

# Placement: heavy work runs on a fleet node (the MBP or a phone), never on
# groot, unless the worker declared a GPU or toolchain exception.
def placed(+w: W, h: Host) -> Bool:
  Bool.or(Bool.not(on_groot(h)), Bool.or(Bool.not(heavy(wload(w))), declared(wexc(w))))

def dec(n: Nat) -> Nat:
  match n:
    case 0n:
      0n
    case 1n+k:
      k

def is_zero(n: Nat) -> Bool:
  match n:
    case 0n:
      True{}
    case 1n+k:
      False{}

# the clock has passed `base + lim`
def late(now: Nat, base: Nat, lim: Nat) -> Bool:
  Nat.is_gt(now, Nat.add(base, lim))

# Per-state transition tables
# ---------------------------

def from_dispatched(+w: W, e: Ev) -> St:
  match e:
    case Start{+h, t}:
      pick(placed(w, h), Running{w, h, t, 0n}, Dispatched{w})
    case Interrupt{t}:
      Interrupted{w, t, 0n}
    case Abandon{}:
      Abandoned{w}
    case _:
      Dispatched{w}

def from_running(+w: W, +h: Host, +hb: Nat, +bg: Nat, e: Ev, lim: Nat) -> St:
  match e:
    case Beat{t}:
      Running{w, h, t, bg}
    case Spawn{}:
      Running{w, h, hb, 1n+bg}
    case Reap{}:
      Running{w, h, hb, dec(bg)}
    case Tick{now}:
      pick(late(now, hb, lim), Stalled{w, h, hb, bg}, Running{w, h, hb, bg})
    case Finish{}:
      Completed{w, bg}
    case Interrupt{t}:
      Interrupted{w, t, bg}
    case _:
      Running{w, h, hb, bg}

# a stalled worker that stays silent for a second limit is declared interrupted
def from_stalled(+w: W, +h: Host, +hb: Nat, +bg: Nat, e: Ev, +lim: Nat) -> St:
  match e:
    case Beat{t}:
      Running{w, h, t, bg}
    case Reap{}:
      Stalled{w, h, hb, dec(bg)}
    case Tick{+now}:
      pick(late(now, hb, Nat.add(lim, lim)), Interrupted{w, now, bg}, Stalled{w, h, hb, bg})
    case Finish{}:
      Completed{w, bg}
    case Interrupt{t}:
      Interrupted{w, t, bg}
    case _:
      Stalled{w, h, hb, bg}

# Interrupted leaves only by Resume (a successor picks the work up from the
# worker's log and adopts its background processes) or by an explicit
# Abandon once every background process is reaped. Past the limit it turns
# Overdue: a needs-Kevin item, never a silent drop.
def from_interrupted(+w: W, +at: Nat, +bg: Nat, e: Ev, lim: Nat) -> St:
  match e:
    case Reap{}:
      Interrupted{w, at, dec(bg)}
    case Tick{now}:
      pick(late(now, at, lim), Overdue{w, at, bg}, Interrupted{w, at, bg})
    case Resume{by, log}:
      pick(log, Resumed{w, by, bg}, Interrupted{w, at, bg})
    case Abandon{}:
      pick(is_zero(bg), Abandoned{w}, Interrupted{w, at, bg})
    case _:
      Interrupted{w, at, bg}

def from_overdue(+w: W, +at: Nat, +bg: Nat, e: Ev) -> St:
  match e:
    case Reap{}:
      Overdue{w, at, dec(bg)}
    case Resume{by, log}:
      pick(log, Resumed{w, by, bg}, Overdue{w, at, bg})
    case Abandon{}:
      pick(is_zero(bg), Abandoned{w}, Overdue{w, at, bg})
    case _:
      Overdue{w, at, bg}

def from_completed(+w: W, +bg: Nat, e: Ev) -> St:
  match e:
    case Reap{}:
      Completed{w, dec(bg)}
    case Integrate{}:
      pick(is_zero(bg), Integrated{w}, Completed{w, bg})
    case Abandon{}:
      pick(is_zero(bg), Abandoned{w}, Completed{w, bg})
    case _:
      Completed{w, bg}

def step(s: St, e: Ev, lim: Nat) -> St:
  match s:
    case Dispatched{w}:
      from_dispatched(w, e)
    case Running{w, h, hb, bg}:
      from_running(w, h, hb, bg, e, lim)
    case Stalled{w, h, hb, bg}:
      from_stalled(w, h, hb, bg, e, lim)
    case Interrupted{w, at, bg}:
      from_interrupted(w, at, bg, e, lim)
    case Overdue{w, at, bg}:
      from_overdue(w, at, bg, e)
    case Completed{w, bg}:
      from_completed(w, bg, e)
    case Resumed{w, by, bg}:
      Resumed{w, by, bg}
    case Abandoned{w}:
      Abandoned{w}
    case Integrated{w}:
      Integrated{w}

# replay a tape of events from s (the tape shrinks, so this terminates)
def run(es: List<&2, Ev>, +lim: Nat, s: St) -> St:
  match es:
    case Nil{}:
      s
    case e <> t:
      run(t, lim, step(s, e, lim))

# the worker is in the batched needs-Kevin queue
def needs_kevin(s: St) -> Bool:
  match s:
    case Overdue{w, at, bg}:
      True{}
    case _:
      False{}

# Lease: one owner per worktree or branch at a time
# ------------------------------------------------
# Also the phone install lock. A lease changes hands only through Free, or
# by Reclaim with evidence that the holder is dead (an Interrupted or
# Overdue worker whose successor resumes it).

type Lease is Data:
  Free{}
  Held{o: Nat}

type LEv is Data:
  Acquire{a: Nat}
  Release{a: Nat}
  Reclaim{a: Nat, dead: Bool}

def lpick(ok: Bool, x: Lease, y: Lease) -> Lease:
  match ok:
    case True{}:
      x
    case False{}:
      y

def lfree(e: LEv) -> Lease:
  match e:
    case Acquire{a}:
      Held{a}
    case _:
      Free{}

def lheld(+o: Nat, e: LEv) -> Lease:
  match e:
    case Acquire{a}:
      Held{o}
    case Release{a}:
      lpick(Nat.is_eq(a, o), Free{}, Held{o})
    case Reclaim{a, dead}:
      lpick(dead, Held{a}, Held{o})

def lstep(l: Lease, e: LEv) -> Lease:
  match l:
    case Free{}:
      lfree(e)
    case Held{o}:
      lheld(o, e)

# a worker may write to the leased worktree (commit, push, install) only as
# the holder
def holds(l: Lease, a: Nat) -> Bool:
  match l:
    case Free{}:
      False{}
    case Held{o}:
      Nat.is_eq(o, a)

# Device: the owner's S25
# -----------------------
# lk is the install lock; fg is the app last observed in the foreground,
# Unknown after any input (the input may have changed the screen).

type Fg is Data:
  Unknown{}
  Seen{app: Nat}

type Device is Data:
  Dev{lk: Lease, fg: Fg}

type PEv is Data:
  Lock{a: Nat}
  Unlock{a: Nat}
  Peek{app: Nat}
  Install{a: Nat}
  Input{a: Nat, app: Nat}

# what the step does to the device
type Eff is Data:
  NoEff{}
  Installed{a: Nat}
  Typed{a: Nat, app: Nat}

def epick(ok: Bool, x: Eff, y: Eff) -> Eff:
  match ok:
    case True{}:
      x
    case False{}:
      y

def fg_is(f: Fg, app: Nat) -> Bool:
  match f:
    case Unknown{}:
      False{}
    case Seen{x}:
      Nat.is_eq(x, app)

def dev_eff(lk: Lease, fg: Fg, e: PEv) -> Eff:
  match e:
    case Install{+a}:
      epick(holds(lk, a), Installed{a}, NoEff{})
    case Input{+a, +app}:
      epick(fg_is(fg, app), Typed{a, app}, NoEff{})
    case _:
      NoEff{}

def peff(p: Device, e: PEv) -> Eff:
  match p:
    case Dev{lk, fg}:
      dev_eff(lk, fg, e)

def dev_step(lk: Lease, fg: Fg, e: PEv) -> Device:
  match e:
    case Lock{a}:
      Dev{lstep(lk, Acquire{a}), fg}
    case Unlock{a}:
      Dev{lstep(lk, Release{a}), fg}
    case Peek{app}:
      Dev{lk, Seen{app}}
    case Install{a}:
      Dev{lk, fg}
    case Input{a, app}:
      Dev{lk, Unknown{}}

def pstep(p: Device, e: PEv) -> Device:
  match p:
    case Dev{lk, fg}:
      dev_step(lk, fg, e)
