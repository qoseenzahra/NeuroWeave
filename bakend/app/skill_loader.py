"""Native JSON Skill orchestration catalog; executable contracts live in Methods."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .skill_definitions import canonical_skills



def _normalize_skill_token(text: str) -> str:
    """Normalize explicit native Skill identifiers for mention matching."""
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
    overview: str = ""
    aliases: tuple[str, ...] = ()

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
        """Provide the native Skill overview within the prompt budget."""
        excerpt = re.sub(r"```[\s\S]*?```", "", self.overview or self.instructions)
        excerpt = re.sub(r"\n{3,}", "\n\n", excerpt).strip()
        if len(excerpt) > max_chars:
            excerpt = excerpt[:max_chars].rstrip() + "\n..."
        return excerpt


class SkillLoader:
    """Native Skill definitions with cached orchestration summaries."""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir.resolve()
        self._cache_signature: tuple[tuple[str, int, int], ...] | None = None
        self._cache: list[Skill] = []

    def _signature(self) -> tuple[tuple[str, int, int], ...]:
        entries: list[tuple[str, int, int]] = []
        paths = [
            *self.skills_dir.glob("*/SKILL.md"),
            *self.skills_dir.glob("*/skill.json"),
        ]
        for path in sorted(paths):
            stat = path.stat()
            entries.append((f"{path.parent.name}/{path.name}", stat.st_mtime_ns, stat.st_size))
        return tuple(entries)

    def load_all(self) -> list[Skill]:
        """Load native orchestration definitions; Markdown is reference material only."""
        signature = self._signature()
        if signature == self._cache_signature:
            return self._cache
        skills = []
        # Read each native definition once per changed filesystem signature.
        loaded = [(path, json.loads(path.read_text(encoding='utf-8')))
                  for path in sorted(self.skills_dir.glob('*/skill.json'))]
        raw = {value['id']: value for _, value in loaded}
        definitions, aliases = canonical_skills(raw)
        self._aliases = aliases
        for path, value in loaded:
            name = value['id']
            if name not in definitions:
                continue
            methods = value.get('method_refs', [])
            pipelines = value.get('pipeline_refs', [])
            description = value.get('description', '')
            rules = value.get('selection_rules', [])
            overview = '\n'.join([value.get('name', name), description,
                '按需通过 list_skill_methods 浏览，再 read_skill_method / read_skill_pipeline 读取准确契约。',
                '适用情况：', *value.get('applicability', []), '选择规则：', *rules,
                '限制：', *value.get('limitations', []),
                f'统筹 {len({r["method_ref"] for r in methods})} 个 Method 与 {len({r["pipeline_ref"] for r in pipelines})} 个 Pipeline。'])
            mode = 'runner' if methods or pipelines else 'planning'
            skills.append(Skill(name=name, display_name=value.get('name', name), description=description,
                summary_en=description, summary_zh=description, layer='orchestration', skill_type=value.get('scope','workflow'),
                runtime='registered-methods', status='ready' if mode=='runner' else 'planning',
                dependencies=[], complementary_skills=[], source='NeuroWeave', script_count=0, has_handler=False,
                executable=mode=='runner', structure_mode=mode, path=path.parent, skill_md=path,
                instructions=json.dumps(value, ensure_ascii=False, indent=2), overview=overview,
                aliases=tuple(key for key, target in aliases.items() if target == name)))
        self._cache_signature=signature
        self._cache=skills
        return skills

    def find(self, name: str) -> Skill | None:
        self.load_all()
        normalized = self._aliases.get(name.strip().lower(), name.strip().lower())
        return next((skill for skill in self.load_all() if skill.name.lower() == normalized), None)

    def infer(self, user_text: str, limit: int = 5) -> list[Skill]:
        """Infer explicitly mentioned skills by their registered identifiers and aliases."""
        normalized_message = _normalize_skill_token(user_text)
        if not normalized_message:
            return []

        inferred: list[Skill] = []
        for skill in self.load_all():
            candidates = (skill.name, skill.path.name, *skill.aliases)
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
