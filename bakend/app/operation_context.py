"""Cooperative checkpoints for read/validation operations running outside the API loop."""
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Event
from typing import Callable


class OperationCancelled(RuntimeError):
    pass


@dataclass
class OperationContext:
    cancel_event: Event
    report: Callable[[str], None]


current_operation: ContextVar[OperationContext | None] = ContextVar("current_operation", default=None)


def checkpoint(message: str = "") -> None:
    context = current_operation.get()
    if context:
        if context.cancel_event.is_set():
            raise OperationCancelled("检查已取消")
        if message:
            context.report(message)
