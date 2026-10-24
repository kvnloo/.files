# Symlink-safe IaC rollout

Repository path migrations are staged from a separate worktree so the live
desktop can be tested before the canonical checkout changes.

## Manual procedure

Assume the active checkout is `/workspace/.files`.

```sh
cd /workspace/.files
git fetch origin

git worktree add /workspace/.files-rollout iac/fleet-future-state

cd /workspace/.files-rollout
python -m pytest tests/test_iac_collect.py tests/test_iac_links.py tests/test_iac_plan.py tests/test_future_layout.py -q
```

Generate a frozen symlink plan:

```sh
./iac links scan   --old-root /workspace/.files   --new-root /workspace/.files-rollout   --map transitions/path-map.toml   --output-dir /tmp/dotfiles-rollout
```

Review before changing anything:

```sh
jq . /tmp/dotfiles-rollout/plan.json
python /tmp/dotfiles-rollout/stage.py
```

Stage links into the candidate worktree:

```sh
python /tmp/dotfiles-rollout/stage.py --apply
./scripts/onboard doctor
./iac collect --stdout >/tmp/dotfiles-observed.json
./iac plan --observed /tmp/dotfiles-observed.json
```

If anything is wrong:

```sh
python /tmp/dotfiles-rollout/rollback.py --apply
```

After the PR is merged and the canonical checkout is updated in place:

```sh
cd /workspace/.files
git switch dev
git pull --ff-only
python /tmp/dotfiles-rollout/cutover.py --apply
./scripts/onboard doctor
./iac collect --stdout >/tmp/dotfiles-observed-after.json
./iac plan --observed /tmp/dotfiles-observed-after.json
```

Do not remove the candidate worktree or compatibility symlinks until the final
doctor/plan passes.

## Agent prompt for the local rollout

```text
We are testing the .files fleet-IaC migration from a NEW git worktree.

Do not edit or reset the active /workspace/.files checkout.
Do not delete any worktree.
Do not pull into the active checkout until the staged candidate passes.

1. Identify the active .files checkout and its current branch/HEAD/dirty state.
2. Fetch origin and create a new worktree for the future-state PR branch.
3. Run the IaC/unit tests in that worktree.
4. Run:
     ./iac links scan
   with:
     old-root = the active checkout
     new-root = the candidate worktree
     map = transitions/path-map.toml
     output-dir = /tmp/dotfiles-rollout
5. Inspect plan.json and summarize every live symlink that would change.
   Never display secret file contents; the plan should contain paths only.
6. Dry-run stage.py. Refuse to proceed if any target is missing or any link is
   no longer a symlink.
7. If clean, run stage.py --apply.
8. Run the real local acceptance suite:
     ./scripts/onboard doctor
     ./scripts/onboard status --json
     ./iac collect --stdout
     ./iac plan
   plus desktop/audio/Hermes checks relevant to this host.
9. If ANY regression appears, run rollback.py --apply immediately and report.
10. If the staged worktree is healthy, stop and report READY FOR CUTOVER.
    Do not merge or pull into the active checkout without explicit approval.

After approval:
11. Update the canonical checkout with a fast-forward only.
12. Run cutover.py --apply so links point back to the canonical checkout at
    their new paths.
13. Re-run the same acceptance suite.
14. Keep compatibility symlinks and the rollout bundle until a later cleanup
    PR removes them.

Report:
- active HEAD
- candidate HEAD
- symlinks discovered
- symlinks remapped
- missing targets
- tests
- staged smoke result
- rollback result if used
- READY FOR CUTOVER yes/no
```
