import Base

# Independently authored .files finite control; no upstream Hapsland source.
# External booleans are assertions supplied by an observer, not OS verification.
# Wire outcome: state[0..5], accepted[6], reason[7..12], action[13..17],
# established-event[18..23]. A zero event slot means no established event;
# otherwise it contains event ID + 1. Denials retain state and request no action.

def has(+facts: U32, +mask: U32) -> Bool:
  U32.is_eq((facts .&. mask : U32), mask)

def denied(+state: U32, reason: U32) -> U32:
  (state + reason * 128 : U32)

def allowed(state: U32, reason: U32, action: U32, established: U32) -> U32:
  (state + 64 + reason * 128 + action * 8192 + established * 262144 : U32)

def guard(phase: Bool, facts: Bool, +state: U32, reason: U32, next: U32, action: U32, established: U32) -> U32:
  match phase:
    case False{}:
      denied(state, 1)
    case True{}:
      match facts:
        case False{}:
          denied(state, reason)
        case True{}:
          allowed(next, 0, action, established)

def onboarding_rest(+state: U32) -> Bool:
  U32.is_eq(state, 0) || U32.is_eq(state, 2) || U32.is_eq(state, 3) || U32.is_eq(state, 5) || U32.is_eq(state, 6)

def server_state(+state: U32) -> Bool:
  U32.is_eq(state, 12) || U32.is_eq(state, 13) || U32.is_eq(state, 14) || U32.is_eq(state, 15) || U32.is_eq(state, 16) || U32.is_eq(state, 17) || U32.is_eq(state, 18) || U32.is_eq(state, 19) || U32.is_eq(state, 23)

def status_result(phase: Bool, observed: Bool, complete: Bool, +state: U32) -> U32:
  match phase:
    case False{}:
      denied(state, 1)
    case True{}:
      match observed:
        case False{}:
          denied(state, 2)
        case True{}:
          match complete:
            case False{}:
              allowed(2, 0, 2, 2)
            case True{}:
              allowed(5, 0, 0, 2)

def module_result(phase: Bool, observed: Bool, succeeded: Bool, +state: U32) -> U32:
  match phase:
    case False{}:
      denied(state, 1)
    case True{}:
      match observed:
        case False{}:
          denied(state, 2)
        case True{}:
          match succeeded:
            case False{}:
              allowed(3, 15, 0, 7)
            case True{}:
              allowed(3, 0, 0, 7)

# Preflight facts summarize actual script checks; the producer cannot invent them.
# The ordered reasons distinguish host/auth/storage/network/firewall/ownership.
def preflight_gates(host: Bool, admin: Bool, storage: Bool, network: Bool, firewall: Bool, ownership: Bool, passed: Bool) -> U32:
  match host:
    case False{}:
      5
    case True{}:
      match admin:
        case False{}:
          6
        case True{}:
          match storage:
            case False{}:
              7
            case True{}:
              match network:
                case False{}:
                  8
                case True{}:
                  match firewall:
                    case False{}:
                      9
                    case True{}:
                      match ownership:
                        case False{}:
                          10
                        case True{}:
                          match passed:
                            case False{}:
                              11
                            case True{}:
                              0

def preflight_decision(passed: Bool, managed: Bool, ready: Bool, reason: U32) -> U32:
  match passed:
    case True{}:
      match managed:
        case False{}:
          allowed(12, 0, 0, 11)
        case True{}:
          match ready:
            case False{}:
              allowed(20, 12, 0, 11)
            case True{}:
              allowed(14, 0, 0, 11)
    case False{}:
      allowed(20, reason, 0, 11)

def preflight_reason(+reason: U32, managed: Bool, ready: Bool) -> U32:
  preflight_decision(U32.is_zero(reason), managed, ready, reason)

def preflight_result(phase: Bool, observed: Bool, +state: U32, +facts: U32) -> U32:
  match phase:
    case False{}:
      denied(state, 1)
    case True{}:
      match observed:
        case False{}:
          denied(state, 2)
        case True{}:
          preflight_reason(preflight_gates(has(facts, 32), has(facts, 64), has(facts, 128), has(facts, 256), has(facts, 512), has(facts, 1024), has(facts, 2048)), has(facts, 4096), has(facts, 24576))

def startup_result(phase: Bool, observed: Bool, ready: Bool, +state: U32) -> U32:
  match phase:
    case False{}:
      denied(state, 1)
    case True{}:
      match observed:
        case False{}:
          denied(state, 2)
        case True{}:
          match ready:
            case False{}:
              allowed(20, 12, 0, 13)
            case True{}:
              allowed(14, 0, 0, 13)

def apply_request(already_ready: Bool, +state: U32, +facts: U32) -> U32:
  match already_ready:
    case True{}:
      guard(True{}, has(facts, 4084) && has(facts, 4096) && has(facts, 24576), state, 17, 14, 0, 0)
    case False{}:
      guard(U32.is_eq(state, 12), has(facts, 4084) && Bool.not(has(facts, 4096)), state, 17, 13, 6, 0)

def initial() -> U32:
  0

def route(event: Nat, +state: U32, +facts: U32) -> U32:
  match event:
    case 0n:
      guard(onboarding_rest(state), True{}, state, 0, 1, 1, 0)
    case 1n:
      status_result(U32.is_eq(state, 1), has(facts, 1), has(facts, 2), state)
    case 2n:
      guard(U32.is_eq(state, 2), has(facts, 4), state, 3, 3, 0, 3)
    case 3n:
      guard(U32.is_eq(state, 2), True{}, state, 0, 6, 0, 4)
    case 4n:
      guard(U32.is_eq(state, 3) || U32.is_eq(state, 5), has(facts, 4), state, 3, 4, 3, 0)
    case 5n:
      guard(U32.is_eq(state, 3) || U32.is_eq(state, 5), has(facts, 4), state, 3, 4, 4, 0)
    case 6n:
      module_result(U32.is_eq(state, 4), has(facts, 1), has(facts, 8), state)
    case 7n:
      guard(U32.is_eq(state, 3), has(facts, 3), state, 16, 5, 0, 8)
    case 8n:
      guard(onboarding_rest(state) || U32.is_eq(state, 22), has(facts, 20), state, 4, 10, 0, 9)
    case 9n:
      guard(U32.is_eq(state, 10) || U32.is_eq(state, 20), has(facts, 96), state, 6, 11, 5, 0)
    case 10n:
      preflight_result(U32.is_eq(state, 11), has(facts, 1), state, facts)
    case 11n:
      apply_request(U32.is_eq(state, 14), state, facts)
    case 12n:
      startup_result(U32.is_eq(state, 13) || U32.is_eq(state, 23), has(facts, 1), has(facts, 134246400), state)
    case 13n:
      guard(U32.is_eq(state, 14), has(facts, 65604), state, 18, 15, 7, 0)
    case 14n:
      guard(U32.is_eq(state, 15), has(facts, 32769), state, 2, 16, 0, 15)
    case 15n:
      guard(U32.is_eq(state, 16), has(facts, 196676), state, 19, 17, 8, 0)
    case 16n:
      guard(U32.is_eq(state, 17), has(facts, 3932161), state, 13, 18, 0, 17)
    case 17n:
      guard(U32.is_eq(state, 18), has(facts, 4194305), state, 14, 19, 0, 18)
    case 18n:
      guard(server_state(state), has(facts, 1), state, 2, 20, 0, 19)
    case 19n:
      guard(U32.is_eq(state, 20), has(facts, 68), state, 20, 20, 9, 0)
    case 20n:
      guard(U32.is_eq(state, 20), has(facts, 301995108) && Bool.not(has(facts, 8192)), state, 21, 23, 10, 0)
    case 21n:
      guard(server_state(state) || U32.is_eq(state, 20), has(facts, 25165892), state, 22, 21, 11, 0)
    case 22n:
      guard(U32.is_eq(state, 21), has(facts, 67108865), state, 2, 22, 0, 23)
    case _:
      denied(state, 23)

def step(state: U32, event: U32, facts: U32) -> U32:
  route(U32.to_nat(event), state, facts)

# Retains exported functions in the compiler's emitted JavaScript reachability.
# Producer replaces only the CLI footer, never these decisions.
def main() -> U32:
  step(initial(), 0, 0)
