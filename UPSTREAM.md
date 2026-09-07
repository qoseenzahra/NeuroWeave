# NeuroClaw reuse inventory

NeuroWeave currently uses a local snapshot from:

```text
D:\reference_projects\NeuroClaw-main
```

The source directory was not a Git checkout when the snapshot was imported, so no upstream commit hash was available. Snapshot date: 2026-09-01.

## Reused directly

- All 99 upstream `skills/*/SKILL.md` directories
- Skill-owned `scripts/`, `agents/`, handlers, reference files and requirements files
- `core/skill_loader/loader.py`
- `core/skill_loader/validate_dag.py`
- `core/web/static/skill_summaries.json`
- NeuroClaw's MIT license text

The two Python compatibility modules are kept under `bakend/app/neuroclaw_compat/`. NeuroWeave's `app/skill_loader.py` is an adapter that adds caching, provenance, script counts and API-safe serialization while delegating discovery and front-matter parsing to the reused loader.

## Local additions

NeuroWeave adds four platform-level examples: `dataset-inspector`, `table-cleaning`, `image-batch-processing`, and `report-builder`. The active catalog therefore contains 103 skills in total.

## Execution boundary

Imported Skill documents, scripts, and command examples are discovery and planning evidence; they are never executed directly from model output. A method becomes executable only after NeuroWeave maps it to an explicitly registered trusted Runner, validates the server runtime and inputs, and passes Dry-run review. Skills without that reviewed mapping remain planning-only. Environment-oriented skills such as `claw-shell`, `conda-env-manager`, `dependency-planner`, and `docker-env-manager` are reference-only and cannot mutate server environments.

## Refreshing the snapshot

```powershell
cd D:\reference_projects\LocalFlow
.\scripts\sync-neuroclaw.ps1
```

The sync is additive/update-only: it copies current upstream content but does not delete NeuroWeave-owned skills.
