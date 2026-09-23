"""Resolve catalog aliases without presenting duplicate orchestration entries.

Aliases preserve saved selections. They cannot contain executable definitions or
form chains; a canonical Skill remains the only owner of its selection guidance.
"""
def canonical_skills(values):
    skills = {key: value for key, value in values.items() if not value.get("alias_of")}
    aliases = {}
    for key, value in values.items():
        if not value.get("alias_of"):
            continue
        target = value["alias_of"]
        if target not in skills or target == key:
            raise ValueError("Skill alias must point directly to a canonical Skill: " + key)
        if any(value.get(field) for field in ("method_refs", "pipeline_refs", "planning_capabilities")):
            raise ValueError("Skill alias cannot own contracts: " + key)
        aliases[key] = target
    return skills, aliases
