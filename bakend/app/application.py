"""FastAPI factory: transport registration and process lifetime, no business logic."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import (
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

    @app.exception_handler(ServiceError)
    async def application_error(request: Request, error: ServiceError):
        return JSONResponse(
            status_code=error.status_code, content={"detail": error.detail}
        )

    app.include_router(
        workspace_router(services.workspace_service, services.dataset_files, services.authorization_service)
    )
    app.include_router(
        library_router(
            services.pipeline_library,
            services.workflow_service,
            services.workspace_service,
            services.runner_registry,
            services.chat_service,
        )
    )
    def require_authenticated_request() -> None:
        # Business/resource APIs must fail closed when authoritative identity is
        # not configured; endpoint-specific policy checks still apply as well.
        if services.authorization_service is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            services.authorization_service.require_authenticated()
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail="Authentication required") from exc

    for group in (health, catalog):
        app.include_router(group.router_for(services))

    for group in (
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
