# Owner laws, universally quantified over the actual MODEL.decide domain.
# Derived from 2026-10-25 mbp: live ~/.config/systemd/user was a directory link
# into the .files checkout, so a merge silently changed (and deleted) loaded units.
# No theorem here verifies the caller's observations, permission or host.
import Base
import ./MODEL.bend as M

law unmatched_host_refuses:
  for m: Bool
  for p: M.Parent
  for l: M.Live
  for mt: M.Mount
  for f: Bool
  {M.decide(M.HNone{}, m, p, l, mt, f) == M.HRefuse{M.RNoHost{}} : M.Verdict}

law ambiguous_host_refuses:
  for m: Bool
  for p: M.Parent
  for l: M.Live
  for mt: M.Mount
  for f: Bool
  {M.decide(M.HMany{}, m, p, l, mt, f) == M.HRefuse{M.RAmbiguousHost{}} : M.Verdict}

law undeclared_manifest_refuses:
  for p: M.Parent
  for l: M.Live
  for mt: M.Mount
  for f: Bool
  {M.decide(M.HOne{}, False{}, p, l, mt, f) == M.HRefuse{M.RNoManifest{}} : M.Verdict}

law never_through_checkout:
  for l: M.Live
  for mt: M.Mount
  for f: Bool
  {M.decide(M.HOne{}, True{}, M.PThroughCheckout{}, l, mt, f) == M.HRefuse{M.RThroughCheckout{}} : M.Verdict}

law operator_edit_refuses:
  for mt: M.Mount
  for f: Bool
  {M.decide(M.HOne{}, True{}, M.PReal{}, M.LChanged{}, mt, f) == M.HRefuse{M.RChanged{}} : M.Verdict}

law unmounted_fresh_tree_refuses:
  for k: M.Accepted
  {M.decide(M.HOne{}, True{}, M.PReal{}, M.LAccepted{k}, M.MUnmounted{}, True{}) == M.HRefuse{M.RUnmounted{}} : M.Verdict}

law existing_tree_survives_unmount:
  for k: M.Accepted
  {M.decide(M.HOne{}, True{}, M.PReal{}, M.LAccepted{k}, M.MUnmounted{}, False{}) == M.HLink{} : M.Verdict}

law single_disk_host_links:
  for k: M.Accepted
  for f: Bool
  {M.decide(M.HOne{}, True{}, M.PReal{}, M.LAccepted{k}, M.MNotDeclared{}, f) == M.HLink{} : M.Verdict}

law mounted_bulk_links:
  for k: M.Accepted
  for f: Bool
  {M.decide(M.HOne{}, True{}, M.PReal{}, M.LAccepted{k}, M.MMounted{}, f) == M.HLink{} : M.Verdict}

law unknown_dominates:
  for d: Bool
  {M.status(True{}, d) == M.SUnknown{} : M.Status}

law drift_never_clean:
  {M.status(False{}, True{}) == M.SDrift{} : M.Status}

law clean_only_without_findings:
  {M.status(False{}, False{}) == M.SClean{} : M.Status}
