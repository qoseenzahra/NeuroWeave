"""Validate native Skill identities; retired alias definitions are unsupported."""

def native_skills(values):
    for identity, value in values.items():
        if "alias_of" in value:
            raise ValueError("Skill aliases are no longer supported: " + identity)
        if identity != value.get("id"):
            raise ValueError("Skill identity mismatch: " + identity)
    return values
