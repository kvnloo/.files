# Presentation machine for the ops plane's decision gates (O1-O5, O7). Every verdict is
# computed by the unchanged Ops.bend (kvnloo/z0intelligence bend/ops_fsm/ops.bend); this
# file only names the last verdict as a state so Hapsland can draw and step it.
# O6 takes lists (the accessibility sets) and O8/O9 are machines of their own in Ops.bend.
import Base
import ./Ops.bend as O

type GSt is Data:
  GIdle{}
  GAdmitted{}
  GWaiting{}
  GRefused{}
  GRolledBack{}

type GEv is Data:
  GPlace{c: O.Cls, mbp: Bool, phone: Bool}
  GGit{served: Bool, op: O.GitOp, txn: Bool}
  GRoll{q: O.Req, check: Bool}
  GPush{private: Bool, vis: O.Vis}
  GPhone{a: O.PAct, call: Bool}
  GRoute{cancelled: Bool, sol: Bool, design: Bool}

def by_bool(ok: Bool) -> GSt:
  match ok:
    case True{}:
      GAdmitted{}
    case False{}:
      GRefused{}

def by_place(p: O.Place) -> GSt:
  match p:
    case O.RunOn{l}:
      GAdmitted{}
    case O.Wait{}:
      GWaiting{}

def by_out(o: O.Out) -> GSt:
  match o:
    case O.ORefused{}:
      GRefused{}
    case O.ODeferred{}:
      GWaiting{}
    case O.OPromoted{}:
      GAdmitted{}
    case O.ORolledBack{}:
      GRolledBack{}

# the state is the verdict on the last gated action; it does not constrain the next one
def gate_step(s: GSt, e: GEv) -> GSt:
  match e:
    case GPlace{c, mbp, phone}:
      by_place(O.place(c, mbp, phone))
    case GGit{served, op, txn}:
      by_bool(O.wt_allows(served, op, txn))
    case GRoll{q, check}:
      by_out(O.rollout(q, check))
    case GPush{private, vis}:
      by_bool(O.push_allows(private, vis))
    case GPhone{a, call}:
      by_bool(O.phone_allows(a, call))
    case GRoute{cancelled, sol, design}:
      by_bool(O.route_ok(cancelled, sol, design))
