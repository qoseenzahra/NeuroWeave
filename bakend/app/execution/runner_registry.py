from __future__ import annotations

import tempfile
from pathlib import Path
from threading import Event

from ..operation_context import checkpoint, current_operation
from ..workflow_models import MethodOption, Workflow, WorkflowStep
from ..parameter_rules import effective_parameters
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
from .runners.mrtrix_commands import command_runners
from .runners.scientific_commands import scientific_runners
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
        runners.extend(command_runners())
        runners.extend(scientific_runners())
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
        groups = [binding for binding in step.input_bindings.values()
                  if binding.source != "upstream_output" and binding.binding_mode == "per_sample"]
        if groups:
            identifiers = [match.sample_id for match in groups[0].sample_matches]
            if not identifiers or len(set(identifiers)) != len(identifiers):
                return ["多样本输入为空或含有重复样本"]
            expected = set(identifiers)
            if any({match.sample_id for match in binding.sample_matches} != expected
                   or len(binding.sample_matches) != len(identifiers)
                   or any(match.status != "matched" or not match.absolute_path for match in binding.sample_matches)
                   for binding in groups):
                return ["多样本输入覆盖不一致，或仍有缺失文件"]
            problems = []
            for sample_id in identifiers:
                checkpoint(f"检查样本：{sample_id}")
                sample_step = step.model_copy(deep=True)
                for binding in sample_step.input_bindings.values():
                    if binding.source == "upstream_output" or binding.binding_mode != "per_sample":
                        continue
                    match = next(item for item in binding.sample_matches if item.sample_id == sample_id)
                    binding.absolute_path = match.absolute_path
                    from ..historical_inputs import select_history_sample
                    select_history_sample(binding, sample_id)
                    binding.binding_mode = "single"
                    binding.sample_matches = []
                problems.extend(f"样本 {sample_id}：{problem}"
                                for problem in self.preflight_snapshot(workflow, sample_step, method))
            return problems
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
                cancel_event=current_operation.get().cancel_event if current_operation.get() else Event(),
                log=lambda _message, _progress, _level: None,
                remote_gpu_available=remote_gpu_available,
                is_dry_run=True,
            )
            context.step.selected_parameters = effective_parameters(context.method, step.selected_parameters)
            try:
                from ..historical_inputs import historical_binding_problems
                history_problems = [problem for binding in context.step.input_bindings.values()
                                    for problem in historical_binding_problems(binding)]
                return history_problems + runner.preflight(context)
            except (RuntimeError, ValueError, OSError) as exc:
                return [f"输入或运行环境检查失败：{exc}"]
