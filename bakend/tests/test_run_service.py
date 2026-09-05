from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.capability_registry import CapabilityRegistry
from app.conversation_models import ConversationRecord
from app.dataset_models import DatasetInspection, DatasetRecord
from app.execution import RunnerRegistry, RunConflict, RunService
from app.execution.base import RunnerResult
from app.local_store import LocalStore
from app.run_models import RunArtifact
from app.workflow_models import (
    DryRunReport,
    InputBinding,
    MethodOption,
    Workflow,
    WorkflowStep,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"


class RunServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.dataset_root = root / "dataset"
        (self.dataset_root / "sub-01" / "anat").mkdir(parents=True)
        (self.dataset_root / "dataset_description.json").write_text(
            '{"Name":"test","BIDSVersion":"1.9.0"}',
            encoding="utf-8",
        )
        (self.dataset_root / "sub-01" / "anat" / "sub-01_T1w.nii.gz").write_bytes(
            b"not-a-real-nifti"
        )
        now = datetime.now(timezone.utc).isoformat()
        self.dataset = DatasetRecord(
            dataset_id="dataset_test",
            root_id="root_test",
            relative_path="dataset",
            display_name="测试数据集",
            absolute_path=str(self.dataset_root),
            inspection=DatasetInspection(
                file_count=2,
                total_bytes=20,
                is_bids=True,
                has_t1w=True,
                input_types=["dataset_folder", "bids_anat"],
                features={"has_t1w": True},
                sample_layout="bids",
                sample_count=1,
                scanned_at=now,
            ),
            created_at=now,
            updated_at=now,
        )
        self.store = LocalStore(root / "localflow.db")
        self.store.save_dataset(self.dataset)
        self.capabilities = CapabilityRegistry(SKILLS_DIR)
        self.runners = RunnerRegistry()
        self.service = RunService(
            self.store,
            self.capabilities,
            self.runners,
            root / "outputs",
        )

    def tearDown(self) -> None:
        self.service.shutdown()
        self.temporary.cleanup()

    def test_confirmed_dataset_inspection_executes_and_persists_artifact(self) -> None:
        workflow = self._workflow(execution_enabled=True)
        self.store.save_workflow(workflow, event_type="workflow_confirmed")

        run = self.service.create(workflow.workflow_id, workflow.revision)
        for _ in range(200):
            run = self.service.get(run.run_id)
            if run.status in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.01)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.progress, 100.0)
        self.assertEqual(len(run.artifacts), 1)
        artifact = run.artifacts[0]
        output = Path(artifact.absolute_path)
        self.assertTrue(output.is_file())
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["runner_id"], "dataset.inspect")
        self.assertEqual(report["file_count"], 2)
        self.assertTrue(artifact.sha256)
        events = self.service.events(run.run_id)
        self.assertIn("run_started", {item["event_type"] for item in events})
        self.assertIn("run_succeeded", {item["event_type"] for item in events})

        # Removing a chat that references this workflow must preserve the actual
        # task, audit trail and result file.
        now = datetime.now(timezone.utc).isoformat()
        self.store.create_conversation(ConversationRecord(
            conversation_id="conv_delete_test", title="可删除对话", created_at=now, updated_at=now,
        ))
        self.store.append_conversation_message(
            "conv_delete_test", role="assistant", content="巡检完成", estimated_tokens=5,
            metadata={"workflow_id": workflow.workflow_id}, created_at=now,
        )
        self.store.update_conversation("conv_delete_test", archived=True, updated_at=now)
        self.assertTrue(self.store.delete_archived_conversation("conv_delete_test"))
        self.assertIsNotNone(self.store.get_workflow(workflow.workflow_id))
        self.assertEqual(self.service.get(run.run_id).status, "succeeded")
        self.assertTrue(self.service.events(run.run_id))
        self.assertTrue(output.is_file())

    def test_run_rejects_manifest_only_workflow(self) -> None:
        workflow = self._workflow(execution_enabled=False)
        self.store.save_workflow(workflow, event_type="workflow_confirmed")
        with self.assertRaisesRegex(RunConflict, "尚未接入实际执行器"):
            self.service.create(workflow.workflow_id, workflow.revision)

    def test_freesurfer_recipe_expands_and_binds_runner_artifacts(self) -> None:
        calls: list[tuple[str, str | None]] = []

        class FakeFreeSurferRunner:
            runner_id = "freesurfer.recon_all"
            label = "Fake FreeSurfer"

            @staticmethod
            def runtime_status() -> dict[str, object]:
                return {"available": True, "reason": "test"}

            @staticmethod
            def preflight(_context) -> list[str]:
                return []

            @staticmethod
            def run(context) -> RunnerResult:
                stage = str(context.step.selected_parameters["processing_stage"])
                subject_binding = context.step.input_bindings.get("subject")
                if subject_binding is None:
                    subject = context.output_directory / "subject-test"
                    subject.mkdir(parents=True, exist_ok=True)
                    source = None
                else:
                    subject = Path(str(subject_binding.absolute_path))
                    source = str(subject)
                (subject / f"{stage}.done").write_text("ok", encoding="utf-8")
                calls.append((stage, source))
                return RunnerResult(
                    artifacts=[
                        RunArtifact(
                            artifact_id=f"artifact_{stage}",
                            step_id=context.step.id,
                            artifact_type="freesurfer_subject",
                            label=f"FreeSurfer {stage}",
                            absolute_path=str(subject),
                            relative_path=subject.name,
                            media_type="inode/directory",
                            metadata={"output_slot_id": "subject"},
                        )
                    ],
                    message=f"{stage} complete",
                )

        self.runners._runners["freesurfer.recon_all"] = FakeFreeSurferRunner()
        definition = next(
            item
            for item in self.capabilities.selectable_methods_for("skill.freesurfer-tool")
            if item.method_id
            == "freesurfer-tool-guided--fast-subcortical-basic-surfaces"
        )
        self.assertEqual(definition.execution_mode, "runner")
        self.assertIsNotNone(definition.execution_recipe)
        method = MethodOption(
            id=definition.method_id,
            skill_id=definition.skill_id,
            label=definition.label,
            description=definition.description,
            runner_id=definition.runner_id,
            execution_mode=definition.execution_mode,
            input_types=definition.input_types,
            output_types=definition.output_types,
            parameters=definition.parameters,
            input_slots=definition.input_slots,
            output_slots=definition.output_slots,
            structure_level=definition.structure_level,
            execution_recipe=definition.execution_recipe,
        )
        t1w = self.dataset_root / "sub-01" / "anat" / "sub-01_T1w.nii.gz"
        now = datetime.now(timezone.utc).isoformat()
        workflow = Workflow(
            workflow_id="workflow_freesurfer_recipe",
            template_id="dynamic:skill.freesurfer-tool",
            revision=1,
            title="FreeSurfer 分阶段执行",
            summary="连续运行三个受信任 Runner 阶段",
            original_request="运行 FreeSurfer autorecon1/2/3",
            status="confirmed",
            dataset_id=self.dataset.dataset_id,
            dataset=self.dataset,
            planner_source="test",
            execution_mode="runner",
            plan_kind="atomic",
            requested_capabilities=["skill.freesurfer-tool"],
            steps=[
                WorkflowStep(
                    id="skill_freesurfer_tool",
                    order=1,
                    title="FreeSurfer",
                    description="分阶段",
                    selection="user",
                    status="confirmed",
                    capability="skill.freesurfer-tool",
                    method_options=[method],
                    selected_method_id=method.id,
                    selected_parameters={"threads": 2},
                    input_bindings={
                        "t1w": InputBinding(
                            slot_id="t1w",
                            artifact_type="t1w_image",
                            source="existing_path",
                            label="T1w",
                            absolute_path=str(t1w),
                            status="validated",
                        )
                    },
                )
            ],
            dry_run_report=DryRunReport(
                valid=True,
                execution_enabled=True,
                dataset_path_validated=True,
                checked_at=now,
            ),
            confirmed_at=now,
            created_at=now,
            updated_at=now,
        )
        self.store.save_workflow(workflow, event_type="workflow_confirmed")

        run = self.service.create(workflow.workflow_id, workflow.revision)
        for _ in range(200):
            run = self.service.get(run.run_id)
            if run.status in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.01)

        self.assertEqual(run.status, "succeeded", run.error_message)
        self.assertEqual(
            [step.step_id for step in run.steps],
            [
                "skill_freesurfer_tool__autorecon1",
                "skill_freesurfer_tool__autorecon2",
                "skill_freesurfer_tool__autorecon3",
            ],
        )
        self.assertEqual([stage for stage, _source in calls], ["autorecon1", "autorecon2", "autorecon3"])
        self.assertIsNone(calls[0][1])
        self.assertEqual(calls[1][1], calls[2][1])
        self.assertTrue(Path(str(calls[1][1])).is_dir())

    def _workflow(self, *, execution_enabled: bool) -> Workflow:
        definition = self.capabilities.methods_for("dwi.inspect")[0]
        method = MethodOption(
            id=definition.method_id,
            skill_id=definition.skill_id,
            label=definition.label,
            description=definition.description,
            runner_id=definition.runner_id,
            execution_mode=definition.execution_mode,
            input_types=definition.input_types,
            output_types=definition.output_types,
            parameters=definition.parameters,
            input_slots=definition.input_slots,
            output_slots=definition.output_slots,
            structure_level=definition.structure_level,
        )
        parameters = {
            item.id: item.default
            for item in method.parameters
            if item.default is not None
        }
        now = datetime.now(timezone.utc).isoformat()
        return Workflow(
            workflow_id=f"workflow_{'enabled' if execution_enabled else 'disabled'}",
            template_id="dynamic:dwi.inspect",
            revision=1,
            title="数据集巡检",
            summary="执行真实的数据集结构与元数据巡检",
            original_request="检查这个数据集",
            status="confirmed",
            dataset_id=self.dataset.dataset_id,
            dataset=self.dataset,
            planner_source="test",
            execution_mode="runner",
            plan_kind="atomic",
            requested_capabilities=["dwi.inspect"],
            steps=[
                WorkflowStep(
                    id="dwi_inspect",
                    order=1,
                    title="数据集巡检",
                    description="生成数据集巡检报告",
                    selection="auto",
                    status="confirmed",
                    capability="dwi.inspect",
                    method_options=[method],
                    selected_method_id=method.id,
                    selected_parameters=parameters,
                )
            ],
            dry_run_report=DryRunReport(
                valid=True,
                execution_enabled=execution_enabled,
                dataset_path_validated=True,
                checked_at=now,
            ),
            confirmed_at=now,
            created_at=now,
            updated_at=now,
        )
