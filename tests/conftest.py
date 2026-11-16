"""Keep operator-machine checks separate from the clean-runner suite.

Every temp dir the suite makes (mkdtemp in tests and their subprocesses) lands in one session dir
that is removed at exit; tests used to leak thousands of fixtures into tmpfs /tmp.
"""
import os
import shutil
import tempfile

_SESSION_TMP = None


def pytest_addoption(parser):
    parser.addoption(
        "--run-live-system",
        action="store_true",
        default=False,
        help="Include checks of the deployed desktop, installed tools, and real accounts.",
    )


def pytest_configure(config):
    global _SESSION_TMP
    _SESSION_TMP = tempfile.mkdtemp(prefix="files-tests-")
    os.environ["TMPDIR"] = _SESSION_TMP
    tempfile.tempdir = _SESSION_TMP
    config.addinivalue_line(
        "markers",
        "live_system: checks deployed host state or real provider accounts (explicit opt-in)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live-system"):
        return
    selected = []
    live = []
    for item in items:
        if item.get_closest_marker("live_system") is not None:
            live.append(item)
        else:
            selected.append(item)
    items[:] = selected
    if live:
        config.hook.pytest_deselected(items=live)


def pytest_unconfigure(config):
    if _SESSION_TMP:
        tempfile.tempdir = None
        for root, dirs, _ in os.walk(_SESSION_TMP):   # read-only fixture dirs would survive rmtree
            for d in dirs:
                p = os.path.join(root, d)
                if not os.path.islink(p):
                    os.chmod(p, 0o700)
        shutil.rmtree(_SESSION_TMP, ignore_errors=True)
