"""Health HTTP endpoints; dependencies are supplied by the application factory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ..application_services import ApplicationServices
from ..maintenance import inventory_outputs, storage_status


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.get("/")
    def root() -> dict[str, str]:
        return {"name": "NeuroWeave API", "docs": "/docs"}

    @router.get("/api/health")
    def health(include_runtime: bool = True) -> dict[str, Any]:
        skill_stats = services.skill_loader.stats()
        skill_stats["execution_enabled"] = services.run_service.enabled
        result = {
            "status": "ok",
            "release": {
                "api_contract": "2",
                "frontend_revision": os.getenv(
                    "NEUROWEAVE_RELEASE_REVISION", "development"
                ),
                "backend_revision": os.getenv(
                    "NEUROWEAVE_RELEASE_REVISION", "development"
                ),
                "worker_revision": Path(
                    os.getenv("LOCALFLOW_SLURM_WORKER_ROOT", "unversioned")
                ).name,
                "maintenance": (
                    services.settings.database_path.parent / "release-maintenance.lock"
                ).exists(),
            },
            "mode": services.chat_service.mode,
            "model": services.chat_service.model or "conversation-demo",
            "prompt_version": services.chat_service.prompt_version,
            "thinking": services.chat_service.thinking
            if services.chat_service.mode == "model"
            else "disabled",
            "services.skill_catalog": skill_stats,
            "capability_catalog": services.capability_registry.stats(),
            "services.capability_tree": services.capability_tree.stats(),
            "conversation_memory": {
                "compact_trigger_tokens": services.conversation_service.compact_trigger_tokens,
                "keep_recent_messages": services.conversation_service.keep_recent_messages,
                "storage": "sqlite",
            },
            "persistence": "sqlite",
            "dataset_roots": len(services.dataset_service.roots()),
            "execution": {
                "enabled": services.run_service.enabled,
                "runner_count": len(services.runner_registry.ids()),
                "output_root": str(services.settings.output_root),
            },
        }
        if include_runtime:
            runners = services.runner_registry.public_catalog()
            result["execution"].update(
                ready_runner_count=sum(bool(item.get("available")) for item in runners),
                runners=runners,
            )
        return result

    def _storage_paths():
        backups = Path(
            os.getenv(
                "LOCALFLOW_BACKUP_ROOT",
                str(services.settings.database_path.parent / "backups"),
            )
        )
        roots = [
            services.settings.output_root,
            Path(
                os.getenv(
                    "LOCALFLOW_SLURM_OUTPUT_ROOT", str(services.settings.output_root)
                )
            ),
        ]
        return backups, roots

    @router.get("/api/maintenance/storage")
    def maintenance_storage() -> dict[str, Any]:
        backups, roots = _storage_paths()
        return {
            **storage_status(services.settings.database_path, backups, roots),
            "backend_revision": os.getenv("NEUROWEAVE_RELEASE_REVISION", "development"),
        }

    @router.post("/api/maintenance/inventory-jobs", status_code=202)
    def maintenance_inventory() -> dict[str, Any]:
        _, roots = _storage_paths()
        try:
            return services.operation_service.submit(
                "storage_inventory",
                "outputs",
                lambda: inventory_outputs(services.settings.database_path, roots),
            )
        except ValueError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

    return router
