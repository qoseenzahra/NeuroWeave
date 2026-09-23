# Skill / Method / Pipeline quality gates

The catalog has two Skill groups: task orchestration and software selection.
Repeated software wrappers are aliases, excluded from listings and recommendations.
Canonical Skills own applicability, selection rules, limitations and optional examples;
method references explain the role of an implementation without overriding its contract.
Saved alias selections resolve to the canonical Skill. The original alias directories
are retained; no deployed files or scientific outputs need to be deleted.

Method JSON remains authoritative for parameters, ports and execution adapters.
Registry loading rejects invalid defaults, option values, ranges, condition references,
conflict references and duplicate identities. `scripts/check_release.py` also rejects
missing parameter/port descriptions and methods absent from canonical Skills.
Existing adapter arguments and algorithms are unchanged by documentation enrichment.

## Evidence states

Both Method detail APIs return `verification`. Contract checks, description coverage,
live runtime availability and actual execution evidence are separate facts.
`not_recorded` means no matching record, not a failed execution.
`stale` means the definition or execution source changed after testing.
Synthetic execution does not establish scientific validity on a real dataset.

Evidence lives in `deploy/method-verification/<method-id>.json`. Each record binds
the method version and an execution fingerprint (full definition + execution Python
sources) to a SHA-256 checked report under `deploy/method-verification/reports/`.
It includes `method_id`, `method_version`, `execution_fingerprint`, `report_path`,
`report_sha256`, `test_type` (`synthetic` / `real_dataset`), `tested_at`, `environment`,
and `result` (`passed` / `failed`). Invalid or outside-root reports never count as passes.
Only trusted release tooling writes evidence; the browser/model cannot mark a method
verified. Historical tests without a bound report are not promoted to verified status.

## Contributor checks

Run `python scripts/build_skill_layers.py` and `python scripts/build_capability_tree.py`
after changing Skill guidance. Run `python scripts/audit_method_documentation.py
--output deploy/skill-runtime/method-documentation.json` and `python scripts/check_release.py`
before committing. Extend meaningful runner tests when changing execution behavior.
Parameter/port/algorithm changes require updated contracts and dependent pipelines;
adding a software executable to PATH alone never creates an executable Method.

## Verification recorded for this branch

The 2026-09-23 isolated server check ran 12 registered MRtrix commands and the
independent tckgen -> tcksift2 chain with small synthetic inputs. Thirteen Methods
have matching evidence records; the remaining 236 are explicitly not recorded for
this version. No web deployment, service restart or dataset job was involved.
Reproduce in a fresh checkout with the scientific Python environment:

```bash
/opt/neuroweave/envs/scientific-py311/bin/python scripts/smoke_mrtrix_commands.py \
  --work-dir /an/explicit/new/empty/directory --record-evidence
```

Review the generated reports before committing them. This does not certify every
option combination, GPU execution, real-data correctness or all software under /opt.

Final local checks: backend 310 passed, 3 skipped, 608 subtests passed; frontend
45 passed; TypeScript/Vite build, ESLint and release structure checks passed.
The Vite build still reports its existing >500 kB chunk warning.
