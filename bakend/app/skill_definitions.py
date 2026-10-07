"""Validate native Skill identities; retired alias definitions are unsupported."""

from .skill_references import reference_specs

def native_skills(values):
    for identity, value in values.items():
        if "alias_of" in value:
            raise ValueError("Skill aliases are no longer supported: " + identity)
        if identity != value.get("id"):
            raise ValueError("Skill identity mismatch: " + identity)
        reference_specs(value)
    return values
