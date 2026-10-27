# Host layout admission: may an installer link one manifest-owned live path?
# The operational decision is scripts/host_admission.py:decide, called by
# apply-agent-oom and install-host-drift. Observation of the inputs (hostname,
# filesystem, mount table) is not proven; see README.md for the boundary.
import Base

type Hosts is Data:
  HNone{}
  HOne{}
  HMany{}

type Parent is Data:
  PReal{}
  PThroughCheckout{}

type Accepted is Data:
  AAbsent{}
  ASameBytes{}
  AInventoried{}
  AVerifiedStamp{}

type Live is Data:
  LChanged{}
  LAccepted{kind: Accepted}

type Mount is Data:
  MNotDeclared{}
  MMounted{}
  MUnmounted{}

type Reason is Data:
  RNoHost{}
  RAmbiguousHost{}
  RNoManifest{}
  RThroughCheckout{}
  RChanged{}
  RUnmounted{}

type Verdict is Data:
  HRefuse{reason: Reason}
  HLink{}

def check_mount(mount: Mount, fresh: Bool) -> Verdict:
  match mount:
    case MNotDeclared{}:
      HLink{}
    case MMounted{}:
      HLink{}
    case MUnmounted{}:
      match fresh:
        case True{}:
          HRefuse{RUnmounted{}}
        case False{}:
          HLink{}

def check_live(live: Live, mount: Mount, fresh: Bool) -> Verdict:
  match live:
    case LChanged{}:
      HRefuse{RChanged{}}
    case LAccepted{kind}:
      check_mount(mount, fresh)

def check_parent(parent: Parent, live: Live, mount: Mount, fresh: Bool) -> Verdict:
  match parent:
    case PReal{}:
      check_live(live, mount, fresh)
    case PThroughCheckout{}:
      HRefuse{RThroughCheckout{}}

def check_manifest(manifest: Bool, parent: Parent, live: Live, mount: Mount, fresh: Bool) -> Verdict:
  match manifest:
    case True{}:
      check_parent(parent, live, mount, fresh)
    case False{}:
      HRefuse{RNoManifest{}}

def decide(hosts: Hosts, manifest: Bool, parent: Parent, live: Live, mount: Mount, fresh: Bool) -> Verdict:
  match hosts:
    case HNone{}:
      HRefuse{RNoHost{}}
    case HMany{}:
      HRefuse{RAmbiguousHost{}}
    case HOne{}:
      check_manifest(manifest, parent, live, mount, fresh)

# Drift report status. Unknown observation dominates; drift is never relabelled clean.
type Status is Data:
  SClean{}
  SDrift{}
  SUnknown{}

def status(unknown: Bool, drift: Bool) -> Status:
  match unknown:
    case True{}:
      SUnknown{}
    case False{}:
      match drift:
        case True{}:
          SDrift{}
        case False{}:
          SClean{}

# Exhaustive Python/Bend parity uses these lossless codes.
def code(v: Verdict) -> Nat:
  match v:
    case HRefuse{reason}:
      match reason:
        case RNoHost{}:
          0n
        case RAmbiguousHost{}:
          1n
        case RNoManifest{}:
          2n
        case RThroughCheckout{}:
          3n
        case RChanged{}:
          4n
        case RUnmounted{}:
          5n
    case HLink{}:
      6n

def status_code(s: Status) -> Nat:
  match s:
    case SClean{}:
      0n
    case SDrift{}:
      1n
    case SUnknown{}:
      2n
