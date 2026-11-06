# All proofs implement the exact, owner-reviewed LAWS.bend signatures.
# Do not weaken LAWS to make --verdict pass.
import Base
import ./MODEL.bend as M
import ./LAWS.bend as Laws

def Laws.unmatched_host_refuses(m, p, l, mt, f):
  {==}

def Laws.ambiguous_host_refuses(m, p, l, mt, f):
  {==}

def Laws.undeclared_manifest_refuses(p, l, mt, f):
  {==}

def Laws.never_through_checkout(l, mt, f):
  {==}

def Laws.operator_edit_refuses(mt, f):
  {==}

def Laws.unmounted_fresh_tree_refuses(k):
  {==}

def Laws.existing_tree_survives_unmount(k):
  {==}

def Laws.single_disk_host_links(k, f):
  {==}

def Laws.mounted_bulk_links(k, f):
  {==}

def Laws.unknown_dominates(d):
  {==}

def Laws.drift_never_clean():
  {==}

def Laws.clean_only_without_findings():
  {==}
