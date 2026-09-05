from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..base import RunnerContext, RunnerResult
from ..external_command import ExternalCommandRunner


class MrtrixTckgenRunner(ExternalCommandRunner):
    runner_id = "mrtrix.tckgen"
    label = "MRtrix3 纤维追踪"

    def __init__(self) -> None:
        root = Path(os.getenv("LOCALFLOW_MRTRIX_ROOT", "/opt/software/mrtrix3-master"))
        self.executable = root / "bin" / "tckgen"
        self.sift2_executable = root / "bin" / "tcksift2"
        self.mrstats_executable = root / "bin" / "mrstats"

    def runtime_status(self) -> dict[str, object]:
        status = super().runtime_status()
        libpng = Path(
            os.getenv(
                "LOCALFLOW_MRTRIX_LIBPNG",
                "/lib/x86_64-linux-gnu/libpng16.so.16",
            )
        )
        if status["available"] and not libpng.is_file():
            status.update(available=False, reason=f"缺少 MRtrix 运行库：{libpng}")
        status["optional_sift2"] = str(self.sift2_executable)
        status["libpng"] = str(libpng)
        if status["available"] and not self.mrstats_executable.is_file():
            status.update(available=False, reason=f"缺少 FOD 检查工具：{self.mrstats_executable}")
        return status

    def allowed_executables(self) -> set[Path]:
        return {self.executable, self.sift2_executable}

    def preflight(self, context: RunnerContext) -> list[str]:
        problems = self.common_preflight(context)
        if context.step.input_bindings.get("fod") is None:
            problems.append("缺少必需的 FOD 影像")
        else:
            try:
                fod = self.required_binding(context, "fod")
                checked = subprocess.run(  # noqa: S603 - fixed reviewed executable and argv
                    [str(self.mrstats_executable), str(fod), "-output", "max"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    timeout=90,
                    check=False,
                    env={**os.environ, **self._environment()},
                )
                maxima = [float(token) for token in checked.stdout.split()]
                if checked.returncode != 0 or not maxima:
                    problems.append("无法读取 FOD 数值统计，请检查文件格式")
                elif max(maxima) <= 0:
                    problems.append("FOD 所有系数均为 0，不能用于纤维追踪")
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                problems.append(f"FOD 内容检查失败：{exc}")
        if bool(self.parameter(context, "act_enabled", True)) and context.step.input_bindings.get("five_tt") is None:
            problems.append("启用 ACT 时必须绑定 5TT 影像")
        if self.parameter(context, "seeding_strategy", "dynamic") == "roi" and context.step.input_bindings.get("seed_roi") is None:
            problems.append("选择 ROI 播种时必须绑定种子 ROI")
        if self.parameter(context, "postprocessing", "none") == "sift2":
            if not self.sift2_executable.is_file() or not os.access(self.sift2_executable, os.X_OK):
                problems.append(f"SIFT2 可执行文件不可用：{self.sift2_executable}")
        return problems

    @staticmethod
    def _environment() -> dict[str, str]:
        # Do not prepend the FSL library folder here: its libstdc++/libgcc may
        # override the system ABI used to build MRtrix and can cause SIGSEGV.
        root = Path(os.getenv("LOCALFLOW_MRTRIX_ROOT", "/opt/software/mrtrix3-master"))
        return {
            "PATH": str(root / "bin") + os.pathsep + os.getenv("PATH", ""),
            "LD_LIBRARY_PATH": os.getenv("LD_LIBRARY_PATH", ""),
        }

    def run(self, context: RunnerContext) -> RunnerResult:
        fod = self.required_binding(context, "fod")
        tracks = context.output_directory / "tracks.tck"
        argv = [
            str(self.executable), str(fod), str(tracks),
            "-algorithm", str(self.parameter(context, "algorithm", "iFOD2")),
            "-select", str(int(self.parameter(context, "streamline_count", 10000))),
            "-nthreads", str(int(self.parameter(context, "threads", 4))),
            "-minlength", str(float(self.parameter(context, "min_length", 5))),
            "-maxlength", str(float(self.parameter(context, "max_length", 250))),
            "-cutoff", str(float(self.parameter(context, "cutoff", 0.06))),
            "-force",
        ]
        angle = self.parameter(context, "max_angle", 45)
        if angle is not None:
            argv.extend(("-angle", str(float(angle))))
        step_size = self.parameter(context, "step_size", 0)
        if step_size and float(step_size) > 0:
            argv.extend(("-step", str(float(step_size))))
        seed_strategy = str(self.parameter(context, "seeding_strategy", "dynamic"))
        if seed_strategy == "roi":
            argv.extend(("-seed_image", str(self.required_binding(context, "seed_roi"))))
        else:
            argv.extend(("-seed_dynamic", str(fod)))
        five_tt = self.optional_binding(context, "five_tt")
        if bool(self.parameter(context, "act_enabled", True)):
            assert five_tt is not None
            argv.extend(("-act", str(five_tt)))
            if bool(self.parameter(context, "backtrack", True)):
                argv.append("-backtrack")
            if bool(self.parameter(context, "crop_at_gmwmi", True)):
                argv.append("-crop_at_gmwmi")
        self.execute(context, argv, environment=self._environment(), progress_end=85.0)
        artifacts = [
            self.artifact(context, tracks, "tractogram", "MRtrix3 纤维流线", metadata={"algorithm": self.parameter(context, "algorithm", "iFOD2")})
        ]
        if self.parameter(context, "postprocessing", "none") == "sift2":
            weights = context.output_directory / "sift2_weights.txt"
            sift_argv = [
                str(self.sift2_executable), str(tracks), str(fod), str(weights),
                "-nthreads", str(int(self.parameter(context, "threads", 4))), "-force",
            ]
            if five_tt is not None:
                sift_argv.extend(("-act", str(five_tt)))
            self.execute(context, sift_argv, environment=self._environment(), progress_start=86.0, progress_end=96.0)
            artifacts.append(self.artifact(context, weights, "streamline_weights", "SIFT2 流线权重", "text/plain"))
        context.log("纤维追踪输出已完成完整性校验", 100.0, "info")
        return RunnerResult(artifacts=artifacts, message=f"纤维追踪完成，生成 {len(artifacts)} 个制品。")
