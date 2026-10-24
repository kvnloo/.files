# Dotfiles migration, 2026-10-04

The 2026-09-22 receipt kept `migration/` in place because
`02-deploy-dotfiles.sh` was still inside the 7-day hot window (content commit
2026-09-17). That window has cleared.

## Path move

| Path | Result |
| --- | --- |
| `migration/` | Moved to `transitions/legacy/cachyos-migration/`. Old path is a relative symlink. |
| `claudedocs`, `POLYBAR_PYWAL_USAGE.md` | Unchanged compatibility symlinks from 2026-09-22. |
| `proposal_codexbar_aggregate.md` | Still absent. |

Active scripts `00a` through `08` no longer treat the parent of `readlink -f`
as the repo root. They walk up to `.git`. A symlink cutover therefore does not
point `DOTFILES` at `transitions/legacy/`.

`migration/old-scripts/` still computes a few log paths from its own directory.
Those scripts are historical and were not the hot path.
