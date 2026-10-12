# Task B — API / Resource-Action Coverage

Every business entry point below is wired in production code and covered by a test that goes through the real application (`bakend/tests/test_task_b_integration.py`, unless another file is named). Invisible objects answer **404** (never 403), so existence is not leaked. Anonymous requests answer **401**.

Shared entry point: `app/access/resources.py::ResourceAccess` (ownership, visibility, `allowed_actions`, share/handover/takeover). Routers call it through `app/api/guards.py`.

| Entry point | Rule (action checked) | Where |
|---|---|---|
| `GET /api/access/scope` | trusted identity; requested project must be an active membership | `api/access.py` |
| Conversation create / list / search / page | identity; private to manager; current personal/project scope; filtered **before** paging | `conversation_service.py` |
| Conversation read / rename / archive / delete / compact | READ / UPDATE / DELETE on conversation | `api/conversations.py` |
| Conversation ↔ output binding | UPDATE conversation + UPDATE output | `workspace_service.bind_conversation` |
| Chat submit `POST /api/chat`, `/api/chat/turns` | identity; UPDATE conversation; READ dataset/output in the request; turn bound to owner | `chat_turns.py` |
| Chat turn read / retry / cancel | turn owner (recipient check) + READ/RETRY/CANCEL on conversation | `chat_turns.py` |
| Replayed `client_turn_id` by another user | 409 without content | `chat_turns.submit` |
| Queued / in-flight chat turn | identity and owner rechecked when it starts and before the result is saved | `chat_turns._run` |
| Workspace tool events | only the turn owner | `workspace_routes.events` |
| Dataset roots / directory browsing | live READ grant; ancestors only show the path to grants | `api/datasets.py`, `access/directory_grants.py` |
| Dataset register (sync and background job) | READ grant on the directory; duplicate/overlapping registration in another scope → 409; owner recorded in the same transaction | `api/datasets.py`, `local_store.save_dataset` |
| Dataset list / read / inspect / workspace link | visible set / READ / UPDATE | `api/datasets.py` |
| Dataset file list / inspect / read / search (HTTP and model tools) | READ dataset | `dataset_files.DatasetFiles.reader` |
| Output directory register | live WRITE grant; no duplicate or parent/child overlap with any record | `workspace_service._guard_registration` |
| Output list / update / remove / trash list | visible set / UPDATE / DELETE / READ | `workspace_service.py` |
| `GET /api/fs/roots`, raw path list / inspect / read / search | only granted subtrees; nothing inherited from global roots | `workspace_service._authorize_path` |
| Workspace path list / inspect / read / search (HTTP and model tools) | READ output | same |
| File proposals: mkdir, copy, move, rename, delete, read-sensitive, restore | UPDATE output (READ for sensitive read) + WRITE grant; bound to initiator, project, output revision, grant revision | `workspace_service._proposal_binding` |
| Proposal read / confirm | initiator only; same project; output revision and grant revision unchanged; file fingerprints unchanged | `workspace_service._recheck_binding` |
| Background operations (`/api/operations/*`) | owner only; run with the initiator's request context | `operation_service.py` |
| Task index / list (My tasks, Project tasks) | visible set applied in SQL before LIMIT/OFFSET | `api/workflows.py`, `local_store.workflow_index` |
| Task read / events / execution-draft read | READ task | `api/workflows.py`, `api/execution.py` |
| Task draft creation | identity; READ dataset/output, UPDATE conversation; owner recorded on first save | `api/workflows.py`, `local_store.save_workflow` |
| Task edits: method, lock/unlock, dataset, step removal, replan, dependencies, parameters, review, inputs, output, execution-draft autosave, dry-run, confirm | UPDATE task (+ READ dataset / READ grant for typed paths / UPDATE output) | `api/workflows.py`, `api/workflow_inputs.py`, `api/execution.py` |
| Historical results (candidates, preview, bind, validation at submit) | READ on the source run's task; filtered before paging | `historical_inputs.py`, `run_store.historical_runs` |
| Run submission | SUBMIT task; current project = task project; READ dataset and historical runs; UPDATE output + live WRITE grant; durable quota reservation (`BEGIN IMMEDIATE`); idempotency key; frozen scope stored | `api/execution.py`, `access/execution_control.py` |
| Run retry | RETRY task; same checks against the original snapshot; new reservation | `api/execution.py` |
| Run cancel | CANCEL task; cancellation actor recorded | `api/execution.py` |
| Run read / events / monitor / authorization record | READ task | `api/execution.py` |
| FreeSurfer recovery / resume monitoring | READ (dry run) or RETRY / UPDATE | `api/execution.py` |
| User Pipelines: list, versions, source, migration review, trash | visible set / READ | `library_routes.py`, `pipeline_library.records` |
| User Pipelines: create, update, delete, restore, publish/archive | owner recorded / UPDATE / DELETE / RESTORE / PUBLISH | `library_routes.py` |
| Use a Pipeline to create a task | SUBMIT Pipeline (members may use project-shared ones) + READ dataset/output | `library_routes.use` |
| Save a task as a Pipeline | READ task; copy owned by the caller; no data access granted | `library_routes.from_workflow` |
| Pipeline drafts: list, save, autosave, delete, restore | private to owner; another user's draft id → 404 | `library_routes.py`, `pipeline_management.save_draft` |
| Built-in skills / methods / Pipelines / catalog | any logged-in user; read-only | `api/catalog.py` (mounted behind identity) |
| Model retrieval of user Pipelines | visible set only | `pipeline_library.bindings` → `records` |
| Share / withdraw sharing | SHARE; dependencies must be shared to the same project; revision bump | `api/access.py` |
| Handover | HANDOVER; recipient must be an active project member; former creator keeps attribution only | `api/access.py` |
| Platform takeover | platform administrator + reason (≥ 8 chars) + audit; a platform role alone gives no read access | `api/access.py` |
| Directory grants: mine / list / create / revoke | own / project administrator or platform administrator; project administrators can only delegate inside a platform-granted project root | `api/access.py` |
| Quotas: mine / read / update | own / platform administrator, project administrator for `project:<id>` | `api/access.py` |
| Maintenance storage / inventory | platform administrator | `api/health.py` |
| Liveness `/`, `/api/health` | anonymous (allow-list) | `api/health.py` |

## Frontend

| Concern | Rule | Where / test |
|---|---|---|
| Chat submission | resolves the authenticated scope itself; never fails before sending | `chat/chatTurns.ts` — `frontend/tests/task-b-authorization.test.mjs` |
| Late responses | every request is tied to the scope epoch; a switch aborts it and discards late payloads; chat progress from an old epoch is dropped | `api/http.ts`, `access/businessScope.ts` — same test |
| Query cache | hash includes user and scope; switch cancels and removes all cached queries and pending turns | `main.tsx`, `access/useScopeCleanup.ts` — same test |
| Draft recovery copies | bound to user and scope | `library/usePipelineDraft.ts`, `library/libraryApi.ts` — same test |
| Buttons and labels | server `allowed_actions`; takeover only for platform administrators | `access/authorization.ts`, `ResourcePolicyPanel.tsx` — same test |

## Non-negotiable rules

1. Never authorize from frontend-supplied user IDs or roles.
2. Never use a long-lived permission cache for business authorization.
3. Filter unauthorized records before pagination/counting.
4. Private resources are invisible to non-authorized users, including direct-ID access.
5. Accepted execution snapshots retain their frozen scope; revocation blocks new work but does not cancel accepted jobs.
6. Built-in catalogs remain read-only/trusted, while execution still checks inputs, outputs and quota.
7. The production identity reader remains fail-closed until Developer A injects the authoritative session, account, membership and archival contracts. Test doubles are used only in tests.
