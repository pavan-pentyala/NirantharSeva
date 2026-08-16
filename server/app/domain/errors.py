"""Error hierarchy shared across the domain, sync, and API layers."""


class DomainError(Exception):
    """Base for all errors raised by domain/sync logic."""


class NotFoundError(DomainError):
    pass


class GuardViolationError(DomainError):
    """A state transition was attempted without the required role or
    preconditions. Never caught silently — see plan §6, invariant I4."""


class ConflictError(DomainError):
    """A write lost a conflict against a newer or concurrent write.
    See invariant I6 — the losing write is never deleted."""
