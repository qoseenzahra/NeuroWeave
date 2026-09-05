"""Build LocalFlow's complete, reviewed Skill capability index.

The tree separates machine-reviewed runner capabilities from structured
planning capabilities generated from every Skill. Every loaded Skill must be
assigned exactly once to a curated taxonomy group; generation fails when the
catalog and index drift.
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
OUTPUT_FILE = SKILLS_DIR / "capability.tree.json"

sys.path.insert(0, str(BACKEND_ROOT))

from app.skill_loader import Skill, SkillLoader  # noqa: E402


GROUPS: list[dict[str, Any]] = [
    {
        "id": "dataset-workflows",
        "label": "公开数据集工作流",
        "description": "按数据集定位访问、整理、质控和多模态处理指南。",
        "groups": [
            {
                "id": "population-development-datasets",
                "label": "人群、发育与生命周期数据集",
                "skills": [
                    "abcd-skill", "aomic-skill", "camcan-skill", "hbn-skill",
                    "hcpa-skill", "hcpd-skill", "hcpya-skill", "ixi-skill",
                    "pnc-skill", "ukb-skill",
                ],
            },
            {
                "id": "clinical-datasets",
                "label": "临床与疾病数据集",
                "skills": [
                    "abide-skill", "adhd200-skill", "adni-skill", "aibl-skill",
                    "cobre-skill", "hcpep-skill", "mnd-skill", "mschallenge-skill",
                    "nifd-skill", "oasis-skill", "ppmi-skill",
                    "rest-mneta-mdd-skill", "tcp-skill", "ucla-cnp-skill",
                ],
            },
            {
                "id": "task-cognitive-datasets",
                "label": "任务态与认知实验数据集",
                "skills": ["bold5000-skill", "dmt-har-med-skill", "nsd-skill", "scan-skill"],
            },
            {
                "id": "eeg-datasets",
                "label": "EEG 数据集",
                "skills": ["seed-iv-skill", "seed-vig-skill"],
            },
        ],
    },
    {
        "id": "modality-workflows",
        "label": "成像与电生理模态",
        "description": "按数据模态定位端到端预处理、特征提取与分析指南。",
        "groups": [
            {
                "id": "modality-pipelines",
                "label": "模态处理工作流",
                "skills": [
                    "asl-skill", "dwi-skill", "eeg-skill", "fmri-skill",
                    "meg-skill", "pet-skill", "smri-skill",
                ],
            },
        ],
    },
    {
        "id": "data-preparation",
        "label": "数据理解、转换与整理",
        "description": "检查输入、转换格式、组织 BIDS、批处理影像和清洗表格。",
        "groups": [
            {
                "id": "inspection-cleaning",
                "label": "检查、清洗与批处理",
                "skills": ["dataset-inspector", "table-cleaning", "image-batch-processing"],
            },
            {
                "id": "format-conversion-organization",
                "label": "格式转换与数据组织",
                "skills": ["bids-organizer", "dcm2nii", "nii2dcm", "nibabel-skill"],
            },
        ],
    },
    {
        "id": "neuroimaging-tools",
        "label": "神经影像软件与分析工具",
        "description": "定位现有开源软件的预处理、连接、量化和分割能力。",
        "groups": [
            {
                "id": "preprocessing-suites",
                "label": "标准预处理与综合软件",
                "skills": [
                    "fmriprep-tool", "freesurfer-tool", "fsl-tool",
                    "hcppipeline-tool", "qsiprep-tool",
                ],
            },
            {
                "id": "analysis-libraries",
                "label": "模态分析库与连接分析",
                "skills": ["conn-tool", "dipy-tool", "mne-eeg-tool", "nilearn-tool"],
            },
            {
                "id": "quality-harmonization-segmentation",
                "label": "校正、Harmonization 与分割",
                "skills": ["harmonization-tool", "wmh-segmentation"],
            },
        ],
    },
    {
        "id": "models-analysis",
        "label": "建模、统计与模式发现",
        "description": "从经典统计、信号分解到深度学习和因果、生存模型。",
        "groups": [
            {
                "id": "deep-prediction-models",
                "label": "深度学习与脑网络预测",
                "skills": [
                    "bnt", "braingnn", "brainnetcnn", "cnn3d", "combraintf",
                    "fm_app", "ibgnn", "lggnn", "neurostorm",
                ],
            },
            {
                "id": "statistical-prediction-models",
                "label": "统计、预测与个体差异模型",
                "skills": [
                    "brain-age-modeling", "causal-treatment-models", "cpm", "glm",
                    "imaging-genetics-models", "spacenet", "statistical-ml",
                    "subject-subtyping", "survival-models", "temporal-models",
                ],
            },
            {
                "id": "signal-decomposition-parcellation",
                "label": "信号处理、分解与脑区划分",
                "skills": [
                    "detrending", "dictlearning", "filtering", "hierarchical", "ica", "kmeans",
                ],
            },
            {
                "id": "discovery-decoding-routing",
                "label": "连接组发现、解码与模型路由",
                "skills": [
                    "connectome-discovery", "kg-link-prediction",
                    "neuroimaging-decoding", "run_models",
                ],
            },
        ],
    },
    {
        "id": "research-lifecycle",
        "label": "科研全流程与成果表达",
        "description": "支持检索、构思、方法设计、实验、知识图谱、写作和结果展示。",
        "groups": [
            {
                "id": "literature-ideation",
                "label": "检索、选题与知识组织",
                "skills": [
                    "academic-research-hub", "multi-search-engine", "research-idea",
                    "knowledge-graph-builder", "method-design",
                ],
            },
            {
                "id": "experiments-publication",
                "label": "实验、写作与发布",
                "skills": ["experiment-controller", "paper-writing", "overleaf-skill"],
            },
            {
                "id": "visualization-reporting",
                "label": "可视化与报告",
                "skills": ["brain-visualization", "report-builder"],
            },
        ],
    },
    {
        "id": "local-infrastructure",
        "label": "本地环境、执行与工程保障",
        "description": "管理环境和依赖，安全调用命令，维护版本与审计记录。",
        "groups": [
            {
                "id": "environment-dependencies",
                "label": "环境、容器与依赖",
                "skills": ["conda-env-manager", "docker-env-manager", "dependency-planner"],
            },
            {
                "id": "shell-version-control",
                "label": "命令执行与版本控制",
                "skills": ["claw-shell", "git-essentials", "git-workflows"],
            },
            {
                "id": "verification-maintenance",
                "label": "验证、维护与审计",
                "skills": ["harness-core", "skill-updater", "beautiful-log"],
            },
        ],
    },
]


LABEL_OVERRIDES = {
    "academic-research-hub": "学术文献检索与下载",
    "asl-skill": "ASL 灌注成像处理",
    "beautiful-log": "对话日志整理",
    "bids-organizer": "BIDS 数据组织",
    "brain-age-modeling": "脑龄建模",
    "brain-visualization": "脑影像结果可视化",
    "claw-shell": "安全命令执行",
    "conda-env-manager": "Conda 环境管理",
    "dataset-inspector": "数据集巡检",
    "dependency-planner": "依赖规划",
    "docker-env-manager": "Docker 环境管理",
    "dwi-skill": "DWI 扩散成像工作流",
    "eeg-skill": "EEG 脑电处理工作流",
    "experiment-controller": "实验执行与记录",
    "fmri-skill": "fMRI 功能成像工作流",
    "harmonization-tool": "多中心数据 Harmonization",
    "image-batch-processing": "影像批处理",
    "knowledge-graph-builder": "知识图谱构建",
    "meg-skill": "MEG 脑磁处理工作流",
    "method-design": "研究方法设计",
    "multi-search-engine": "多搜索引擎检索",
    "paper-writing": "论文写作",
    "pet-skill": "PET 成像处理工作流",
    "report-builder": "结果与质控报告",
    "research-idea": "研究选题与构思",
    "run_models": "预测模型选择与运行指南",
    "skill-updater": "Skill 经验更新",
    "smri-skill": "sMRI 结构成像工作流",
    "statistical-ml": "统计与机器学习",
    "table-cleaning": "表格清洗",
    "wmh-segmentation": "白质高信号分割",
}


KEYWORD_OVERRIDES = {
    "asl-skill": ["ASL", "CBF", "脑灌注"],
    "bids-organizer": ["BIDS", "数据整理", "数据组织"],
    "dataset-inspector": ["数据巡检", "文件检查", "元数据"],
    "dcm2nii": ["DICOM", "NIfTI", "格式转换"],
    "dwi-skill": ["DWI", "DTI", "扩散磁共振", "纤维追踪"],
    "eeg-skill": ["EEG", "脑电", "ERP", "BCI"],
    "fmri-skill": ["fMRI", "功能磁共振", "功能连接"],
    "fmriprep-tool": ["fMRIPrep", "fMRI 预处理"],
    "freesurfer-tool": ["FreeSurfer", "皮层重建", "分割"],
    "fsl-tool": ["FSL", "FLIRT", "FEAT", "eddy", "配准"],
    "harmonization-tool": ["ComBat", "批次效应", "多中心"],
    "meg-skill": ["MEG", "脑磁", "源定位", "时频分析"],
    "mne-eeg-tool": ["MNE", "EEG", "ICA", "脑电预处理"],
    "nibabel-skill": ["NIfTI", "affine", "影像读写"],
    "nii2dcm": ["NIfTI", "DICOM", "格式转换"],
    "nilearn-tool": ["Nilearn", "ROI", "功能连接", "解码"],
    "pet-skill": ["PET", "SUVR", "部分容积校正"],
    "qsiprep-tool": ["QSIPrep", "DWI 预处理", "topup", "eddy"],
    "smri-skill": ["sMRI", "T1w", "T2w", "FLAIR", "结构磁共振"],
    "table-cleaning": ["CSV", "TSV", "Excel", "缺失值", "异常值"],
    "wmh-segmentation": ["WMH", "FLAIR", "白质高信号"],
}


STRUCTURED_BRANCH = {
    "id": "structured-execution",
    "label": "已结构化的本地任务能力",
    "description": "已有受审 Manifest、方法选项、参数定义和 runner，可生成交互式任务卡。",
    "execution_level": "category",
    "children": [
        {
            "id": "structured-data-preparation",
            "label": "数据检查与整理",
            "execution_level": "category",
            "children": [
                {
                    "id": "dwi.inspect",
                    "label": "DWI 数据集巡检",
                    "description": "扫描目录结构和轻量元数据，识别 DWI、梯度文件与输入条件。",
                    "keywords": ["检查数据", "数据巡检", "DWI inspection", "质量检查"],
                    "skill_ids": ["dataset-inspector"],
                    "execution_level": "structured",
                },
                {
                    "id": "dwi.bids",
                    "label": "整理并校验 BIDS",
                    "description": "把原始或已有 DWI 数据整理为可供 BIDS-App 使用的结构。",
                    "keywords": ["BIDS", "整理数据", "组织数据集", "BIDS validation"],
                    "skill_ids": ["bids-organizer"],
                    "execution_level": "structured",
                },
            ],
        },
        {
            "id": "structured-image-processing",
            "label": "影像预处理与定量分析",
            "execution_level": "category",
            "children": [
                {
                    "id": "dwi.preprocess",
                    "label": "DWI 预处理",
                    "description": "完成畸变、运动和涡流校正，并生成质量控制结果。",
                    "keywords": ["DWI 预处理", "eddy", "topup", "QSIPrep", "运动校正"],
                    "skill_ids": ["qsiprep-tool", "fsl-tool", "hcppipeline-tool"],
                    "execution_level": "structured",
                },
                {
                    "id": "image.registration",
                    "label": "图像配准",
                    "description": "使用 FSL FLIRT 或 ANTs 把移动影像对齐到参考影像，输出配准结果与变换。",
                    "keywords": ["图像配准", "registration", "FLIRT", "ANTs", "SyN", "刚体配准", "仿射配准", "非线性配准"],
                    "skill_ids": ["fsl-tool", "smri-skill"],
                    "execution_level": "structured",
                },
                {
                    "id": "dwi.tensor_metrics",
                    "label": "扩散张量指标",
                    "description": "拟合扩散张量并计算 FA、MD、AD、RD 等指标。",
                    "keywords": ["FA", "MD", "DTI", "张量拟合", "扩散指标"],
                    "skill_ids": ["dipy-tool", "fsl-tool"],
                    "execution_level": "structured",
                },
                {
                    "id": "dwi.response",
                    "label": "DWI 组织响应函数",
                    "description": "使用 dwi2response 估计 CSD 所需白质或多组织响应函数。",
                    "keywords": ["响应函数", "response function", "dwi2response", "Dhollander", "Tournier"],
                    "skill_ids": ["dwi-skill"],
                    "execution_level": "structured",
                },
                {
                    "id": "dwi.fod",
                    "label": "DWI FOD 估计",
                    "description": "使用 CSD 或 MSMT-CSD 估计纤维方向分布，供纤维追踪使用。",
                    "keywords": ["FOD", "纤维方向分布", "dwi2fod", "CSD", "MSMT-CSD"],
                    "skill_ids": ["dwi-skill"],
                    "execution_level": "structured",
                },
                {
                    "id": "dwi.five_tt",
                    "label": "ACT 五组织类型分割",
                    "description": "从 T1w 生成 MRtrix3 ACT 追踪需要的 5TT 影像。",
                    "keywords": ["5TT", "five tissue", "5ttgen", "ACT", "五组织"],
                    "skill_ids": ["dwi-skill"],
                    "execution_level": "structured",
                },
                {
                    "id": "dwi.tractography",
                    "label": "DWI 纤维追踪与连接组",
                    "description": "选择 MRtrix3 或 FSL 纤维追踪方法；已有有效 FOD 时可直接执行 MRtrix3 tckgen。",
                    "keywords": ["纤维追踪", "tractography", "MRtrix3", "probtrackx", "connectome"],
                    "skill_ids": ["dwi-skill", "fsl-tool"],
                    "execution_level": "planning",
                },
                {
                    "id": "dwi.connectome",
                    "label": "结构连接组矩阵",
                    "description": "使用 tck2connectome 将纤维流线与脑区分区汇总为连接矩阵。",
                    "keywords": ["结构连接组", "connectome", "连接矩阵", "tck2connectome"],
                    "skill_ids": ["dwi-skill"],
                    "execution_level": "structured",
                },
            ],
        },
        {
            "id": "structured-reporting",
            "label": "结果与质量控制",
            "execution_level": "category",
            "children": [
                {
                    "id": "dwi.report",
                    "label": "处理结果报告",
                    "description": "生成流程摘要、参数快照、质量控制与结果清单。",
                    "keywords": ["QC", "报告", "结果汇总", "quality control"],
                    "skill_ids": ["report-builder"],
                    "execution_level": "structured",
                }
            ],
        },
    ],
}


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _description(skill: Skill) -> str:
    text = _collapse(skill.summary_en or skill.description)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = sentences[0] if sentences else text
    if len(summary) < 90 and len(sentences) > 1:
        summary += " " + sentences[1]
    return summary[:320].rstrip()


def _keywords(skill: Skill) -> list[str]:
    values = [skill.name, skill.display_name, *KEYWORD_OVERRIDES.get(skill.name, [])]
    values.extend(re.findall(r"\b[A-Z][A-Za-z0-9-]{1,15}\b", _description(skill))[:8])
    return list(dict.fromkeys(value for value in values if value))


def _skill_node(skill: Skill) -> dict[str, Any]:
    slug = re.sub(r"[^a-z0-9]+", "-", skill.name.lower()).strip("-")
    return {
        "id": f"skill.{slug}",
        "label": LABEL_OVERRIDES.get(skill.name, skill.display_name),
        "description": _description(skill),
        "keywords": _keywords(skill),
        "skill_ids": [skill.name],
        "execution_level": "planning",
    }


def build_tree(skills: list[Skill]) -> dict[str, Any]:
    by_name = {skill.name: skill for skill in skills}
    assigned = [
        name
        for section in GROUPS
        for group in section["groups"]
        for name in group["skills"]
    ]
    duplicates = sorted({name for name in assigned if assigned.count(name) > 1})
    missing = sorted(set(by_name) - set(assigned))
    unknown = sorted(set(assigned) - set(by_name))
    if duplicates or missing or unknown:
        raise RuntimeError(
            "Capability taxonomy drift: "
            f"duplicates={duplicates}, missing={missing}, unknown={unknown}"
        )

    taxonomy_children: list[dict[str, Any]] = []
    for section in GROUPS:
        taxonomy_children.append(
            {
                "id": section["id"],
                "label": section["label"],
                "description": section["description"],
                "execution_level": "category",
                "children": [
                    {
                        "id": group["id"],
                        "label": group["label"],
                        "execution_level": "category",
                        "children": [_skill_node(by_name[name]) for name in group["skills"]],
                    }
                    for group in section["groups"]
                ],
            }
        )

    return {
        "schema_version": 1,
        "generated_from": "scripts/build_capability_tree.py",
        "root": {
            "id": "localflow-capabilities",
            "label": "LocalFlow 本地数据处理能力",
            "description": (
                "完整索引所有现有 Skill；先按能力定位，再只读取命中的 SKILL.md。"
                "所有 Skill 都有结构化规划 Manifest；只有受审 runner 能力可生成执行预览。"
            ),
            "execution_level": "category",
            "children": [STRUCTURED_BRANCH, *taxonomy_children],
        },
    }


def main() -> None:
    loader = SkillLoader(SKILLS_DIR, SUMMARIES_FILE)
    skills = loader.load_all()
    payload = build_tree(skills)
    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_FILE} with {len(skills)} Skill capability leaves")


if __name__ == "__main__":
    main()
