"""Resource-policy subroutes supplied by Task B for A's management pages.

Every route requires a trusted identity (the application mounts this router
behind the authentication dependency) and rechecks the specific permission.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..access.contracts import AuthorizationDenied, PlatformRole, ResourceAction, SharingScope
from ..access.execution_control import QuotaPolicy
from ..access.filesystem import GrantScope
from ..access.request_context import requested_project
from ..application_services import ApplicationServices

ManagedType = Literal["dataset", "output", "task", "pipeline"]


class ShareRequest(BaseModel):
    scope: Literal["private", "project"]
    expected_revision: int = Field(ge=0)


class HandoverRequest(BaseModel):
    new_manager_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=0)


class TakeoverRequest(BaseModel):
    reason: str = Field(min_length=8, max_length=500)
    expected_revision: int = Field(ge=0)


class GrantRequest(BaseModel):
    project_id: str = Field(default="", max_length=128)
    user_id: str = Field(default="*", max_length=200)
    root: str = Field(min_length=1, max_length=4096)
    scope: Literal["read", "write"]


class ModelPolicyRequest(BaseModel):
    allow_external_file_text: bool


class QuotaRequest(BaseModel):
    max_concurrent_units: int = Field(ge=1, le=4096)
    max_cpus_per_unit: int = Field(ge=1, le=1024)
    max_memory_gb_per_unit: int = Field(ge=1, le=8192)
    max_gpus_per_unit: int = Field(ge=0, le=64)
    allowed_nodes: list[str] | None = Field(default=None, max_length=256)


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    def access():
        if services.resource_access is None:
            raise AuthorizationDenied("authentication_required")
        return services.resource_access

    def conflict(exc: ValueError) -> HTTPException:
        return HTTPException(409, {"code": str(exc), "message": str(exc)})

    @router.get("/api/access/scope")
    def scope():
        identity = access().actor()
        project = access().current_project()
        return {
            "userId": identity.user_id,
            "projectId": project,
            "platformRole": identity.platform_role.value,
        }

    @router.get("/api/access/resources/{resource_type}/{resource_id}")
    def resource(resource_type: ManagedType | Literal["conversation"], resource_id: str):
        access().require(resource_type, resource_id, ResourceAction.READ)
        return access().view(resource_type, resource_id).as_dict()

    @router.post("/api/access/resources/{resource_type}/{resource_id}/share")
    def share(resource_type: ManagedType, resource_id: str, request: ShareRequest):
        try:
            return access().share(
                resource_type, resource_id, SharingScope(request.scope),
                expected_revision=request.expected_revision,
            ).as_dict()
        except ValueError as exc:
            raise conflict(exc) from exc

    @router.post("/api/access/resources/{resource_type}/{resource_id}/handover")
    def handover(resource_type: ManagedType, resource_id: str, request: HandoverRequest):
        try:
            return access().handover(
                resource_type, resource_id, request.new_manager_id,
                expected_revision=request.expected_revision,
            ).as_dict()
        except ValueError as exc:
            raise conflict(exc) from exc

    @router.post("/api/access/resources/{resource_type}/{resource_id}/takeover")
    def takeover(resource_type: ManagedType | Literal["conversation"], resource_id: str, request: TakeoverRequest):
        try:
            return access().takeover(
                resource_type, resource_id, reason=request.reason,
                expected_revision=request.expected_revision,
            ).as_dict()
        except ValueError as exc:
            raise conflict(exc) from exc

    # ------------------------------------------------------------ directories
    def directories():
        if services.directory_access is None:
            raise AuthorizationDenied("authentication_required")
        return services.directory_access

    @router.get("/api/access/directory-grants/mine")
    def my_grants():
        user_id, project_id = directories().scope()
        return {"items": [
            {"grant_id": grant_id, "root": str(grant.root), "scope": grant.scope.value, "revision": grant.revision}
            for grant_id, grant in directories().grants.grants_for(user_id, project_id)
        ]}

    @router.get("/api/access/directory-grants")
    def list_grants(project_id: str = ""):
        directories().require_manage(project_id)
        return {"items": directories().grants.list(project_id)}

    @router.post("/api/access/directory-grants")
    def create_grant(request: GrantRequest):
        try:
            return directories().create_grant(
                user_id=request.user_id, project_id=request.project_id,
                root=Path(request.root), scope=GrantScope(request.scope),
            )
        except ValueError as exc:
            raise conflict(exc) from exc

    @router.delete("/api/access/directory-grants/{grant_id}")
    def revoke_grant(grant_id: str):
        try:
            return directories().revoke_grant(grant_id)
        except KeyError as exc:
            raise HTTPException(404, "Grant not found") from exc

    # ---------------------------------------------------------------- quotas
    def require_quota_manager(subject: str) -> None:
        identity = access().actor()
        if identity.platform_role is PlatformRole.ADMIN:
            return
        if subject.startswith("project:"):
            directories().require_manage(subject.split(":", 1)[1])
            return
        raise AuthorizationDenied("quota_management_denied")

    def valid_subject(subject: str) -> str:
        if subject != "default" and not subject.startswith(("user:", "project:")):
            raise HTTPException(422, "Quota subject must be default, user:<id> or project:<id>")
        return subject

    @router.get("/api/access/quotas/mine")
    def my_quota():
        identity = access().actor()
        project = access().current_project()
        control = services.execution_control
        result = {
            "user": control.quota_for(f"user:{identity.user_id}").as_dict(),
            "user_reserved_units": control.usage(submitter_id=identity.user_id),
        }
        if project:
            result["project"] = control.quota_for(f"project:{project}").as_dict()
            result["project_reserved_units"] = control.usage(project_id=project)
        return result

    @router.get("/api/access/quotas/{subject}")
    def get_quota(subject: str):
        require_quota_manager(valid_subject(subject))
        return {"subject": subject, **services.execution_control.quota_for(subject).as_dict()}

    @router.put("/api/access/quotas/{subject}")
    def put_quota(subject: str, request: QuotaRequest):
        require_quota_manager(valid_subject(subject))
        policy = QuotaPolicy(
            request.max_concurrent_units, request.max_cpus_per_unit,
            request.max_memory_gb_per_unit, request.max_gpus_per_unit,
            tuple(request.allowed_nodes) if request.allowed_nodes is not None else None,
        )
        try:
            result = services.execution_control.set_quota(subject, policy, updated_by=access().actor().user_id)
        except ValueError as exc:
            raise conflict(exc) from exc
        access()._audit(
            "execution.quota.updated", resource_type="quota", resource_id=subject,
            action="update", reason="quota_changed",
            project_id=subject.split(":", 1)[1] if subject.startswith("project:") else requested_project(),
        )
        return result

    # ---------------------------------------------------------- model policy
    def governance():
        if services.model_governance is None:
            raise AuthorizationDenied("authentication_required")
        access().actor()
        return services.model_governance

    @router.get("/api/access/model-policy")
    def model_policy():
        policy = governance().current_policy()
        return {**policy, "can_manage": governance().can_manage(policy["subject"])}

    @router.put("/api/access/model-policy/{subject}")
    def put_model_policy(subject: str, request: ModelPolicyRequest):
        if subject != "default" and not subject.startswith(("personal:", "project:")):
            raise HTTPException(422, "Policy subject must be personal:<user> or project:<id>")
        if subject == "default" and access().actor().platform_role is not PlatformRole.ADMIN:
            raise AuthorizationDenied("model_policy_management_denied")
        return governance().set_policy(subject, request.allow_external_file_text)

    @router.get("/api/access/model-usage/mine")
    def my_model_usage():
        identity = access().actor()
        project = access().current_project()
        result = {"user": governance().usage_summary(user_id=identity.user_id)}
        if project:
            result["project"] = governance().usage_summary(project_id=project)
        return result

    return router
