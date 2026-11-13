"""Managed Groot stage producers share a lock; retention takes it exclusively."""
from contextlib import contextmanager
import fcntl
from pathlib import Path


@contextmanager
def _lock(mode, path=None):
    target = Path(path) if path is not None else Path.home() / '.local/state/fleet/stage-retention.lock'
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('a') as stream:
        fcntl.flock(stream, mode)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def submission_lock(path=None):
    """Hold from before stage publication through Kubernetes Job creation."""
    return _lock(fcntl.LOCK_SH, path)


def exclusive_retention_lock(path=None):
    """Hold through receipt observation, planning, fresh API checks and apply."""
    return _lock(fcntl.LOCK_EX, path)
