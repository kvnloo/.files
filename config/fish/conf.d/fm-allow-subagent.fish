# Firstmate primary subagent hatch. Fail-closed elsewhere; only 1 enables the hook.
# Must be present at harness launch; this file makes new fish shells export it.
set -gx FM_ALLOW_SUBAGENT 1
