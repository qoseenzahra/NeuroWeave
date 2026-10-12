"""FastAPI factory: transport registration and process lifetime, no business logic."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .access.contracts import AuthorizationDenied, ResourceNotFound
from .access.execution_control import QuotaExceeded
from .access.request_context import install_request_context
from .api import (
    access,
    catalog,
    chat,
    conversations,
    datasets,
    execution,
    health,
    operations,
    workflow_inputs,
    workflows,
)
from .api.middleware import install_maintenance
from .application_services import ApplicationServices
from .bootstrap import build_services
from .catalog_locale import CatalogLocaleMiddleware
from .errors import ServiceError
from .library_routes import library_router
from .settings import Settings
from .workspace_routes import workspace_router


def install_access_error_handlers(app: FastAPI) -> None:
    """Uniform 401/403/404/429 translation for Task B authorization errors."""

    @app.exception_handler(ResourceNotFound)
    async def resource_not_found(request: Request, error: ResourceNotFound):
        # Invisible objects are indistinguishable from missing ones.
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    @app.exception_handler(AuthorizationDenied)
    async def authorization_denied(request: Request, error: AuthorizationDenied):
        reason = str(error)
        if reason in {"authentication_required", "account_disabled"}:
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})
        return JSONResponse(
            status_code=403,
            content={"detail": {"code": reason or "forbidden", "message": "Not permitted"}},
        )

    @app.exception_handler(QuotaExceeded)
    async def quota_exceeded(request: Request, error: QuotaExceeded):
        return JSONResponse(
            status_code=429,
            content={"detail": {"code": str(error), "message": "Execution quota exceeded"}},
        )


def create_app(services: ApplicationServices | None = None) -> FastAPI:
    services = services or build_services(Settings.from_environment())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await services.chat_turns.shutdown()
        services.operation_service.shutdown()
        services.run_service.shutdown()

    app = FastAPI(
        title="NeuroWeave API",
        version="0.1.0",
        description="Local dialogue and skill-discovery API.",
        lifespan=lifespan,
    )
    app.state.services = services
    app.add_middleware(CatalogLocaleMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(services.settings.origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    install_maintenance(app, services)
    # Outermost: bind the session handle, requested project and request id
    # before any route or background task reads the current identity.
    install_request_context(
        app,
        lambda: services.authorization_service.identity_reader
        if services.authorization_service is not None else None,
    )

    @app.exception_handler(ServiceError)
    async def application_error(request: Request, error: ServiceError):
        return JSONResponse(
            status_code=error.status_code, content={"detail": error.detail}
        )

    install_access_error_handlers(app)

    def require_authenticated_request() -> None:
        # Business/resource APIs must fail closed when authoritative identity is
        # not configured; endpoint-specific policy checks still apply as well.
        if services.authorization_service is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            services.authorization_service.require_authenticated()
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail="Authentication required") from exc

    app.include_router(
        workspace_router(
            services.workspace_service,
            services.dataset_files,
            services.authorization_service,
            turn_owner=services.chat_turns.owner_of,
        )
    )
    app.include_router(
        library_router(
            services.pipeline_library,
            services.workflow_service,
            services.workspace_service,
            services.runner_registry,
            services.chat_service,
            access=services.resource_access,
        ),
        dependencies=[Depends(require_authenticated_request)],
    )
    # Minimal liveness stays anonymous; maintenance endpoints inside the health
    # router require identity themselves.
    app.include_router(health.router_for(services))

    for group in (
        catalog,
        access,
        datasets,
        operations,
        conversations,
        chat,
        workflows,
        workflow_inputs,
        execution,
    ):
        app.include_router(
            group.router_for(services),
            dependencies=[Depends(require_authenticated_request)],
        )
    return app
