"""Request-scoped identity plumbing between A's authentication and B's policies.

Developer A owns cookies, sessions and membership storage. This module only
defines the narrow adapter B needs and the per-request context it reads:

* ``IdentityAuthority`` is implemented by A. ``resolve_session`` turns a request
  into an opaque session handle; ``identity_for_session`` and
  ``membership_for`` are *live* lookups so a disabled account, revoked session or
  removed membership takes effect on the very next check, including checks made
  later by background chat turns that inherited the request context.
* ``RequestIdentityReader`` is the production ``IdentityReader``. It never
  trusts a client-supplied user id or role.
* The requested project scope comes from the ``X-NeuroWeave-Project`` header that
  A's shared HTTP client sends. It only *selects* a scope; membership is still
  checked by every policy decision.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Protocol
from uuid import uuid4

from .contracts import Identity, IdentityReader, ProjectMembership

PROJECT_HEADER = "x-neuroweave-project"
REASON_HEADER = "x-neuroweave-reason"
REQUEST_ID_HEADER = "x-request-id"
_PROJECT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

_session: ContextVar[Any | None] = ContextVar("neuroweave_session", default=None)
_project: ContextVar[str | None] = ContextVar("neuroweave_project", default=None)
_request_id: ContextVar[str | None] = ContextVar("neuroweave_request_id", default=None)
_reason: ContextVar[str | None] = ContextVar("neuroweave_reason", default=None)

ANONYMOUS = Identity(user_id="", enabled=False)


class InvalidProjectScope(ValueError):
    pass


def requested_project() -> str | None:
    return _project.get()


def request_id() -> str | None:
    return _request_id.get()


def administrative_reason() -> str | None:
    """Reason given for managing another member's shared resource (audited)."""
    return _reason.get()


def parse_project_header(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value == "personal":
        return None
    if not _PROJECT_PATTERN.fullmatch(value):
        raise InvalidProjectScope("invalid_project_scope")
    return value


@contextmanager
def request_scope(
    *, session: Any | None = None, project_id: str | None = None, request_identifier: str | None = None,
    reason: str | None = None,
) -> Iterator[None]:
    tokens = (
        _session.set(session),
        _project.set(project_id),
        _request_id.set(request_identifier or uuid4().hex),
        _reason.set(reason),
    )
    try:
        yield
    finally:
        _reason.reset(tokens[3])
        _request_id.reset(tokens[2])
        _project.reset(tokens[1])
        _session.reset(tokens[0])


class IdentityAuthority(Protocol):
    """What B needs from A's ``identity`` module (wired by A in bootstrap)."""

    def resolve_session(self, request: Any) -> Any | None: ...
    def identity_for_session(self, session: Any) -> Identity | None: ...
    def membership_for(self, user_id: str, project_id: str) -> ProjectMembership | None: ...


class RequestIdentityReader(IdentityReader):
    """Production identity reader: live, request-scoped, fail-closed."""

    def __init__(self, authority: IdentityAuthority):
        self.authority = authority

    def resolve_session(self, request: Any) -> Any | None:
        return self.authority.resolve_session(request)

    def current_identity(self) -> Identity:
        session = _session.get()
        if session is None:
            return ANONYMOUS
        identity = self.authority.identity_for_session(session)
        if identity is None or not identity.user_id:
            return ANONYMOUS
        return identity

    def project_membership(self, project_id: str) -> ProjectMembership | None:
        identity = self.current_identity()
        if not identity.authenticated or not project_id:
            return None
        membership = self.authority.membership_for(identity.user_id, project_id)
        if membership is None or membership.user_id != identity.user_id:
            return None
        return membership

    def membership_of(self, user_id: str, project_id: str) -> ProjectMembership | None:
        return self.authority.membership_for(user_id, project_id)


def install_request_context(app, identity_reader_provider) -> None:
    """Bind session handle, requested project and request id for each request.

    ``identity_reader_provider`` is called per request so tests and A's final
    wiring can swap the reader without rebuilding the application.
    """

    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def neuroweave_request_context(request, call_next):
        try:
            project_id = parse_project_header(request.headers.get(PROJECT_HEADER))
        except InvalidProjectScope:
            return JSONResponse({"detail": "Invalid project scope"}, status_code=400)
        reader = identity_reader_provider()
        resolver = getattr(reader, "resolve_session", None)
        session = resolver(request) if callable(resolver) else None
        identifier = (request.headers.get(REQUEST_ID_HEADER) or "")[:100] or None
        from urllib.parse import unquote

        reason = unquote(request.headers.get(REASON_HEADER) or "").strip()[:500] or None
        with request_scope(session=session, project_id=project_id, request_identifier=identifier, reason=reason):
            return await call_next(request)
