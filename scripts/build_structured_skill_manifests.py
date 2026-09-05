"""Generate planning manifests for every LocalFlow/NeuroClaw Skill.

Planning manifests make a Skill available as a typed Workflow step with bounded
parameters. They intentionally do not declare an executable runner. Reviewed
tool.manifest.json files remain the only source of runner-backed methods.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "bakend"
SKILLS_DIR = PROJECT_ROOT / "skills"
SUMMARIES_FILE = BACKEND_ROOT / "resources" / "neuroclaw_skill_summaries.json"

sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app.skill_loader import Skill, SkillLoader  # noqa: E402
from build_capability_tree import GROUPS, LABEL_OVERRIDES  # noqa: E402


def _options(*items: tuple[Any, str]) -> list[dict[str, Any]]:
    return [{"value": value, "label": label} for value, label in items]


def _parameter(
    parameter_id: str,
    label: str,
    description: str,
    value_type: str,
    default: Any,
    options: list[dict[str, Any]] | None = None,
    *,
    control: str = "auto",
    level: str = "basic",
    group: str = "常用参数",
    required: bool = True,
    unit: str = "",
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
    placeholder: str = "",
    visible_when: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": parameter_id,
        "argument": parameter_id.replace("_", "-"),
        "label": label,
        "description": description,
        "type": value_type,
        "control": control,
        "level": level,
        "group": group,
        "unit": unit,
        "required": required,
        "default": default,
        "options": options or [],
        "minimum": minimum,
        "maximum": maximum,
        "step": step,
        "placeholder": placeholder,
        "visible_when": visible_when or {},
    }


PROFILE_PARAMETERS: dict[str, list[dict[str, Any]]] = {
    "dataset-workflows": [
        _parameter(
            "processing_scope",
            "处理范围",
            "选择单个受试者、小批量或完整数据集；这里只记录规划约束。",
            "string",
            "single_subject",
            _options(
                ("single_subject", "单个受试者"),
                ("selected_cohort", "选定队列"),
                ("full_dataset", "完整数据集"),
            ),
        ),
        _parameter(
            "validation_level",
            "验证级别",
            "严格验证会要求更完整的输入、元数据和质量控制检查。",
            "string",
            "strict",
            _options(("basic", "基础检查"), ("strict", "严格检查")),
        ),
    ],
    "modality-workflows": [
        _parameter(
            "workflow_scope",
            "工作流范围",
            "选择只做预处理、提取特征或规划端到端模态流程。",
            "string",
            "end_to_end",
            _options(
                ("preprocess", "仅预处理"),
                ("features", "特征提取"),
                ("end_to_end", "端到端流程"),
            ),
        ),
        _parameter(
            "quality_control",
            "包含质量控制",
            "在流程方案中保留输入检查、中间 QC 和结果核验步骤。",
            "boolean",
            True,
            _options((True, "包含"), (False, "不包含")),
        ),
    ],
    "data-preparation": [
        _parameter(
            "output_policy",
            "输出策略",
            "规划阶段默认保留原始数据，并把结果写入新目录。",
            "string",
            "new_output",
            _options(
                ("preview_only", "只预览变更"),
                ("copy_then_modify", "复制后处理"),
                ("new_output", "写入新输出目录"),
            ),
        ),
        _parameter(
            "validation_level",
            "输出验证",
            "选择基础结构检查或包含模式、计数和元数据的严格验证。",
            "string",
            "strict",
            _options(("basic", "基础验证"), ("strict", "严格验证")),
        ),
    ],
    "neuroimaging-tools": [
        _parameter(
            "processing_level",
            "处理级别",
            "控制方案中启用的步骤深度，不会直接启动对应软件。",
            "string",
            "standard",
            _options(
                ("minimal", "最小必要步骤"),
                ("standard", "标准流程"),
                ("advanced", "高级选项"),
            ),
        ),
        _parameter(
            "quality_control",
            "包含质量控制",
            "要求规划结果包含工具输出的质量检查。",
            "boolean",
            True,
            _options((True, "包含"), (False, "不包含")),
        ),
    ],
    "models-analysis": [
        _parameter(
            "evaluation_scope",
            "评估范围",
            "选择单次划分、交叉验证或多方法基准比较。",
            "string",
            "cross_validation",
            _options(
                ("single_split", "单次划分"),
                ("cross_validation", "交叉验证"),
                ("benchmark", "基准比较"),
            ),
        ),
        _parameter(
            "reproducibility",
            "记录复现信息",
            "保留随机种子、数据划分、依赖和参数快照。",
            "boolean",
            True,
            _options((True, "记录"), (False, "不记录")),
        ),
    ],
    "research-lifecycle": [
        _parameter(
            "output_detail",
            "输出详细程度",
            "控制科研产出的层次与解释深度。",
            "string",
            "standard",
            _options(
                ("outline", "提纲"),
                ("standard", "标准"),
                ("detailed", "详细"),
            ),
        ),
        _parameter(
            "evidence_trace",
            "保留依据追踪",
            "要求方案区分已提供证据、外部来源和模型推断。",
            "boolean",
            True,
            _options((True, "保留"), (False, "不保留")),
        ),
    ],
    "local-infrastructure": [
        _parameter(
            "change_policy",
            "变更策略",
            "当前平台只支持检查、方案和验证型 Dry-run，不执行系统修改。",
            "string",
            "plan_only",
            _options(
                ("inspection_only", "仅检查"),
                ("plan_only", "只生成方案"),
                ("validated_dry_run", "验证型 Dry-run"),
            ),
        ),
        _parameter(
            "preserve_existing",
            "保留现有状态",
            "要求方案默认不覆盖已有环境、文件或版本状态。",
            "boolean",
            True,
            _options((True, "保留"), (False, "允许替换方案")),
        ),
    ],
}


PROFILE_ADVANCED_PARAMETERS: dict[str, list[dict[str, Any]]] = {
    "dataset-workflows": [
        _parameter(
            "missing_data_policy", "缺失数据策略", "遇到缺失模态或表型时采用的处理策略。",
            "string", "report", _options(("report", "报告并继续"), ("exclude", "排除不完整样本"), ("stop", "停止并等待处理")),
            level="advanced", group="样本与完整性",
        ),
        _parameter(
            "subject_filter", "受试者筛选表达式", "可选的受试者、诊断或队列筛选条件；留空表示不额外筛选。",
            "string", "", control="text", level="advanced", group="样本与完整性", required=False,
            placeholder="例如：group == 'control'",
        ),
        _parameter(
            "verify_checksums", "校验文件完整性", "在方案中加入校验和或文件完整性检查。",
            "boolean", False, _options((True, "校验"), (False, "不校验")),
            level="advanced", group="验证与资源",
        ),
        _parameter(
            "parallel_jobs", "并行任务数", "规划批量处理时允许的最大并行任务数。",
            "integer", 1, control="number", level="advanced", group="验证与资源",
            minimum=1, maximum=128, step=1,
        ),
    ],
    "modality-workflows": [
        _parameter(
            "artifact_strategy", "伪影处理策略", "选择保守标记、自动校正或排除受影响数据。",
            "string", "correct", _options(("flag", "仅标记"), ("correct", "自动校正"), ("exclude", "排除受影响数据")),
            level="advanced", group="预处理细节",
        ),
        _parameter(
            "normalization_space", "标准空间", "规划空间标准化目标；原生空间不会应用模板归一化。",
            "string", "native", _options(("native", "原生空间"), ("template", "标准模板空间"), ("both", "同时保留")),
            level="advanced", group="空间与输出",
        ),
        _parameter(
            "smoothing_extent", "平滑尺度", "按模态解释为空间或时间平滑尺度；0 表示关闭。",
            "number", 0, control="number", level="advanced", group="空间与输出",
            minimum=0, maximum=20, step=0.5,
        ),
        _parameter(
            "compute_threads", "计算线程数", "为支持并行的软件规划线程数量。",
            "integer", 4, control="number", level="advanced", group="计算资源",
            minimum=1, maximum=128, step=1,
        ),
    ],
    "data-preparation": [
        _parameter(
            "metadata_policy", "元数据处理", "控制缺失或冲突元数据的处理方式。",
            "string", "preserve_and_report", _options(("preserve_and_report", "保留并报告"), ("normalize", "规范化字段"), ("strict", "严格拒绝冲突")),
            level="advanced", group="结构与元数据",
        ),
        _parameter(
            "naming_template", "命名模板", "可选的输出文件或实体命名模板。",
            "string", "", control="text", level="advanced", group="结构与元数据", required=False,
            placeholder="例如：sub-{subject}_ses-{session}",
        ),
        _parameter(
            "collision_policy", "命名冲突策略", "目标位置已经存在同名文件时的处理方式。",
            "string", "stop", _options(("stop", "停止并报告"), ("rename", "自动追加编号"), ("replace_copy", "替换输出副本")),
            level="advanced", group="安全策略",
        ),
        _parameter(
            "worker_count", "并行处理数", "批量转换或清洗时允许的并行任务数量。",
            "integer", 2, control="number", level="advanced", group="性能",
            minimum=1, maximum=64, step=1,
        ),
    ],
    "neuroimaging-tools": [
        _parameter(
            "resource_profile", "资源配置", "选择偏向低内存、平衡或高性能的工具运行方案。",
            "string", "balanced", _options(("conservative", "低资源"), ("balanced", "平衡"), ("performance", "高性能")),
            level="advanced", group="计算资源",
        ),
        _parameter(
            "threads", "线程数", "工具支持时使用的 CPU 线程数量。",
            "integer", 4, control="number", level="advanced", group="计算资源",
            minimum=1, maximum=128, step=1,
        ),
        _parameter(
            "memory_limit_gb", "内存上限", "规划任务可使用的内存上限。",
            "number", 8, control="number", level="advanced", group="计算资源", unit="GB",
            minimum=1, maximum=1024, step=1,
        ),
        _parameter(
            "keep_intermediates", "保留中间文件", "保留关键中间结果以便复核和断点恢复。",
            "boolean", False, _options((True, "保留"), (False, "不保留")),
            level="advanced", group="输出与复现",
        ),
    ],
    "models-analysis": [
        _parameter(
            "validation_folds", "交叉验证折数", "交叉验证或基准比较使用的折数。",
            "integer", 5, control="number", level="advanced", group="验证设计",
            minimum=2, maximum=20, step=1,
            visible_when={"evaluation_scope": ["cross_validation", "benchmark"]},
        ),
        _parameter(
            "random_seed", "随机种子", "控制数据划分、初始化和可复现实验。",
            "integer", 42, control="number", level="advanced", group="验证设计",
            minimum=0, maximum=2147483647, step=1,
        ),
        _parameter(
            "hyperparameter_search", "超参数搜索", "选择固定参数、网格搜索或贝叶斯搜索。",
            "string", "fixed", _options(("fixed", "固定参数"), ("grid", "网格搜索"), ("bayesian", "贝叶斯搜索")),
            level="advanced", group="模型优化",
        ),
        _parameter(
            "class_balance", "类别不平衡处理", "分类任务中对类别不平衡的处理方式。",
            "string", "none", _options(("none", "不处理"), ("class_weight", "类别权重"), ("resample", "重采样")),
            level="advanced", group="模型优化",
        ),
        _parameter(
            "explainability", "生成解释结果", "在支持时生成特征重要性、显著性或模型解释。",
            "boolean", True, _options((True, "生成"), (False, "不生成")),
            level="advanced", group="输出与解释",
        ),
    ],
    "research-lifecycle": [
        _parameter(
            "output_language", "输出语言", "科研材料与报告的主要输出语言。",
            "string", "zh-CN", _options(("zh-CN", "中文"), ("en", "英文"), ("bilingual", "中英双语")),
            level="advanced", group="表达格式",
        ),
        _parameter(
            "citation_style", "引文格式", "需要引用时采用的默认格式。",
            "string", "apa", _options(("apa", "APA"), ("vancouver", "Vancouver"), ("gbt7714", "GB/T 7714")),
            level="advanced", group="表达格式",
        ),
        _parameter(
            "include_methods_appendix", "包含方法附录", "在产出中附带检索、分析或生成过程的结构化说明。",
            "boolean", True, _options((True, "包含"), (False, "不包含")),
            level="advanced", group="透明度",
        ),
        _parameter(
            "mark_uncertainty", "标注不确定性", "显式标记证据不足、推断内容和待人工核验项。",
            "boolean", True, _options((True, "标注"), (False, "不标注")),
            level="advanced", group="透明度",
        ),
    ],
    "local-infrastructure": [
        _parameter(
            "isolation_mode", "隔离方式", "规划原生环境、Conda 环境或容器隔离。",
            "string", "existing", _options(("existing", "使用现有环境"), ("conda", "Conda 环境"), ("container", "容器")),
            level="advanced", group="环境隔离",
        ),
        _parameter(
            "rollback_plan", "生成回滚方案", "对可能改变环境或文件状态的步骤生成回滚说明。",
            "boolean", True, _options((True, "生成"), (False, "不生成")),
            level="advanced", group="安全与审计",
        ),
        _parameter(
            "log_level", "日志级别", "控制规划中建议保留的日志详细程度。",
            "string", "info", _options(("warning", "仅警告"), ("info", "标准"), ("debug", "调试")),
            level="advanced", group="安全与审计",
        ),
        _parameter(
            "timeout_minutes", "步骤超时", "单个外部软件或命令步骤的计划超时时间。",
            "integer", 60, control="number", level="advanced", group="执行限制", unit="分钟",
            minimum=1, maximum=10080, step=1,
        ),
    ],
}


def _skill_sections() -> dict[str, str]:
    return {
        skill_id: str(section["id"])
        for section in GROUPS
        for group in section["groups"]
        for skill_id in group["skills"]
    }


def _description(skill: Skill) -> str:
    value = skill.summary_zh or skill.summary_en or skill.description
    return re.sub(r"\s+", " ", value).strip()[:360]


def _clean_markdown(value: str) -> str:
    value = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[`*_~]", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _table_cells(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [_clean_markdown(cell) for cell in stripped.split("|")]


CURATED_OPERATION_OPTIONS: dict[str, list[tuple[str, str, str]]] = {
    "dataset-inspector": [
        ("directory_inventory", "目录与格式盘点", "统计目录层级、文件类型、数量和体积。"),
        ("table_schema", "表格模式检查", "检查字段、类型、缺失率与主键候选。"),
        ("imaging_metadata", "影像元数据检查", "只读取必要头信息并汇总空间、维度和格式。"),
        ("quality_findings", "质量问题汇总", "输出异常、缺失输入和后续处理建议。"),
    ],
    "harness-core": [
        ("self_verification", "自验证", "为调用方加入结果与不变量检查。"),
        ("checkpoint", "检查点管理", "保存和恢复长任务的阶段状态。"),
        ("drift_detection", "漂移检测", "对配置、数据或输出变化进行比较。"),
        ("audit_logging", "审计日志", "记录调用、参数、结果与失败信息。"),
    ],
    "image-batch-processing": [
        ("format_conversion", "批量格式转换", "按输入输出映射转换影像格式。"),
        ("batch_preprocessing", "批量预处理", "先验证单样本，再扩展到全部样本。"),
        ("spatial_validation", "空间信息检查", "检查方向、体素大小、维度和参考空间。"),
        ("failure_manifest", "失败清单与质量控制", "保存成功、跳过和失败样本清单。"),
    ],
    "multi-search-engine": [
        ("general_search", "多引擎通用检索", "组合中文与全球搜索引擎。"),
        ("site_search", "站点限定检索", "限定域名或站点执行检索。"),
        ("time_filtered_search", "时间范围检索", "按时间窗口筛选结果。"),
        ("knowledge_query", "知识与计算查询", "路由到适合事实或计算问题的引擎。"),
    ],
    "report-builder": [
        ("processing_summary", "处理摘要", "汇总步骤、方法、参数和输出清单。"),
        ("quality_report", "质量控制报告", "整理 QC 指标、警告和图表引用。"),
        ("diagnostic_report", "诊断详情报告", "保留失败项、日志与排查信息。"),
        ("reproducibility_report", "复现信息报告", "记录软件、版本、命令和参数快照。"),
    ],
    "skill-updater": [
        ("collect_evidence", "收集成功经验", "从已确认成功的任务中提取可复用事实。"),
        ("locate_skills", "定位相关 Skill", "查找应当更新的最小 Skill 集合。"),
        ("propose_diff", "生成更新差异", "生成可审阅的 SKILL.md 修改建议。"),
        ("validate_update", "验证 Skill 更新", "检查范围、格式和行为边界。"),
    ],
    "table-cleaning": [
        ("schema_normalization", "字段与类型规范化", "规范列名、数据类型和日期格式。"),
        ("missing_values", "缺失值处理", "按字段策略标记、填补或排除缺失值。"),
        ("duplicates_outliers", "重复与异常值处理", "识别重复记录和异常范围。"),
        ("cleaning_validation", "清洗结果验证", "核对主键、行数、模式和规则影响范围。"),
    ],
}

# These entries are settings or lifecycle controls, not independently runnable
# methods. Their reviewed Runner exposes them in the parameter phase instead.
PARAMETER_ONLY_OPERATION_LABELS: dict[str, set[str]] = {
    "freesurfer-tool": {
        "improve pial surface with t2",
        "use flair for better segmentation",
        "enable multi-core acceleration",
        "resume interrupted run",
    },
}


def _operation_parameter(skill: Skill) -> dict[str, Any] | None:
    """Extract bounded task choices from a Skill-authored reference table."""
    text = skill.skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    target_terms = (
        "quick reference",
        "methods catalog",
        "supported operations",
        "common workflows",
        "quick workflows",
        "quick usage",
    )
    options: list[dict[str, Any]] = []
    source_heading = ""
    seen_labels: set[str] = set()

    for heading_index, line in enumerate(lines):
        heading_match = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if not heading_match:
            continue
        heading = _clean_markdown(heading_match.group(2))
        if not any(term in heading.lower() for term in target_terms):
            continue
        heading_level = len(heading_match.group(1))
        section_end = len(lines)
        for cursor in range(heading_index + 1, len(lines)):
            next_heading = re.match(r"^(#{1,6})\s+", lines[cursor])
            if next_heading and len(next_heading.group(1)) <= heading_level:
                section_end = cursor
                break
        for table_index in range(heading_index + 1, section_end - 1):
            if "|" not in lines[table_index] or "|" not in lines[table_index + 1]:
                continue
            separator_cells = _table_cells(lines[table_index + 1])
            if not separator_cells or not all(
                re.fullmatch(r":?-{3,}:?", cell.replace(" ", ""))
                for cell in separator_cells
            ):
                continue
            for row_index in range(table_index + 2, section_end):
                row = lines[row_index]
                if "|" not in row or not row.strip():
                    break
                cells = _table_cells(row)
                if len(cells) < 2:
                    continue
                label = cells[0][:100]
                normalized_label = label.casefold()
                if not label or normalized_label in seen_labels:
                    continue
                seen_labels.add(normalized_label)
                slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
                option_value = slug or f"option-{len(options) + 1}"
                description = "；".join(cell for cell in cells[1:] if cell)[:360]
                options.append(
                    {
                        "value": option_value,
                        "label": label,
                        "description": (
                            f"{description}（来源：SKILL.md:L{row_index + 1}）"
                            if description
                            else f"来源：SKILL.md:L{row_index + 1}"
                        ),
                    }
                )
                if len(options) >= 12:
                    break
            source_heading = heading
            break
        if options:
            break

    if len(options) < 2:
        options = [
            {"value": value, "label": label, "description": description}
            for value, label, description in CURATED_OPERATION_OPTIONS.get(skill.name, [])
        ]
        source_heading = "Skill 核心能力"
    excluded = PARAMETER_ONLY_OPERATION_LABELS.get(skill.name, set())
    if excluded:
        options = [
            option
            for option in options
            if str(option["label"]).casefold() not in excluded
        ]
    if len(options) < 2:
        return None
    return _parameter(
        "operation",
        "任务/方法范围",
        f"选项来自该 Skill 的“{source_heading}”章节；这是规划约束，不代表已经存在执行器。",
        "string",
        options[0]["value"],
        options,
        group="方法与任务",
    )


def _command_kind(command: str) -> str:
    lowered = command.lower().lstrip()
    if lowered.startswith(("export ", "source ", "set ", "$env:")):
        return "environment"
    if lowered.startswith(
        (
            "pip ",
            "pip3 ",
            "conda ",
            "mamba ",
            "apt ",
            "apt-get ",
            "brew ",
            "git clone ",
            "docker pull ",
            "wget ",
            "curl ",
        )
    ):
        return "setup"
    return "operation"


def _looks_like_shell_command(command: str) -> bool:
    stripped = command.strip()
    if not stripped or stripped.startswith(("#", "//", "...", "---")):
        return False
    if stripped.endswith(":") and " " not in stripped[:-1]:
        return False
    first = re.split(r"\s+", stripped, maxsplit=1)[0].lower()
    rejected = {
        "usage:",
        "output:",
        "example:",
        "expected",
        "note:",
        "step",
        "then",
    }
    return first not in rejected and bool(re.match(r"^[a-z0-9_.$/{][^:]*$", first))


def _command_references(skill: Skill) -> list[dict[str, Any]]:
    """Collect examples from shell fences without claiming they are executable runners."""
    text = skill.skill_md.read_text(encoding="utf-8")
    fence_pattern = re.compile(
        r"^```(?P<language>bash|sh|shell|zsh|powershell|pwsh)\s*\n"
        r"(?P<body>.*?)^```\s*$",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    references: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_path = f"skills/{skill.name}/SKILL.md"
    for match in fence_pattern.finditer(text):
        language = match.group("language").lower()
        body = match.group("body")
        body_start_line = text[: match.start("body")].count("\n") + 1
        pending = ""
        pending_line = body_start_line
        for offset, raw_line in enumerate(body.splitlines()):
            line = raw_line.strip()
            if line.startswith("$ "):
                line = line[2:].strip()
            if not line or line.startswith("#"):
                continue
            if not pending:
                pending_line = body_start_line + offset
            pending = f"{pending} {line}".strip()
            if line.endswith("\\"):
                pending = pending[:-1].rstrip()
                continue
            command = re.sub(r"\s+", " ", pending).strip()
            pending = ""
            if not _looks_like_shell_command(command):
                continue
            command = re.sub(
                r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9]{20,}",
                "<redacted-api-key>",
                command,
            )
            signature = command.casefold()
            if signature in seen:
                continue
            seen.add(signature)
            references.append(
                {
                    "command": command[:1200],
                    "language": language,
                    "source_path": source_path,
                    "line_start": pending_line,
                    "kind": _command_kind(command),
                    "executable": False,
                }
            )
        if len(references) >= 8:
            break
    return sorted(
        references[:8],
        key=lambda item: ({"operation": 0, "environment": 1, "setup": 2}.get(item["kind"], 3), item["line_start"]),
    )


def _source_references(skill: Skill, command_count: int) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = [
        {
            "path": f"skills/{skill.name}/SKILL.md",
            "label": "Skill 说明与方法依据",
            "kind": "skill",
            "line_start": 1,
            "line_end": None,
        }
    ]
    scripts_dir = skill.path / "scripts"
    if scripts_dir.is_dir():
        for script_path in sorted(item for item in scripts_dir.rglob("*") if item.is_file())[:12]:
            references.append(
                {
                    "path": script_path.relative_to(PROJECT_ROOT).as_posix(),
                    "label": script_path.name,
                    "kind": "script",
                    "line_start": 1,
                    "line_end": None,
                }
            )
    if command_count:
        references.append(
            {
                "path": f"skills/{skill.name}/SKILL.md",
                "label": f"已提取 {command_count} 条参考命令",
                "kind": "command",
                "line_start": None,
                "line_end": None,
            }
        )
    return references


def _generic_artifacts(skill: Skill, section_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if section_id in {"research-lifecycle", "local-infrastructure"}:
        return [], []
    slug = re.sub(r"[^a-z0-9]+", "-", skill.name.lower()).strip("-")
    if section_id in {"dataset-workflows", "data-preparation", "modality-workflows"}:
        input_type, binding, label = "dataset_folder", "folder", "输入数据集"
    elif section_id == "models-analysis":
        input_type, binding, label = "analysis_input", "artifact", "分析输入"
    else:
        input_type, binding, label = "imaging_input", "artifact", "影像或工具输入"
    return (
        [
            {
                "id": "primary_input",
                "type": input_type,
                "label": label,
                "description": "可从已登记数据集、授权路径或上游步骤选择；具体格式仍以该 Skill 的说明为准。",
                "required": False,
                "binding": binding,
                "source_options": ["dataset", "existing_path", "upstream_output"],
                "validation": ["path_exists"],
            }
        ],
        [
            {
                "id": "planned_output",
                "type": "planned_artifact",
                "label": "规划输出",
                "description": "该 planning 步骤声明的预期产物；只有接入 runner 后才会实际生成。",
                "primary": True,
                "path_template": f"derivatives/{slug}/",
            }
        ],
    )


def _generic_method(skill: Skill, section_id: str) -> dict[str, Any]:
    slug = re.sub(r"[^a-z0-9]+", "-", skill.name.lower()).strip("-")
    label = LABEL_OVERRIDES.get(skill.name, skill.display_name)
    operation = _operation_parameter(skill)
    commands = _command_references(skill)
    sources = _source_references(skill, len(commands))
    input_slots, output_slots = _generic_artifacts(skill, section_id)
    evidence_backed = bool(operation or commands or skill.script_count)
    return {
        "capability": f"skill.{slug}",
        "method_id": f"{slug}-guided",
        "label": f"{label} 受约束方案",
        "description": (
            f"依据 {skill.name}/SKILL.md 生成结构化步骤；"
            "当前为规划型方法，不对应可直接执行的 runner。"
        ),
        "runner_id": f"planning.{slug}",
        "execution_mode": "planning",
        "input_types": ["*"],
        "output_types": ["planned_artifact"],
        "default_recommended": True,
        "default_reason": (
            "该规划方法包含从 SKILL.md 提取的任务选项、脚本或命令依据。"
            if evidence_backed
            else "该 Skill 暂无足够的方法级依据，当前保留受约束的类别参数。"
        ),
        "structure_level": "evidence" if evidence_backed else "profile",
        "source_references": sources,
        "command_references": commands,
        "delegate_skill_ids": list(
            dict.fromkeys([*skill.dependencies, *skill.complementary_skills])
        )[:12],
        "input_slots": input_slots,
        "output_slots": output_slots,
        "parameters": [
            *([operation] if operation else []),
            *PROFILE_PARAMETERS[section_id],
            *PROFILE_ADVANCED_PARAMETERS[section_id],
        ],
    }


def _dwi_tractography_methods() -> list[dict[str, Any]]:
    return [
        {
            "capability": "dwi.tractography",
            "method_id": "mrtrix3-act-sift2",
            "label": "MRtrix3 ACT + SIFT2",
            "description": "基于多组织 FOD、ACT 和 SIFT2 的纤维追踪与连接组规划。",
            "runner_id": "planning.mrtrix3-tractography",
            "execution_mode": "planning",
            "input_types": ["preprocessed_dwi"],
            "output_types": ["tractogram", "connectome"],
            "input_slots": [
                {
                    "id": "preprocessed_dwi", "type": "preprocessed_dwi",
                    "label": "预处理后的 DWI",
                    "description": "已经完成运动、涡流和畸变校正，并包含有效梯度表的 DWI。",
                    "required": True, "binding": "file_bundle",
                    "formats": [".nii", ".nii.gz", ".mif"],
                    "companions": ["bval", "bvec"],
                    "source_options": ["dataset", "existing_path", "upstream_output"],
                    "validation": ["path_exists", "gradient_count_matches_volumes"],
                },
                {
                    "id": "t1w", "type": "t1w_image", "label": "T1w 结构像",
                    "description": "选择由 T1w 生成 5TT 时使用的结构像。",
                    "required": False,
                    "required_when": {"act_enabled": [True], "five_tt_source": ["fsl", "freesurfer"]},
                    "binding": "file", "formats": [".nii", ".nii.gz", ".mif"],
                    "source_options": ["dataset", "existing_path"],
                    "validation": ["path_exists", "nifti_readable"],
                },
                {
                    "id": "five_tt", "type": "five_tt_image", "label": "已有 5TT 影像",
                    "description": "5TT 来源选择“使用已有 5TT”时必须提供。",
                    "required": False,
                    "required_when": {"act_enabled": [True], "five_tt_source": ["existing"]},
                    "binding": "file", "formats": [".nii", ".nii.gz", ".mif"],
                    "source_options": ["existing_path", "upstream_output"],
                    "validation": ["path_exists", "spatially_compatible"],
                },
                {
                    "id": "seed_roi", "type": "seed_mask", "label": "种子 ROI",
                    "description": "种子策略选择“指定 ROI”时必须提供。",
                    "required": False, "required_when": {"seeding_strategy": ["roi"]},
                    "binding": "file", "formats": [".nii", ".nii.gz", ".mif"],
                    "source_options": ["existing_path", "upstream_output"],
                    "validation": ["path_exists", "spatially_compatible"],
                },
                {
                    "id": "parcellation", "type": "parcellation_image", "label": "脑区分区图",
                    "description": "生成连接组矩阵时用于定义网络节点。",
                    "required": False, "required_when": {"generate_connectome": [True]},
                    "binding": "file", "formats": [".nii", ".nii.gz", ".mif"],
                    "source_options": ["existing_path", "upstream_output"],
                    "validation": ["path_exists", "integer_labels", "spatially_compatible"],
                },
                {
                    "id": "scalar_image", "type": "scalar_image", "label": "边权标量图",
                    "description": "连接组边权选择沿流线标量均值时使用。",
                    "required": False,
                    "required_when": {"generate_connectome": [True], "connectome_weighting": ["mean_scalar"]},
                    "binding": "file", "formats": [".nii", ".nii.gz", ".mif"],
                    "source_options": ["existing_path", "upstream_output"],
                    "validation": ["path_exists", "spatially_compatible"],
                },
            ],
            "output_slots": [
                {"id": "response_functions", "type": "response_functions", "label": "组织响应函数", "description": "FOD 建模使用的组织响应函数。", "path_template": "derivatives/mrtrix3/{subject}/response/"},
                {"id": "fod", "type": "fod_image", "label": "纤维方向分布", "description": "CSD/MSMT-CSD 估计的 FOD 影像。", "format": ".mif", "path_template": "derivatives/mrtrix3/{subject}/fod.mif"},
                {"id": "tractogram", "type": "tractogram", "label": "纤维流线文件", "description": "MRtrix3 tckgen 生成的 tractogram。", "format": ".tck", "primary": True, "path_template": "derivatives/mrtrix3/{subject}/tractogram.tck"},
                {"id": "sift2_weights", "type": "streamline_weights", "label": "SIFT2 流线权重", "description": "与完整 tractogram 对应的 SIFT2 权重。", "format": ".txt", "path_template": "derivatives/mrtrix3/{subject}/sift2_weights.txt", "generated_when": {"postprocessing": ["sift2"]}},
                {"id": "connectome", "type": "connectome", "label": "结构连接组矩阵", "description": "根据脑区分区和流线汇总得到的 ROI×ROI 矩阵。", "format": ".csv", "path_template": "derivatives/mrtrix3/{subject}/connectome.csv", "generated_when": {"generate_connectome": [True]}},
            ],
            "default_recommended": True,
            "default_reason": "存在 T1w 且输入满足要求时，优先规划 ACT + SIFT2 路线。",
            "parameters": [
                _parameter(
                    "algorithm",
                    "追踪算法",
                    "iFOD2 适合概率追踪；SD_STREAM 用于确定性追踪方案。",
                    "string",
                    "iFOD2",
                    _options(("iFOD2", "iFOD2 概率追踪"), ("SD_STREAM", "SD_STREAM 确定性追踪")),
                    group="追踪方案",
                ),
                _parameter(
                    "streamline_count",
                    "目标流线数量",
                    "生成的目标流线数；高级模式可进一步控制长度、步长与终止阈值。",
                    "integer",
                    1000000,
                    _options((50000, "5 万"), (1000000, "100 万"), (10000000, "1000 万")),
                    control="select",
                    group="追踪方案",
                ),
                _parameter(
                    "seeding_strategy",
                    "种子策略",
                    "动态 FOD 播种适合全脑追踪；GMWMI 播种依赖 ACT 的灰白质交界面。",
                    "string",
                    "dynamic",
                    _options(("dynamic", "FOD 动态播种"), ("gmwmi", "GMWMI 播种"), ("roi", "指定 ROI 播种")),
                    group="追踪方案",
                ),
                _parameter(
                    "postprocessing",
                    "流线后处理",
                    "SIFT2 保留完整 tractogram 并生成权重；SIFT 生成过滤后的 tractogram。",
                    "string",
                    "sift2",
                    _options(("sift2", "SIFT2 权重（推荐）"), ("sift", "SIFT 过滤"), ("none", "不做 SIFT")),
                    group="追踪方案",
                ),
                _parameter(
                    "response_algorithm", "响应函数估计", "单壳可选 tournier，多壳多组织通常使用 dhollander。",
                    "string", "dhollander", _options(("dhollander", "Dhollander 多组织"), ("tournier", "Tournier 单组织"), ("tax", "Tax")),
                    level="advanced", group="FOD 建模",
                ),
                _parameter(
                    "fod_model", "FOD 模型", "选择单组织或多壳多组织约束球面反卷积。",
                    "string", "msmt_csd", _options(("msmt_csd", "MSMT-CSD"), ("csd", "单组织 CSD")),
                    level="advanced", group="FOD 建模",
                ),
                _parameter(
                    "act_enabled", "使用 ACT", "使用 5TT 解剖约束追踪，要求可用的 T1w/5TT。",
                    "boolean", True, _options((True, "启用"), (False, "关闭")),
                    level="advanced", group="ACT 解剖约束",
                ),
                _parameter(
                    "five_tt_source", "5TT 来源", "选择 5TT 组织分割的生成来源。",
                    "string", "fsl", _options(("fsl", "5ttgen fsl"), ("freesurfer", "5ttgen freesurfer"), ("existing", "使用已有 5TT")),
                    level="advanced", group="ACT 解剖约束", visible_when={"act_enabled": [True]},
                ),
                _parameter(
                    "backtrack", "允许回溯", "ACT 追踪进入无效组织时允许回溯并尝试其他方向。",
                    "boolean", True, _options((True, "启用"), (False, "关闭")),
                    level="advanced", group="ACT 解剖约束", visible_when={"act_enabled": [True]},
                ),
                _parameter(
                    "crop_at_gmwmi", "裁剪到 GMWMI", "把流线端点裁剪到灰白质交界面。",
                    "boolean", True, _options((True, "启用"), (False, "关闭")),
                    level="advanced", group="ACT 解剖约束", visible_when={"act_enabled": [True]},
                ),
                _parameter(
                    "step_size", "追踪步长", "每次积分前进的空间距离；留空表示采用 MRtrix 自动值。",
                    "number", None, control="number", level="advanced", group="追踪几何", unit="mm",
                    required=False, minimum=0, maximum=5, step=0.05,
                ),
                _parameter(
                    "max_angle", "最大转角", "相邻追踪步允许的最大方向变化。",
                    "number", None, control="number", level="advanced", group="追踪几何", unit="°",
                    required=False, minimum=1, maximum=90, step=1,
                ),
                _parameter(
                    "min_length", "最小流线长度", "短于该长度的流线将被丢弃。",
                    "number", 15, control="number", level="advanced", group="追踪几何", unit="mm",
                    minimum=0, maximum=500, step=1,
                ),
                _parameter(
                    "max_length", "最大流线长度", "长于该长度的流线将被终止或丢弃。",
                    "number", 600, control="number", level="advanced", group="追踪几何", unit="mm",
                    minimum=1, maximum=2000, step=1,
                ),
                _parameter(
                    "cutoff", "FOD 截止阈值", "FOD 幅度低于阈值时停止追踪。",
                    "number", 0.06, control="number", level="advanced", group="终止条件",
                    minimum=0.001, maximum=1, step=0.001,
                ),
                _parameter(
                    "max_attempts", "最大播种尝试数", "为达到目标流线数允许的最大播种尝试次数。",
                    "integer", None, control="number", level="advanced", group="终止条件",
                    required=False, minimum=1000, maximum=1000000000, step=1000,
                ),
                _parameter(
                    "sift_target_count", "SIFT 目标数量", "SIFT 过滤后希望保留的流线数量。",
                    "integer", 50000, control="number", level="advanced", group="SIFT 与连接组",
                    minimum=1000, maximum=100000000, step=1000,
                    visible_when={"postprocessing": ["sift"]},
                ),
                _parameter(
                    "generate_connectome", "生成连接组矩阵", "使用分区图把流线汇总为 ROI×ROI 矩阵。",
                    "boolean", True, _options((True, "生成"), (False, "不生成")),
                    level="advanced", group="SIFT 与连接组",
                ),
                _parameter(
                    "connectome_weighting", "连接组边权", "决定每条边使用流线计数、SIFT2 权重或长度校正。",
                    "string", "sift2", _options(("count", "流线计数"), ("sift2", "SIFT2 权重"), ("length", "长度加权"), ("mean_scalar", "沿流线标量均值")),
                    level="advanced", group="SIFT 与连接组",
                    visible_when={"generate_connectome": [True]},
                ),
                _parameter(
                    "symmetric", "对称化矩阵", "把有向计数合并为对称连接矩阵。",
                    "boolean", True, _options((True, "对称"), (False, "保持方向")),
                    level="advanced", group="SIFT 与连接组", visible_when={"generate_connectome": [True]},
                ),
                _parameter(
                    "zero_diagonal", "清零对角线", "移除同一节点内部的自连接。",
                    "boolean", True, _options((True, "清零"), (False, "保留")),
                    level="advanced", group="SIFT 与连接组", visible_when={"generate_connectome": [True]},
                ),
                _parameter(
                    "assignment_radius", "节点分配半径", "端点未落在标签内时允许搜索最近节点的半径。",
                    "number", 2, control="number", level="advanced", group="SIFT 与连接组", unit="mm",
                    minimum=0, maximum=10, step=0.5, visible_when={"generate_connectome": [True]},
                ),
            ],
        },
        {
            "capability": "dwi.tractography",
            "method_id": "fsl-probtrackx",
            "label": "FSL bedpostx + probtrackx",
            "description": "基于 bedpostx 局部纤维方向模型进行 ROI/种子概率追踪规划。",
            "runner_id": "planning.fsl-probtrackx",
            "execution_mode": "planning",
            "input_types": ["preprocessed_dwi"],
            "output_types": ["tractogram", "connectivity_map"],
            "input_slots": [
                {"id": "preprocessed_dwi", "type": "preprocessed_dwi", "label": "预处理后的 DWI", "description": "已经完成校正并具有有效梯度表的 DWI。", "required": True, "binding": "file_bundle", "formats": [".nii", ".nii.gz"], "companions": ["bval", "bvec"], "source_options": ["dataset", "existing_path", "upstream_output"], "validation": ["path_exists", "gradient_count_matches_volumes"]},
                {"id": "seed", "type": "seed_mask", "label": "种子 Mask/ROI", "description": "probtrackx 概率追踪的起始区域。", "required": True, "binding": "file", "formats": [".nii", ".nii.gz"], "source_options": ["existing_path", "upstream_output"], "validation": ["path_exists", "spatially_compatible"]},
                {"id": "target", "type": "target_mask", "label": "目标 Mask/ROI", "description": "种子到目标模式下需要的目标区域。", "required": False, "required_when": {"tracking_mode": ["seed_to_target"]}, "binding": "file", "formats": [".nii", ".nii.gz", ".txt"], "source_options": ["existing_path", "upstream_output"], "validation": ["path_exists", "spatially_compatible"]},
                {"id": "network_nodes", "type": "parcellation_image", "label": "网络节点分区", "description": "网络模式下定义节点的标签影像。", "required": False, "required_when": {"tracking_mode": ["network"]}, "binding": "file", "formats": [".nii", ".nii.gz"], "source_options": ["existing_path", "upstream_output"], "validation": ["path_exists", "integer_labels"]},
                {"id": "waypoint", "type": "waypoint_mask", "label": "Waypoint Mask", "description": "路径必须经过的可选区域。", "required": False, "binding": "file", "formats": [".nii", ".nii.gz"], "source_options": ["existing_path", "upstream_output"], "validation": ["path_exists", "spatially_compatible"]},
                {"id": "exclusion", "type": "exclusion_mask", "label": "排除 Mask", "description": "路径不得进入的可选区域。", "required": False, "binding": "file", "formats": [".nii", ".nii.gz"], "source_options": ["existing_path", "upstream_output"], "validation": ["path_exists", "spatially_compatible"]},
            ],
            "output_slots": [
                {"id": "tractogram", "type": "tractogram", "label": "概率追踪路径", "description": "probtrackx 生成或导出的概率路径结果。", "primary": True, "path_template": "derivatives/fsl/{subject}/probtrackx/"},
                {"id": "connectivity_map", "type": "connectivity_map", "label": "概率连接图", "description": "路径访问计数或归一化连接概率图。", "path_template": "derivatives/fsl/{subject}/probtrackx/connectivity/", "generated_when": {"output_path_distribution": [True]}},
            ],
            "default_recommended": False,
            "default_reason": "适合已有 FSL 环境或明确的种子与目标 ROI 追踪。",
            "parameters": [
                _parameter(
                    "samples",
                    "每体素采样数",
                    "控制概率追踪的采样规模。",
                    "integer",
                    5000,
                    _options((1000, "1,000"), (5000, "5,000"), (10000, "10,000")),
                    group="概率追踪",
                ),
                _parameter(
                    "tracking_mode", "追踪模式", "选择种子到目标、全脑网络或仅输出路径分布。",
                    "string", "seed_to_target", _options(("seed_to_target", "种子到目标"), ("network", "ROI 网络"), ("seed_only", "种子路径分布")),
                    group="概率追踪",
                ),
                _parameter(
                    "loop_check",
                    "启用回路检查",
                    "规划时排除发生回路的路径。",
                    "boolean",
                    True,
                    _options((True, "启用"), (False, "关闭")),
                    group="概率追踪",
                ),
                _parameter(
                    "distance_correction", "距离校正", "按路径长度校正连接概率。",
                    "boolean", False, _options((True, "启用"), (False, "关闭")),
                    group="概率追踪",
                ),
                _parameter(
                    "steps", "最大步数", "每条样本路径允许的最大追踪步数。",
                    "integer", 2000, control="number", level="advanced", group="步进与曲率",
                    minimum=1, maximum=10000, step=1,
                ),
                _parameter(
                    "step_length", "步长", "probtrackx 每一步的物理距离。",
                    "number", 0.5, control="number", level="advanced", group="步进与曲率", unit="mm",
                    minimum=0.05, maximum=5, step=0.05,
                ),
                _parameter(
                    "curvature_threshold", "曲率阈值", "限制路径转弯；值越低允许的弯曲通常越大。",
                    "number", 0.2, control="number", level="advanced", group="步进与曲率",
                    minimum=0.01, maximum=1, step=0.01,
                ),
                _parameter(
                    "fib_threshold", "纤维体积分数阈值", "低于阈值的局部纤维方向不参与采样。",
                    "number", 0.01, control="number", level="advanced", group="步进与曲率",
                    minimum=0, maximum=1, step=0.001,
                ),
                _parameter(
                    "stop_at_target", "到达目标即停止", "路径首次到达目标区域后停止继续采样。",
                    "boolean", False, _options((True, "停止"), (False, "继续")),
                    level="advanced", group="空间约束", visible_when={"tracking_mode": ["seed_to_target", "network"]},
                ),
                _parameter(
                    "output_path_distribution", "输出路径分布", "保存每个体素的访问计数或概率分布。",
                    "boolean", True, _options((True, "输出"), (False, "不输出")),
                    level="advanced", group="输出",
                ),
                _parameter(
                    "normalize_by_samples", "按有效样本归一化", "把路径计数转换为相对于有效样本数的比例。",
                    "boolean", True, _options((True, "归一化"), (False, "保留计数")),
                    level="advanced", group="输出",
                ),
            ],
        },
    ]


def build_manifest(skill: Skill, section_id: str) -> dict[str, Any]:
    provides = [_generic_method(skill, section_id)]
    if skill.name == "dwi-skill":
        commands = _command_references(skill)
        sources = _source_references(skill, len(commands))
        for method in _dwi_tractography_methods():
            method["structure_level"] = "reviewed"
            method["source_references"] = sources
            method["command_references"] = commands
            method["delegate_skill_ids"] = ["dipy-tool", "fsl-tool", "qsiprep-tool"]
            provides.append(method)
    return {
        "schema_version": 1,
        "manifest_kind": "planning",
        "generated_from": "scripts/build_structured_skill_manifests.py",
        "skill_id": skill.name,
        "description": _description(skill),
        "provides": provides,
    }


def _validate_manifest(skill: Skill, manifest: dict[str, Any]) -> None:
    methods = manifest.get("provides", [])
    if not methods:
        raise RuntimeError(f"{skill.name}: planning manifest has no methods")
    for method in methods:
        method_id = method.get("method_id", "<unknown>")
        if method.get("execution_mode") != "planning":
            raise RuntimeError(f"{skill.name}/{method_id}: generated method must stay planning-only")
        if not method.get("source_references"):
            raise RuntimeError(f"{skill.name}/{method_id}: missing source references")
        if any(reference.get("executable") for reference in method.get("command_references", [])):
            raise RuntimeError(f"{skill.name}/{method_id}: reference command cannot be executable")

        parameter_ids: set[str] = set()
        for parameter in method.get("parameters", []):
            parameter_id = str(parameter.get("id") or "")
            if not parameter_id or parameter_id in parameter_ids:
                raise RuntimeError(f"{skill.name}/{method_id}: invalid parameter id {parameter_id!r}")
            parameter_ids.add(parameter_id)
            if not str(parameter.get("description") or "").strip():
                raise RuntimeError(f"{skill.name}/{method_id}/{parameter_id}: missing description")
            for option in parameter.get("options", []):
                if "value" not in option or not str(option.get("label") or "").strip():
                    raise RuntimeError(
                        f"{skill.name}/{method_id}/{parameter_id}: invalid parameter option"
                    )

        for slot_kind in ("input_slots", "output_slots"):
            for slot in method.get(slot_kind, []):
                if not str(slot.get("description") or "").strip():
                    raise RuntimeError(
                        f"{skill.name}/{method_id}/{slot.get('id', '<unknown>')}: "
                        f"missing {slot_kind} description"
                    )


def main() -> None:
    loader = SkillLoader(SKILLS_DIR, SUMMARIES_FILE)
    skills = loader.load_all()
    sections = _skill_sections()
    missing = sorted(skill.name for skill in skills if skill.name not in sections)
    unknown = sorted(set(sections) - {skill.name for skill in skills})
    if missing or unknown:
        raise RuntimeError(f"Skill taxonomy drift: missing={missing}, unknown={unknown}")

    for skill in skills:
        path = skill.path / "planning.manifest.json"
        manifest = build_manifest(skill, sections[skill.name])
        _validate_manifest(skill, manifest)
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    print(f"Wrote {len(skills)} planning manifests")


if __name__ == "__main__":
    main()
