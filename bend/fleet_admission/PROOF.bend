# All proofs implement the exact, owner-reviewed LAWS.bend signatures.
# Do not weaken LAWS to make --verdict pass.
import Base
import ./MODEL.bend as M
import ./LAWS.bend as Laws

def Laws.missing_remote_refuses(q, a, room, t):
  {==}

def Laws.never_groot_fallback(q, a, room, t):
  {==}

def Laws.unqualified_refuses(a, room, t):
  {==}

def Laws.unavailable_refuses(room, t):
  {==}

def Laws.no_room_refuses(t):
  {==}

def Laws.source_transfer_fails_closed():
  {==}

def Laws.source_pending_cannot_execute():
  {==}

def Laws.delivered_remote_admits():
  {==}

def Laws.no_source_remote_admits():
  {==}
