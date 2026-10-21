# Loop 3. Abstract evidence guards are supplied by the read-only collector.
# No fairness/liveness assumption: I1 is a deadline monitor, not a promise
# that an external agent integrates work. Leases are per repository.
import Base

type St is Data:
  Branch{}
  DraftPR{}
  Queued{}
  OnIntegrationBranch{}
  Deployed{}
  OwnerAccepted{}
  Merged{}
  Parked{}
  Conflicted{}

type Ev is Data:
  Draft{}
  Queue{}
  Integrate{lease: Bool, stack: Bool, independent: Bool}
  Deploy{equal: Bool}
  Accept{owner: Bool}
  Merge{}
  Park{reason: Bool, future: Bool}
  Conflict{}
  Resume{}
  Observe{equal: Bool}
  Expire{expired: Bool}

def pick(ok: Bool, x: St, y: St) -> St:
  match ok:
    case True{}:
      x
    case False{}:
      y

def advance(+s: St, e: Ev) -> St:
  match s e:
    case Branch{} Draft{}:
      DraftPR{}
    case DraftPR{} Queue{}:
      Queued{}
    case Queued{} Integrate{lease, stack, independent}:
      pick(Bool.and(lease, Bool.and(stack, independent)), OnIntegrationBranch{}, s)
    case OnIntegrationBranch{} Deploy{equal}:
      pick(equal, Deployed{}, s)
    case Deployed{} Accept{owner}:
      pick(owner, OwnerAccepted{}, s)
    case OwnerAccepted{} Merge{}:
      Merged{}
    case Parked{} Resume{}:
      Queued{}
    case Parked{} Expire{expired}:
      pick(expired, Queued{}, s)
    case Conflicted{} Resume{}:
      Queued{}
    case _ _:
      s

def observe(+s: St, equal: Bool) -> St:
  match s:
    case Deployed{}:
      pick(equal, Deployed{}, OnIntegrationBranch{})
    case OwnerAccepted{}:
      pick(equal, OwnerAccepted{}, OnIntegrationBranch{})
    case _:
      s

def active(+s: St, e: Ev) -> St:
  match e:
    case Park{reason, future}:
      pick(Bool.and(reason, future), Parked{}, s)
    case Conflict{}:
      Conflicted{}
    case Observe{equal}:
      observe(s, equal)
    case _:
      advance(s, e)

def step(s: St, e: Ev) -> St:
  match s:
    case Merged{}:
      Merged{}
    case _:
      active(s, e)

# I1 deadline violation: all open drafts not contained/validly parked at 24 h.
def overdue(age: Nat, contained: Bool, parked: Bool) -> Bool:
  Bool.and(Bool.not(Bool.or(contained, parked)), Nat.is_ge(age, 86400n))

# I3 a single live holder; unexpired leases cannot be stolen.
type Lease is Data:
  Free{}
  Held{owner: Nat, until: Nat}

def lpick(ok: Bool, x: Lease, y: Lease) -> Lease:
  match ok:
    case True{}:
      x
    case False{}:
      y

def acquire(l: Lease, +actor: Nat, +until: Nat, +now: Nat) -> Lease:
  match l:
    case Free{}:
      lpick(Nat.is_gt(until, now), Held{actor, until}, Free{})
    case Held{owner, +expiry}:
      lpick(Bool.and(Nat.is_ge(now, expiry), Nat.is_gt(until, now)), Held{actor, until}, Held{owner, expiry})
