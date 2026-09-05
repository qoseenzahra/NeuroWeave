from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from ..base import RunnerContext, RunnerResult
from ..external_command import ExternalCommandRunner


class FreeSurferReconAllRunner(ExternalCommandRunner):
    runner_id = "freesurfer.recon_all"
    label = "FreeSurfer recon-all"

    def __init__(self) -> None:
        self.home = Path(
            os.getenv(
                "LOCALFLOW_FREESURFER_HOME",
                "/opt/software/freesurfer-7.4.1/usr/local/freesurfer/7.4.1",
            )
        )
        self.executable = self.home / "bin" / "recon-all"
        self.license_file = Path(os.getenv("LOCALFLOW_FREESURFER_LICENSE", str(self.home / "license.txt")))
        self.tcsh = Path("/bin/tcsh")
        self.csh = Path("/bin/csh")
        self.bc = Path(os.getenv("LOCALFLOW_FREESURFER_BC", "/usr/bin/bc"))
        self.libgomp = Path(
            os.getenv(
                "LOCALFLOW_FREESURFER_LIBGOMP",
                "/lib/x86_64-linux-gnu/libgomp.so.1",
            )
        )
        self.libquadmath = Path(
            os.getenv(
                "LOCALFLOW_FREESURFER_LIBQUADMATH",
                "/lib/x86_64-linux-gnu/libquadmath.so.0",
            )
        )
        self.update_needed = self.home / "bin" / "UpdateNeeded"
        self.nu_correct = self.home / "mni" / "bin" / "nu_correct"
        self.gauss_4dfp = self.home / "bin" / "gauss_4dfp"
        self.mni_lib = self.home / "mni" / "lib"

    def runtime_status(self) -> dict[str, object]:
        status = super().runtime_status()
        required_files = {
            "license": self.license_file,
            "tcsh": self.tcsh,
            "csh": self.csh,
            "bc": self.bc,
            "libgomp": self.libgomp,
            "libquadmath": self.libquadmath,
            "SetUpFreeSurfer.sh": self.home / "SetUpFreeSurfer.sh",
            "FreeSurferEnv.sh": self.home / "FreeSurferEnv.sh",
            "UpdateNeeded": self.update_needed,
            "nu_correct": self.nu_correct,
            "gauss_4dfp": self.gauss_4dfp,
        }
        missing = [f"{label}={path}" for label, path in required_files.items() if not path.is_file()]
        for command in ("bash", "perl", "awk", "sed", "grep", "find", "hostname"):
            if shutil.which(command) is None:
                missing.append(f"system-command={command}")
        if not self.mni_lib.is_dir():
            missing.append(f"MINC_LIB_DIR={self.mni_lib}")
        if missing:
            status.update(available=False, reason="缺少 FreeSurfer 运行依赖：" + "、".join(missing))
        status["freesurfer_home"] = str(self.home)
        status["license"] = str(self.license_file)
        status["bc"] = str(self.bc)
        status["libgomp"] = str(self.libgomp)
        status["libquadmath"] = str(self.libquadmath)
        status["nu_correct"] = str(self.nu_correct)
        status["update_needed"] = str(self.update_needed)
        status["gauss_4dfp"] = str(self.gauss_4dfp)
        status["environment_profile"] = "freesurfer-7.4.1-complete"
        return status

    def execution_environment(self, subjects_dir: Path) -> dict[str, str]:
        """Build the non-interactive equivalent of SetUpFreeSurfer.sh.

        Calling ``recon-all`` with only ``FREESURFER_HOME/bin`` on PATH is not
        sufficient: recon-all delegates to MINC, FS-FAST and other bundled
        helpers.  We reproduce the variables established by FreeSurferEnv.sh
        without sourcing a user-controlled shell file at task execution time.
        """

        fsfast_home = self.home / "fsfast"
        mni_dir = self.home / "mni"
        minc_bin = mni_dir / "bin"
        fsl_dir = Path(os.getenv("LOCALFLOW_FSL_ROOT", "/opt/software/fsl"))
        path_parts = [
            self.home / "bin",
            fsfast_home / "bin",
            self.home / "tktools",
        ]
        if (fsl_dir / "bin").is_dir():
            path_parts.append(fsl_dir / "bin")
        path_parts.append(minc_bin)

        previous_path = os.getenv("PATH", "")
        path_value = os.pathsep.join(str(path) for path in path_parts)
        if previous_path:
            path_value += os.pathsep + previous_path

        environment = {
            "FREESURFER_HOME": str(self.home),
            "FREESURFER": str(self.home),
            "FS_LICENSE": str(self.license_file),
            "SUBJECTS_DIR": str(subjects_dir),
            "FUNCTIONALS_DIR": str(self.home / "sessions"),
            "FSFAST_HOME": str(fsfast_home),
            "FMRI_ANALYSIS_DIR": str(fsfast_home),
            "LOCAL_DIR": str(self.home / "local"),
            "MINC_BIN_DIR": str(minc_bin),
            "MINC_LIB_DIR": str(self.mni_lib),
            "MNI_DIR": str(mni_dir),
            "MNI_DATAPATH": str(mni_dir / "data"),
            "FSF_OUTPUT_FORMAT": "nii.gz",
            "FSLOUTPUTTYPE": "NIFTI_GZ",
            "FSLDIR": str(fsl_dir),
            "FSL_DIR": str(fsl_dir),
            "FSL_BIN": str(fsl_dir / "bin"),
            "FS_OVERRIDE": "0",
            "FS_FREESURFERENV_NO_OUTPUT": "1",
            "PATH": path_value,
        }
        mni_perl = mni_dir / "share" / "perl5"
        if mni_perl.is_dir():
            previous_perl = os.getenv("PERL5LIB", "")
            environment["MNI_PERL5LIB"] = str(mni_perl)
            environment["PERL5LIB"] = str(mni_perl) + (
                os.pathsep + previous_perl if previous_perl else ""
            )
        misc_lib = self.home / "lib" / "misc" / "lib"
        if misc_lib.is_dir():
            previous_ld = os.getenv("LD_LIBRARY_PATH", "")
            environment["MISC_LIB"] = str(misc_lib)
            environment["LD_LIBRARY_PATH"] = str(misc_lib) + (
                os.pathsep + previous_ld if previous_ld else ""
            )
        return environment

    def preflight(self, context: RunnerContext) -> list[str]:
        problems = self.common_preflight(context)
        stage = str(self.parameter(context, "processing_stage", "all"))
        if stage in {"all", "autorecon1"}:
            if context.step.input_bindings.get("t1w") is None:
                problems.append("该处理阶段缺少 T1w 输入")
        elif context.step.input_bindings.get("subject") is None:
            problems.append("续跑阶段缺少已有 FreeSurfer 受试者目录")
        if bool(self.parameter(context, "use_t2", False)) and context.step.input_bindings.get("t2w") is None:
            problems.append("启用 T2 辅助时必须绑定 T2w 输入")
        if bool(self.parameter(context, "use_flair", False)) and context.step.input_bindings.get("flair") is None:
            problems.append("启用 FLAIR 辅助时必须绑定 FLAIR 输入")
        return problems

    def run(self, context: RunnerContext) -> RunnerResult:
        stage = str(self.parameter(context, "processing_stage", "all"))
        stage_flags = {
            "autorecon1": "-autorecon1",
            "autorecon2": "-autorecon2",
            "autorecon3": "-autorecon3",
            "stats": "-stats",
            "all": "-all",
        }
        stage_flag = stage_flags.get(stage)
        if stage_flag is None:
            raise RuntimeError(f"不支持的 FreeSurfer 处理阶段：{stage}")

        if stage in {"all", "autorecon1"}:
            raw_subject = (
                context.workflow.dataset.display_name
                if context.workflow.dataset
                else context.run_id
            )
            subject_id = (
                re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_subject).strip("._-")[:80]
                or context.run_id
            )
            subjects_dir = context.output_directory
            subject_dir = subjects_dir / subject_id
            argv = [
                str(self.executable),
                "-sd",
                str(subjects_dir),
                "-s",
                subject_id,
                "-i",
                str(self.required_binding(context, "t1w")),
                stage_flag,
            ]
        else:
            subject_dir = self.required_binding(context, "subject")
            if not subject_dir.is_dir():
                raise RuntimeError(f"FreeSurfer 受试者目录不存在：{subject_dir}")
            subject_id = subject_dir.name
            subjects_dir = subject_dir.parent
            argv = [
                str(self.executable),
                "-sd",
                str(subjects_dir),
                "-s",
                subject_id,
                stage_flag,
            ]
        threads = int(self.parameter(context, "threads", 4))
        if threads > 1:
            argv.extend(("-parallel", "-openmp", str(threads)))
        if bool(self.parameter(context, "use_t2", False)):
            argv.extend(("-T2", str(self.required_binding(context, "t2w")), "-T2pial"))
        if bool(self.parameter(context, "use_flair", False)):
            argv.extend(("-FLAIR", str(self.required_binding(context, "flair")), "-FLAIRpial"))
        environment = self.execution_environment(subjects_dir)
        self.execute(context, argv, environment=environment, progress_end=96.0)
        expected_by_stage = {
            "autorecon1": subject_dir / "mri" / "T1.mgz",
            "autorecon2": subject_dir / "surf" / "lh.white",
            "autorecon3": subject_dir / "stats" / "lh.aparc.stats",
            "stats": subject_dir / "stats" / "aseg.stats",
            "all": subject_dir / "mri" / "aseg.mgz",
        }
        expected = expected_by_stage[stage]
        if not expected.is_file() or expected.stat().st_size == 0:
            raise RuntimeError(f"FreeSurfer 未生成预期输出：{expected}")
        artifact = self.directory_artifact(
            context,
            subject_dir,
            "freesurfer_subject",
            "FreeSurfer SUBJECTS_DIR 结果",
            {
                "subject_id": subject_id,
                "processing_stage": stage,
                "output_slot_id": "subject",
            },
        )
        context.log("FreeSurfer 输出目录已通过关键文件检查", 100.0, "info")
        return RunnerResult(artifacts=[artifact], message=f"FreeSurfer {stage} 完成：{subject_id}")
