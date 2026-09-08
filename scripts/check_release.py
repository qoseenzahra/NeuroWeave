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
    from build_planning_resolution import build
    resolution=root/'bakend/resources/planning_resolution.json'
    if json.loads(resolution.read_text(encoding='utf-8')) != build():
        raise RuntimeError("Planning execution mappings need review/regeneration")
    registry = CapabilityRegistry(root / "skills")
    methods = registry.all_methods()
    if not methods:
        raise RuntimeError("No capability methods loaded")
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
    print(f"Release structure valid: {len(methods)} methods; dependency locks present")


if __name__ == "__main__":
    main()
