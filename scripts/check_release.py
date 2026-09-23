#!/usr/bin/env python3
"""Check release structure and reviewed execution metadata without installed scientific tools."""
from pathlib import Path
import ast
import json
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "bakend"))
from app.capability_registry import CapabilityRegistry


def main():
    from app.method_registry import MethodRegistry
    from app.execution.runner_registry import RunnerRegistry
    from build_skill_layers import build as build_layers
    from build_mrtrix_commands import build as build_command, COMMANDS
    store=MethodRegistry(root);store.load(force=True)
    if set(store.methods) != RunnerRegistry().ids():
        raise RuntimeError('Atomic method catalog and Runner allowlist differ')
    for path, content in build_layers().items():
        if not path.is_file() or path.read_text(encoding='utf-8') != content:
            raise RuntimeError('Skill overview is stale: '+str(path))
    from app.method_registry import MethodDefinition
    for command in COMMANDS:
        definition=MethodDefinition.model_validate(build_command(command))
        if definition != store.methods['mrtrix.command.'+command]:
            raise RuntimeError('Command definition is stale: '+command)
    methods=list(store.methods.values())
    from app.method_validation import documentation_gaps
    for method in methods:
        if documentation_gaps(method):
            raise RuntimeError('Missing method documentation: '+method.id)
        if store.verification(method.id)['execution']['status'] == 'invalid':
            raise RuntimeError('Invalid execution evidence: '+method.id)
    referenced={ref['method_ref'] for skill in store.skills.values() for ref in skill['method_refs']}
    if set(store.methods) - referenced:
        raise RuntimeError('Methods missing from canonical Skill catalog')
    for p in store.pipelines.values():
        store.pipeline_recipe(p['id'])
    for path in (root / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))["packages"][""]
    for key in ("dependencies", "devDependencies"):
        if package[key] != lock[key]:
            raise RuntimeError("Frontend dependency lock is stale")
    for filename in ("bakend/requirements.lock", "bakend/requirements-dev.lock"):
        for line in (root / filename).read_text(encoding="utf-8").splitlines():
            if line and not line.startswith(("#", "-r ")) and "==" not in line:
                raise RuntimeError("Unpinned backend dependency")
    print(f"Release structure valid: {len(methods)} atomic methods, {len(store.pipelines)} pipelines, {len(store.skills)} skills; dependency locks present")


if __name__ == "__main__":
    main()
