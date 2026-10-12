"""Application composition and lifetime wiring.

Construct one service graph per process. The shared run lock prevents filesystem
changes from racing a submission; shutting down web monitoring must not cancel Slurm.
"""

from __future__ import annotations

from pathlib import Path

from .application_services import ApplicationServices
from .access.audit import SQLiteBusinessAuditSink
from .access.directory_grants import DirectoryAccess, DirectoryGrantStore
from .access.execution_control import ExecutionControl
from .access.model_governance import ModelGovernance
from .access.identity_adapter import UnauthenticatedIdentityReader
from .access.resources import ResourceAccess
from .access.service import AuthorizationService
from .capability_registry import CapabilityRegistry
from .capability_tree import CapabilityTree
from .chat_coordinator import ChatCoordinator
from .chat_service import ChatService
from .chat_turns import ChatTurns
from .conversation_service import ConversationService
from .dataset_files import DatasetFiles
from .dataset_service import DatasetService
from .execution import RunnerRegistry, RunService
from .local_store import LocalStore
from .operation_service import OperationService
from .pipeline_library import PipelineLibrary
from .settings import Settings
from .skill_catalog import SkillCatalog
from .skill_loader import SkillLoader
from .workflow_models import (
    Workflow,
)
from .workflow_service import WorkflowService
from .workspace_service import WorkspaceService
from .workspace_tools import WorkspaceTools


def build_services(settings: Settings, *, identity_reader=None, audit_sink=None) -> ApplicationServices:
    """Assemble one service graph.

    ``identity_reader`` is A's production reader (normally
    ``access.request_context.RequestIdentityReader`` around A's identity
    authority). Without it the application fails closed: every business API
    answers 401. ``audit_sink`` is A's common audit; B's business events are
    also kept locally until that sink is wired.
    """
    identity_reader = identity_reader or UnauthenticatedIdentityReader()
    skill_loader = SkillLoader(settings.skills_dir)
    chat_service = ChatService()
    capability_registry = CapabilityRegistry(settings.skills_dir)
    capability_tree = CapabilityTree(settings.skills_dir / "capability.tree.json")
    local_store = LocalStore(settings.database_path)
    business_audit = SQLiteBusinessAuditSink(local_store._connect, forward=audit_sink)
    authorization_service = AuthorizationService(identity_reader, business_audit)
    resource_access = ResourceAccess(local_store, authorization_service)
    directory_access = DirectoryAccess(DirectoryGrantStore(local_store), resource_access)
    execution_control = ExecutionControl(local_store)
    # Historical results (runs reused as inputs) inherit their task permission.
    local_store.historical_visibility = lambda: resource_access.visible_ids("task")
    # Ownership of new business records commits in the creating transaction.
    local_store.ownership_recorder = (
        lambda resource_type, resource_id, connection: resource_access.record_creation(
            resource_type, resource_id, connection=connection
        )
    )
    operation_service = OperationService(local_store)
    dataset_service = DatasetService(settings.project_root, local_store)
    conversation_service = ConversationService(local_store, chat_service, authorization_service=authorization_service)
    workspace_service = WorkspaceService(
        local_store, settings.project_root / "workspaces"
    )
    workspace_service.access = resource_access
    workspace_service.directories = directory_access
    dataset_files = DatasetFiles(dataset_service)
    dataset_files.access = resource_access
    workspace_tools = WorkspaceTools(workspace_service, chat_service, dataset_files)
    runner_registry = RunnerRegistry()
    skill_catalog = SkillCatalog(skill_loader, capability_registry, runner_registry)
    workspace_tools.skill_catalog = skill_catalog
    model_governance = ModelGovernance(local_store, resource_access)
    chat_service.governance = model_governance
    workspace_tools.governance = model_governance
    workflow_service = WorkflowService(
        chat_service,
        capability_registry,
        local_store,
        dataset_service,
        capability_tree,
        skill_loader,
        runner_registry.available_ids(),
        runner_registry,
    )
    run_service = RunService(
        local_store,
        capability_registry,
        runner_registry,
        settings.output_root,
    )

    def _protected_workspace_paths():
        # Reads remain available; mutations cannot invalidate queued/running jobs.
        protected = [
            settings.database_path.parent,
            settings.project_root / "bakend",
            settings.project_root / "skills",
            settings.project_root / "deploy",
            settings.project_root / ".conda",
        ]
        for run in local_store.incomplete_runs():
            protected.append(Path(run.output_directory))
            workflow = Workflow.model_validate(run.plan_snapshot)
            if workflow.dataset:
                protected.append(Path(workflow.dataset.absolute_path))
            for step in workflow.steps:
                for binding in step.input_bindings.values():
                    protected.extend(
                        Path(p)
                        for p in binding.absolute_paths
                        or ([binding.absolute_path] if binding.absolute_path else [])
                    )
                    protected.extend(
                        Path(match.absolute_path)
                        for match in binding.sample_matches
                        if match.absolute_path
                    )
        return protected

    workspace_service.protected_paths = _protected_workspace_paths
    workspace_service.run_lock = run_service.mutation_lock
    dataset_service.registration_lock = run_service.mutation_lock
    dataset_service.registration_guard = workspace_service.guard_dataset_registration
    pipeline_library = PipelineLibrary(local_store, capability_registry)
    pipeline_library.access = resource_access
    capability_registry.library_provider = pipeline_library.bindings
    chat_coordinator = ChatCoordinator(
        conversation_service,
        workspace_service,
        dataset_files,
        workspace_tools,
        skill_loader,
        workflow_service,
        chat_service,
    )
    chat_turns = ChatTurns(
        local_store, conversation_service, chat_coordinator.reply, resource_access=resource_access
    )
    return ApplicationServices(
        settings=settings,
        skill_loader=skill_loader,
        chat_service=chat_service,
        capability_registry=capability_registry,
        capability_tree=capability_tree,
        local_store=local_store,
        operation_service=operation_service,
        dataset_service=dataset_service,
        conversation_service=conversation_service,
        workspace_service=workspace_service,
        dataset_files=dataset_files,
        workspace_tools=workspace_tools,
        runner_registry=runner_registry,
        skill_catalog=skill_catalog,
        workflow_service=workflow_service,
        run_service=run_service,
        pipeline_library=pipeline_library,
        chat_turns=chat_turns,
        chat_coordinator=chat_coordinator,
        authorization_service=authorization_service,
        resource_access=resource_access,
        directory_access=directory_access,
        execution_control=execution_control,
        business_audit=business_audit,
        model_governance=model_governance,
    )
