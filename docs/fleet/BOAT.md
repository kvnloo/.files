# Boat

Use the official `boat` CLI directly (`~/.local/bin/boat`). There is no wrapper.
The old `scripts/boat` / `omp-boat` / `fleet-boat` / `boat-reaper` were deleted on
purpose (owner ruling 2026-11-10). Do not recreate them.

- Run: `fleet run --node boat [--no-src] -- CMD` (uses `boat run`: create, run, delete).
- Direct: `boat run --type small --push DIR --timeout 450 -- CMD`
- Budget: plan-included VM time from `boat --json limits` (`creditBalanceSeconds`).
  Wallet stays $0 and keepGoing stays off, so nothing past the plan can bill.
- Cleanup: `boat list`, `boat delete ID`. `boat run` deletes its own sandbox.
- Next: Boat as a k3s autoscaling pool (Kueue quota = remaining minutes).
