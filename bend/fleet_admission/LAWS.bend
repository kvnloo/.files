# Owner law: universally quantified over the actual MODEL.decide domain.
# No theorem here verifies the caller's inputs, transport, permission or host.
import Base
import ./MODEL.bend as M

law missing_remote_refuses:
  for q: Bool
  for a: Bool
  for room: Bool
  for t: M.Transfer
  {M.decide(M.FMissing{}, q, a, room, t) == M.FRefuse{M.RNoRemote{}} : M.Verdict}

law never_groot_fallback:
  for q: Bool
  for a: Bool
  for room: Bool
  for t: M.Transfer
  {M.decide(M.FGroot{}, q, a, room, t) == M.FRefuse{M.RGrootForbidden{}} : M.Verdict}

law unqualified_refuses:
  for a: Bool
  for room: Bool
  for t: M.Transfer
  {M.decide(M.FRemote{}, False{}, a, room, t) == M.FRefuse{M.RUnqualified{}} : M.Verdict}

law unavailable_refuses:
  for room: Bool
  for t: M.Transfer
  {M.decide(M.FRemote{}, True{}, False{}, room, t) == M.FRefuse{M.RUnavailable{}} : M.Verdict}

law no_room_refuses:
  for t: M.Transfer
  {M.decide(M.FRemote{}, True{}, True{}, False{}, t) == M.FRefuse{M.RNoRoom{}} : M.Verdict}

law source_transfer_fails_closed:
  {M.decide(M.FRemote{}, True{}, True{}, True{}, M.TFailed{}) == M.FRefuse{M.RSourceFailed{}} : M.Verdict}

law source_pending_cannot_execute:
  {M.decide(M.FRemote{}, True{}, True{}, True{}, M.TPending{}) == M.FPrepare{} : M.Verdict}

law delivered_remote_admits:
  {M.decide(M.FRemote{}, True{}, True{}, True{}, M.TComplete{}) == M.FAdmit{} : M.Verdict}

law no_source_remote_admits:
  {M.decide(M.FRemote{}, True{}, True{}, True{}, M.TNotRequired{}) == M.FAdmit{} : M.Verdict}
