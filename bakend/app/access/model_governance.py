"""Model-call governance: external file-text policy and usage records (B5).

* Project/personal policy decides whether file text read by model tools may
  be sent to an *external* model provider. A local provider (localhost or a
  private network address) is never external.
* Every model call is recorded with the current user, project, request id,
  stage, model and the token usage the provider reports, and emits a
  ``model.call`` business audit event. Prompts and file contents are never
  stored.
"""

from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from .contracts import AuthorizationDenied, PlatformRole, ProjectRole
from .request_context import request_id, requested_project

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_policies (
    subject TEXT PRIMARY KEY,
    allow_external_file_text INTEGER NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_usage (
    usage_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    user_id TEXT NOT NULL,
    project_id TEXT,
    request_id TEXT,
    stage TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    external INTEGER NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER
);
CREATE INDEX IF NOT EXISTS idx_model_usage_user ON model_usage(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_model_usage_project ON model_usage(project_id, created_at);
"""

WITHHELD = "[已隐藏：项目/个人策略不允许把文件内容发送给外部模型]"


def initialize_model_schema(connection) -> None:
    connection.executescript(SCHEMA)


def is_external_endpoint(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    if not host:
        return False
    if host in {"localhost", "host.docker.internal"} or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (address.is_loopback or address.is_private or address.is_link_local)


def _default_allowed() -> bool:
    return os.getenv("NEUROWEAVE_ALLOW_FILE_TEXT_TO_EXTERNAL_MODEL", "true").lower() in {"1", "true", "yes"}


class ModelGovernance:
    def __init__(self, store, resources):
        self.store = store
        self.resources = resources

    # ---------------------------------------------------------------- policy
    def _subject(self) -> str:
        identity = self.resources.identity_reader.current_identity()
        project = requested_project()
        return f"project:{project}" if project else f"personal:{identity.user_id}"

    def policy_for(self, subject: str) -> dict:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM model_policies WHERE subject=?", (subject,)).fetchone()
        if row is None:
            return {"subject": subject, "allow_external_file_text": _default_allowed(), "source": "default"}
        return {"subject": subject, "allow_external_file_text": bool(row["allow_external_file_text"]),
                "source": "configured", "updated_by": row["updated_by"], "updated_at": row["updated_at"]}

    def current_policy(self) -> dict:
        return self.policy_for(self._subject())

    def file_text_allowed(self, base_url: str) -> bool:
        if not is_external_endpoint(base_url):
            return True
        return bool(self.current_policy()["allow_external_file_text"])

    def can_manage(self, subject: str) -> bool:
        identity = self.resources.actor()
        if identity.platform_role is PlatformRole.ADMIN:
            return True
        if subject == f"personal:{identity.user_id}":
            return True
        if subject.startswith("project:"):
            project_id = subject.split(":", 1)[1]
            membership = self.resources.identity_reader.project_membership(project_id)
            return bool(membership and membership.active and membership.role is ProjectRole.MANAGER)
        return False

    def set_policy(self, subject: str, allow: bool) -> dict:
        if not self.can_manage(subject):
            raise AuthorizationDenied("model_policy_management_denied")
        actor = self.resources.actor().user_id
        now = datetime.now(timezone.utc).isoformat()
        with self.store._lock, self.store._connect() as db:
            db.execute(
                """INSERT INTO model_policies VALUES(?,?,?,?) ON CONFLICT(subject) DO UPDATE SET
                   allow_external_file_text=excluded.allow_external_file_text,
                   updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
                (subject, int(allow), actor, now),
            )
        self.resources._audit(
            "model.policy.updated", resource_type="model_policy", resource_id=subject,
            action="update", reason=f"allow_external_file_text={allow}",
            project_id=subject.split(":", 1)[1] if subject.startswith("project:") else None,
        )
        return self.policy_for(subject)

    def redact_tool_result(self, result, base_url: str):
        """Withhold file text from tool results when the policy forbids it."""
        if not isinstance(result, dict) or "text" not in result or self.file_text_allowed(base_url):
            return result
        self.resources._audit(
            "model.file_text.withheld", resource_type="file", resource_id=str(result.get("path") or ""),
            action="read", reason="external_model_policy", project_id=requested_project(),
        )
        return {**result, "text": WITHHELD, "withheld_by_policy": True}

    # ----------------------------------------------------------------- usage
    def record_call(self, *, stage: str, provider: str, model: str, base_url: str, usage: dict | None) -> None:
        identity = self.resources.identity_reader.current_identity()
        usage = usage if isinstance(usage, dict) else {}

        def number(key):
            value = usage.get(key)
            return int(value) if isinstance(value, (int, float)) else None

        project = requested_project()
        external = is_external_endpoint(base_url)
        with self.store._connect() as db:
            db.execute(
                "INSERT INTO model_usage VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid4().hex, datetime.now(timezone.utc).isoformat(), identity.user_id or "",
                    project, request_id(), stage, provider, model, int(external),
                    number("prompt_tokens"), number("completion_tokens"), number("total_tokens"),
                ),
            )
        self.resources._audit(
            "model.call", resource_type="model_call", resource_id=request_id(),
            action="execute", reason=stage, project_id=project,
            summary={"model": model, "external": external, "total_tokens": number("total_tokens")},
        )

    def usage_summary(self, *, user_id: str | None = None, project_id: str | None = None) -> dict:
        column, value = ("user_id", user_id) if user_id is not None else ("project_id", project_id)
        with self.store._connect() as db:
            row = db.execute(
                f"""SELECT COUNT(*) AS calls, COALESCE(SUM(prompt_tokens),0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens),0) AS completion_tokens,
                    COALESCE(SUM(total_tokens),0) AS total_tokens
                    FROM model_usage WHERE {column}=?""",
                (value,),
            ).fetchone()
        return dict(row)
