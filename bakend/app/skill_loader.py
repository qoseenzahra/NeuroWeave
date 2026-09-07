"""NeuroWeave adapter around NeuroClaw's reused SkillLoader."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .neuroclaw_compat.loader import (
    SkillLoader as NeuroClawSkillLoader,
    _parse_frontmatter,
    _strip_frontmatter,
)


LOCALFLOW_SKILLS = {
    "dataset-inspector",
    "image-batch-processing",
    "report-builder",
    "table-cleaning",
}


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _normalize_skill_token(text: str) -> str:
    """Match NeuroClaw's robust skill-name mention normalization."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


@dataclass(frozen=True)
class Skill:
    name: str
    display_name: str
    description: str
    summary_en: str
    summary_zh: str
    layer: str
    skill_type: str
    runtime: str
    status: str
    dependencies: list[str]
    complementary_skills: list[str]
    source: str
    script_count: int
    has_handler: bool
    executable: bool
    structure_mode: str
    path: Path
    skill_md: Path
    instructions: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "summary_en": self.summary_en,
            "summary_zh": self.summary_zh,
            "layer": self.layer,
            "skill_type": self.skill_type,
            "runtime": self.runtime,
            "status": self.status,
            "dependencies": self.dependencies,
            "complementary_skills": self.complementary_skills,
            "source": self.source,
            "script_count": self.script_count,
            "has_handler": self.has_handler,
            "executable": self.executable,
            "structure_mode": self.structure_mode,
        }

    def prompt_excerpt(self, max_chars: int = 1_800) -> str:
        """Reuse NeuroClaw's compact SKILL.md context strategy."""
        excerpt = re.sub(r"```[\s\S]*?```", "", self.instructions)
        excerpt = re.sub(r"\n{3,}", "\n\n", excerpt).strip()
        if len(excerpt) > max_chars:
            excerpt = excerpt[:max_chars].rstrip() + "\n..."
        return excerpt


class SkillLoader:
    """Cached NeuroWeave view over the copied NeuroClaw loader and skill tree."""

    def __init__(self, skills_dir: Path, summaries_file: Path | None = None) -> None:
        self.skills_dir = skills_dir.resolve()
        self.summaries_file = summaries_file.resolve() if summaries_file else None
        self._cache_signature: tuple[tuple[str, int, int], ...] | None = None
        self._cache: list[Skill] = []

    def _signature(self) -> tuple[tuple[str, int, int], ...]:
        entries: list[tuple[str, int, int]] = []
        paths = [
            *self.skills_dir.glob("*/SKILL.md"),
            *self.skills_dir.glob("*/tool.manifest.json"),
            *self.skills_dir.glob("*/execution.manifest.json"),
            *self.skills_dir.glob("*/planning.manifest.json"),
        ]
        for path in sorted(paths):
            stat = path.stat()
            entries.append((f"{path.parent.name}/{path.name}", stat.st_mtime_ns, stat.st_size))
        return tuple(entries)

    def _offline_summaries(self) -> dict[str, dict[str, str]]:
        if self.summaries_file is None or not self.summaries_file.exists():
            return {}
        try:
            payload = json.loads(self.summaries_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def load_all(self) -> list[Skill]:
        signature = self._signature()
        if signature == self._cache_signature:
            return self._cache

        upstream_skills = NeuroClawSkillLoader(self.skills_dir).load_all()
        offline_summaries = self._offline_summaries()
        skills: list[Skill] = []

        for descriptor in upstream_skills:
            skill_md = Path(descriptor["skill_md"])
            skill_path = Path(descriptor["path"])
            text = skill_md.read_text(encoding="utf-8")
            metadata = _parse_frontmatter(text)
            name = str(descriptor.get("name") or skill_path.name)
            source = "LocalFlow" if skill_path.name in LOCALFLOW_SKILLS else "NeuroClaw"
            offline = offline_summaries.get(name, {})
            scripts_dir = skill_path / "scripts"
            script_count = (
                sum(1 for item in scripts_dir.rglob("*") if item.is_file())
                if scripts_dir.is_dir()
                else 0
            )
            handler = descriptor.get("handler")
            fallback_runtime = "Script / external tools" if script_count or handler else "SKILL.md workflow"
            structure_mode = (
                "runner"
                if (
                    (skill_path / "tool.manifest.json").is_file()
                    or (skill_path / "execution.manifest.json").is_file()
                )
                else "planning"
                if (skill_path / "planning.manifest.json").is_file()
                else "advisory"
            )

            skills.append(
                Skill(
                    name=name,
                    display_name=str(
                        metadata.get("display_name")
                        or metadata.get("title")
                        or name.replace("-", " ").replace("_", " ").title()
                    ),
                    description=str(descriptor.get("description") or ""),
                    summary_en=str(offline.get("en") or descriptor.get("summary_en") or ""),
                    summary_zh=str(offline.get("zh") or descriptor.get("summary_zh") or ""),
                    layer=str(descriptor.get("layer") or "workflow"),
                    skill_type=str(descriptor.get("skill_type") or "workflow"),
                    runtime=str(metadata.get("runtime") or fallback_runtime),
                    status=str(metadata.get("status") or ("ready" if source == "LocalFlow" else "imported")),
                    dependencies=_as_string_list(descriptor.get("dependencies")),
                    complementary_skills=_as_string_list(descriptor.get("complementary_skills")),
                    source=source,
                    script_count=script_count,
                    has_handler=bool(handler),
                    executable=structure_mode == "runner",
                    structure_mode=structure_mode,
                    path=skill_path,
                    skill_md=skill_md,
                    instructions=_strip_frontmatter(text).strip(),
                )
            )

        self._cache_signature = signature
        self._cache = skills
        return skills

    def find(self, name: str) -> Skill | None:
        normalized = name.strip().lower()
        return next((skill for skill in self.load_all() if skill.name.lower() == normalized), None)

    def infer(self, user_text: str, limit: int = 5) -> list[Skill]:
        """Infer explicitly mentioned skills using NeuroClaw's name-matching rule."""
        normalized_message = _normalize_skill_token(user_text)
        if not normalized_message:
            return []

        inferred: list[Skill] = []
        for skill in self.load_all():
            candidates = (skill.name, skill.path.name)
            if any(
                token and token in normalized_message
                for candidate in candidates
                if (token := _normalize_skill_token(candidate))
            ):
                inferred.append(skill)
            if len(inferred) >= limit:
                break
        return inferred

    def stats(self) -> dict[str, Any]:
        skills = self.load_all()
        sources = Counter(skill.source for skill in skills)
        return {
            "total": len(skills),
            "sources": dict(sorted(sources.items())),
            "with_scripts": sum(skill.script_count > 0 for skill in skills),
            "with_handlers": sum(skill.has_handler for skill in skills),
            "structured": sum(skill.structure_mode != "advisory" for skill in skills),
            "planning_structured": sum(skill.structure_mode == "planning" for skill in skills),
            "runner_structured": sum(skill.structure_mode == "runner" for skill in skills),
            "execution_enabled": False,
        }
