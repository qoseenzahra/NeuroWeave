from __future__ import annotations

import tempfile
from pathlib import Path
from threading import Event

from ..workflow_models import MethodOption, Workflow, WorkflowStep
from .base import RunnerContext, TrustedRunner
from .runners.ants import AntsRegistrationRunner
from .runners.bids_prepare import BidsPrepareRunner
from .runners.bids_apps import FmriprepRunner, QsiprepRunner
from .runners.dcm2niix import Dcm2niixRunner
from .runners.dataset_inspect import DatasetInspectRunner
from .runners.dipy import DipyTensorRunner
from .runners.freesurfer import FreeSurferReconAllRunner
from .runners.fsl import FslDtifitRunner, FslEddyRunner, FslFlirtRunner
from .runners.mrtrix import MrtrixTckgenRunner
from .runners.mrtrix_pipeline import (
    MrtrixDwi2FodRunner,
    MrtrixDwi2ResponseRunner,
    MrtrixFiveTtGenRunner,
    MrtrixTck2ConnectomeRunner,
)
from .runners.modality_scripts import AslCbfRunner, NiftiInspectRunner, PetSuvrRunner
from .runners.nii2dcm import Nii2DcmRunner
from .runners.report import ReportBuilderRunner
from .runners.table_clean import TableCleanRunner
from .runners.reviewed import ReviewedRunner, specifications


class RunnerRegistry:
    """Allowlist of code-reviewed runners that may execute on the server."""

    def __init__(self) -> None:
        runners: list[TrustedRunner] = [
            DatasetInspectRunner(),
            AntsRegistrationRunner(),
            BidsPrepareRunner(),
            FmriprepRunner(),
            QsiprepRunner(),
            Dcm2niixRunner(),
            DipyTensorRunner(),
            FslFlirtRunner(),
            FslDtifitRunner(),
            FslEddyRunner(),
            MrtrixTckgenRunner(),
            MrtrixDwi2ResponseRunner(),
            MrtrixDwi2FodRunner(),
            MrtrixFiveTtGenRunner(),
            MrtrixTck2ConnectomeRunner(),
            AslCbfRunner(),
            PetSuvrRunner(),
            NiftiInspectRunner(),
            Nii2DcmRunner(),
            FreeSurferReconAllRunner(),
            ReportBuilderRunner(),
            TableCleanRunner(),
        ]
        runners.extend(ReviewedRunner(spec) for spec in specifications().values())
        self._runners = {runner.runner_id: runner for runner in runners}

    def ids(self) -> set[str]:
        return set(self._runners)

    def get(self, runner_id: str) -> TrustedRunner | None:
        return self._runners.get(runner_id)

    def available_ids(self) -> set[str]:
        return {
            runner_id
            for runner_id, runner in self._runners.items()
            if bool(runner.runtime_status().get("available"))
        }

    def public_catalog(self) -> list[dict[str, object]]:
        catalog: list[dict[str, object]] = []
        for runner_id, runner in sorted(self._runners.items()):
            catalog.append(
                {
                    "runner_id": runner_id,
                    "label": runner.label,
                    **runner.runtime_status(),
                }
            )
        return catalog

    def preflight_snapshot(
        self,
        workflow: Workflow,
        step: WorkflowStep,
        method: MethodOption,
    ) -> list[str]:
        runner = self.get(method.runner_id)
        if runner is None:
            return [f"runner 尚未注册：{method.runner_id}"]
        remote_gpu_available = False
        if step.selected_parameters.get("backend") == "cuda":
            from .slurm_backend import SlurmBackend
            remote_gpu_available = bool(SlurmBackend().status().get("gpu_available"))
        with tempfile.TemporaryDirectory(prefix="localflow-dryrun-") as temporary:
            context = RunnerContext(
                run_id="dry-run",
                workflow=workflow.model_copy(deep=True),
                step=step.model_copy(deep=True),
                method=method.model_copy(deep=True),
                output_directory=Path(temporary),
                cancel_event=Event(),
                log=lambda _message, _progress, _level: None,
                remote_gpu_available=remote_gpu_available,
            )
            return runner.preflight(context)
