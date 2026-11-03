# --- Android speed-ups: fast_android.py in this folder (README-fast-tree.md) --
# Persistent uiautomator2 jar server for the tree, one-trip lock check, and
# on-phone screen hashing for wait_stable. Falls back to stock on any error.
# Off per command with PH_FAST_TREE=0 / PH_FAST_WAIT=0.
def _load_fast_android():
    import importlib.util as _ilu
    import pathlib as _pl
    import sys as _s
    p = _pl.Path(__file__).resolve().parent / "fast_android.py"
    if not p.exists():
        return None
    try:
        spec = _ilu.spec_from_file_location("phone_harness_fast_android", p)
        mod = _ilu.module_from_spec(spec)
        _s.modules["phone_harness_fast_android"] = mod
        spec.loader.exec_module(mod)
        mod.install()
        return mod
    except Exception as e:                       # never break the harness over a speed-up
        print(f"[fast-tree] disabled: {type(e).__name__}: {e}", file=_s.stderr)
        return None


_fast = _load_fast_android()
if _fast is not None:
    wait_stable = _fast.wait_stable
    wait_for_text = _fast.wait_for_text
    fast_tree_status = _fast.fast_tree_status
    fast_tree_stop = _fast.fast_tree_stop
    fast_tree_uninstall = _fast.fast_tree_uninstall
    fast_tree_last_xml = _fast.fast_tree_last_xml
