"""Cooperative checkpoints for read/validation operations running outside the API loop.

A background operation may carry an ``authorize`` callback. It re-checks the
*live* identity of the user who started the operation (account still enabled,
same user, still a project member, still allowed on the target resource). It
runs when the operation starts, periodically at checkpoints, immediately before
every commit (``checkpoint(commit=True)``) and before a result is delivered, so
a disabled account or revoked permission stops queued and running work.
"""
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Event
from typing import Callable


class OperationCancelled(RuntimeError):
    pass


class OperationUnauthorized(RuntimeError):
    """The initiator lost access while the operation was queued or running."""


AUTHORIZE_INTERVAL_SECONDS = 1.0


@dataclass
class OperationContext:
    cancel_event: Event
    report: Callable[[str], None]
    authorize: Callable[[], None] | None = None
    _last_authorized: float = field(default=0.0, repr=False)

    def require_authorized(self, *, force: bool = False) -> None:
        if self.authorize is None:
            return
        now = time.monotonic()
        if not force and now - self._last_authorized < AUTHORIZE_INTERVAL_SECONDS:
            return
        try:
            self.authorize()
        except OperationCancelled:
            raise
        except Exception as exc:
            reason = getattr(exc, "reason", None) or str(exc) or "authorization_revoked"
            raise OperationUnauthorized(f"permission_revoked:{reason}") from exc
        self._last_authorized = now


current_operation: ContextVar[OperationContext | None] = ContextVar("current_operation", default=None)


def checkpoint(message: str = "", *, commit: bool = False) -> None:
    context = current_operation.get()
    if context:
        if context.cancel_event.is_set():
            raise OperationCancelled("检查已取消")
        context.require_authorized(force=commit)
        if message:
            context.report(message)
