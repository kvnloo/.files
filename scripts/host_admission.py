"""Pure host-layout admission; exhaustively parity-checked against bend/host_layout/MODEL.bend."""
from enum import Enum


class Hosts(Enum):
    NONE = 'HNone'
    ONE = 'HOne'
    MANY = 'HMany'


class Parent(Enum):
    REAL = 'PReal'
    THROUGH_CHECKOUT = 'PThroughCheckout'


class Live(Enum):
    CHANGED = 'LChanged'
    ABSENT = 'AAbsent'
    SAME_BYTES = 'ASameBytes'
    INVENTORIED = 'AInventoried'
    VERIFIED_STAMP = 'AVerifiedStamp'


class Mount(Enum):
    NOT_DECLARED = 'MNotDeclared'
    MOUNTED = 'MMounted'
    UNMOUNTED = 'MUnmounted'


class Reason(Enum):
    NO_HOST = 0
    AMBIGUOUS_HOST = 1
    NO_MANIFEST = 2
    THROUGH_CHECKOUT = 3
    CHANGED = 4
    UNMOUNTED = 5


LINK = 6


def decide(hosts, manifest, parent, live, mount, fresh):
    """Return LINK or a refusal Reason; first refusal wins in MODEL.decide order."""
    if hosts is Hosts.NONE:
        return Reason.NO_HOST
    if hosts is Hosts.MANY:
        return Reason.AMBIGUOUS_HOST
    if not manifest:
        return Reason.NO_MANIFEST
    if parent is Parent.THROUGH_CHECKOUT:
        return Reason.THROUGH_CHECKOUT
    if live is Live.CHANGED:
        return Reason.CHANGED
    if mount is Mount.UNMOUNTED and fresh:
        return Reason.UNMOUNTED
    return LINK


def code(verdict):
    return LINK if verdict == LINK else verdict.value


def status(unknown, drift):
    return 'unknown' if unknown else 'drift' if drift else 'clean'


def hosts_from_count(count):
    return Hosts.NONE if count == 0 else Hosts.ONE if count == 1 else Hosts.MANY
