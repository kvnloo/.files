# Fleet host admission: abstract inputs from scripts/fleet, not a scheduler.
# The operational decision is scripts/fleet_admission.py:decide. External
# registry classification, probe fidelity and SSH/tar outcomes are not proven.
import Base

type Target is Data:
  FMissing{}
  FGroot{}
  FRemote{}

type Transfer is Data:
  TPending{}
  TComplete{}
  TNotRequired{}
  TFailed{}

type Reason is Data:
  RNoRemote{}
  RGrootForbidden{}
  RUnqualified{}
  RUnavailable{}
  RNoRoom{}
  RSourceFailed{}

type Verdict is Data:
  FRefuse{reason: Reason}
  FPrepare{}
  FAdmit{}

def after_transfer(t: Transfer) -> Verdict:
  match t:
    case TPending{}:
      FPrepare{}
    case TComplete{}:
      FAdmit{}
    case TNotRequired{}:
      FAdmit{}
    case TFailed{}:
      FRefuse{RSourceFailed{}}

def check_room(room: Bool, t: Transfer) -> Verdict:
  match room:
    case True{}:
      after_transfer(t)
    case False{}:
      FRefuse{RNoRoom{}}

def check_available(available: Bool, room: Bool, t: Transfer) -> Verdict:
  match available:
    case True{}:
      check_room(room, t)
    case False{}:
      FRefuse{RUnavailable{}}

def check_qualified(qualified: Bool, available: Bool, room: Bool, t: Transfer) -> Verdict:
  match qualified:
    case True{}:
      check_available(available, room, t)
    case False{}:
      FRefuse{RUnqualified{}}

def decide(target: Target, qualified: Bool, available: Bool, room: Bool, transfer: Transfer) -> Verdict:
  match target:
    case FMissing{}:
      FRefuse{RNoRemote{}}
    case FGroot{}:
      FRefuse{RGrootForbidden{}}
    case FRemote{}:
      check_qualified(qualified, available, room, transfer)

# Exhaustive Python/Bend parity uses this lossless code for the 8 verdicts.
def code(v: Verdict) -> Nat:
  match v:
    case FRefuse{reason}:
      match reason:
        case RNoRemote{}:
          0n
        case RGrootForbidden{}:
          1n
        case RUnqualified{}:
          2n
        case RUnavailable{}:
          3n
        case RNoRoom{}:
          4n
        case RSourceFailed{}:
          5n
    case FPrepare{}:
      6n
    case FAdmit{}:
      7n
