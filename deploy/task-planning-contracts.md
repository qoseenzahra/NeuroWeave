# Task constraints and validated Method planning

This change addresses the 3002 conversation in which the user requested tractography
from preprocessed DWI, gradients and a mask, but received a preprocessing card.
The relevant MRtrix Methods were registered and available. Semantic normalization
failed; keyword fallback misinterpreted an existing input as an operation, assigned
confidence 1.0, and sealed the candidate set before the method planner ran.

## Current behavior

- A typed task contract records the desired output artifact types, permitted and
  forbidden existing inputs (optionally exact filenames/relative paths), forbidden
  operations, and whether necessary generated intermediates are permitted.
- `only_listed` permits no other existing input types. An excluded *existing* FOD
  may still be regenerated from authorized DWI. File discovery never grants reuse.
- Task normalization and JSON method planning get at most two attempts. Invalid
  JSON/schema and transient HTTP failures retry; authentication/client errors do
  not. Logs contain stage, attempt, error class and HTTP status, never credentials,
  request bodies or dataset file contents. Failure retains low confidence and
  returns no workflow instead of selecting a default operation.
- The graph prompt includes the actual Pydantic JSON Schema. A schema retry gets
  field locations/error codes (without input values); it does not repeat an
  identical failed request. External inputs are omitted from internal edge maps.
- For a known output goal, the Method index covers every native method regardless
  of Skill references. It joins real output/input types, starts with at most 24
  candidates/depth 3, and widens once to at most 64/depth 5. Tree matches rank ties;
  they do not exclude a method from another branch. Indexes refresh on definition
  changes. Only shortlisted contracts are sent to the model.
- Broad types (`generated_file`, `imaging_input`, etc.) are recorded as unresolved
  semantic boundaries, not expanded into every command accepting a file. The
  gradient-table parent and b-value/b-vector subtypes are checked using declared
  port formats; b-value permission alone never grants b-vector permission.
- The model produces a structured DAG, not independent explanatory prose.
  The existing Pipeline compiler validates method IDs, parameters, ports, types,
  cycles and conditional outputs. Additional checks verify permitted external
  inputs, target output production and that every node contributes to a goal.
- Exact output ports are preserved (WM/GM/CSF response files must not be substituted
  just because their artifact type is the same). Editing parameters rechecks
  conditional outputs and requirements. Constraint failures disable confirmation
  and are also enforced by backend lock/review/dry-run checks.
- The workflow stores the task contract and retrieval/validation diagnostics.
  Titles and summaries come from real steps. Unmatched or invalid candidates do
  not create a workflow or claim the software is absent. Existing histories and
  user-defined Pipelines remain readable; Runner submission behavior is unchanged.

## Retrieval diagnosis and next design

The tree is useful for navigation and fast coarse routing. The defect was treating
one selected branch as an exhaustive method inventory. The sparse retriever also
indexes Skill-level aggregate text, so command relevance can be diluted by broad
software descriptions. Metadata with only generic file types further weakens
automatic composition.

The long-term hybrid design should combine a Method-level inverted index (canonical
IDs, command aliases, labels, operations), semantic retrieval over descriptions,
and the output-contract index added here. Fuse and deduplicate by canonical ID;
use Skill/Pipeline descriptions for orchestration guidance. Rank relevance before
environment availability so a relevant unavailable method is reported separately
instead of replaced by unrelated runnable software. Check goal/operation coverage
before finalizing a shortlist; expand only uncovered operations with bounded pages.

This change implements the typed contract lookup and bounded recovery needed for
validated planning. It does not introduce an embedding provider or a new global
Method/Pipeline search service. Unknown output semantics and generic contracts still
require richer method metadata or further retrieval. No finite semantic search can
promise zero missed matches; budget exhaustion and insufficient metadata must stay
explicit and must never be reported as proof that no method exists.

## Validation and operations

Run `python -m pytest tests -q` from `bakend`, and `npm run build` / `npm test` from
`frontend`. Regression tests cover the exact reported request, transient/malformed
responses, input restrictions, gradient subtypes, wrong tree leaves, conditional
ports, output goals, extra steps, graph ordering, persisted workflows and edited
parameters. Synthetic contracts do not establish scientific suitability of an
algorithm for real acquisition data; users still review inputs and parameters.

No new environment variables or database migration are required. Before deploying,
compare affected server files against the local base revision, keep an exact backup,
and restart only the idle test service. Preserve runs, outputs and immutable Slurm
worker snapshots. No computational job is needed to validate planning.

Verification on 2026-09-23: the complete backend suite passed 329 tests (3 skipped,
611 subtests). After the final schema-feedback/goal-provenance correction, the 77
affected regression tests passed (121 subtests), including 21 new tests. Frontend
build and all 45 tests passed. Live-model isolated verification of the reported
request produced dwi2response -> dwi2fod -> tckgen with ACT disabled, using 10
candidate contracts from an index of 249 native Methods. Planning does not submit
jobs; scientific parameters still require review against the acquisition data.

The final 3002 HTTP smoke test also passed: the original user wording produced
`mrtrix.dwi2response -> mrtrix.dwi2fod -> mrtrix.tckgen`, reached `chain_ready`,
persisted the input contract and disabled ACT. The test conversation was archived;
no Runner job was submitted. Deployment retained three historical runs, preserved
the 3000 process, and verified the new worker snapshot on node01/node02/node03.
Release marker: `04683c8+planning-b80d9fe26f43`.
