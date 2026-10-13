# Task B Acceptance / Wiring Matrix

## Review issues (snapshot 4fedbfa) and how they are closed

| # | Issue | Fix | Tests |
|---|---|---|---|
| 01 | Anonymous sensitive-file access | filesystem router requires identity; proposals bound to initiator; confirm rechecks | `test_anonymous_callers_cannot_read_sensitive_files_or_modify_outputs`, `test_sensitive_read_proposal_is_bound_to_its_initiator` |
| 02 | Anonymous file modifications | same, plus live WRITE grant for registration/mkdir/mutations and overlap checks | `test_new_user_without_grants_does_not_inherit_global_roots`, `test_output_registration_rejects_duplicate_and_nested_directories` |
| 03 | Chat submission fails before HTTP | `submitTurn` resolves the trusted scope itself | `frontend/tests/task-b-authorization.test.mjs` (issue 03 case) |
| 04 | Private chat results exposed / replay | turns bound to owner; recipient check on read/retry/cancel; replay → 409 | `test_private_chat_results_are_not_exposed_or_replayable`, `test_tool_events_are_private_to_the_turn_owner` |
| 05 | Business APIs not integrated | every router behind identity + object checks (see coverage document) | parametrized anonymous test; dataset/task/run/operation isolation tests |
| 06 | Revoked grant falls back to cache | live provider authoritative; durable grant store with revisions | `test_filesystem_authorization.py`, `test_write_grant_revocation_invalidates_pending_confirmation` |
| 07 | Background guard skips checks | explicit denial authoritative; resource-bound operations require the target | `test_background_authorization.py` |
| 08 | Late responses not isolated | epoch-bound requests; discard late payloads; cache/turn cleanup; scope-bound drafts | frontend test (issue 08 case, cleanup, drafts) |
| 09 | Task authorization and quotas | SUBMIT/RETRY/CANCEL, durable cross-process reservations, idempotency, frozen scope, cancellation actor | `test_concurrent_submissions_cannot_exceed_durable_quota`, `test_run_submission_freezes_scope_and_blocks_other_users`, … |
| 10 | Joint integration incomplete | request identity adapter, project header, business audit sink forwarding to A, settings components and cleanup hook mounted | `test_request_identity.py`, `test_business_audit_records_events_without_file_contents`, `test_directory_grant_administration` |
| 11 | Pagination truncates authorized rows | visible set applied in SQL before LIMIT/OFFSET (tasks, runs, history), keyset scan for conversations | `test_authorized_tasks_are_not_truncated_by_pagination` |
| 12 | Handover keeps creator privileges | only the manager has management rights; handover endpoint | `test_access_policies.py`, `test_handover_moves_management_and_former_creator_loses_it` |
| 13 | Migration tooling | read-only report fixed; explicit, atomic assignment tool (dry run by default) | `test_task_b_scope_report.py`, `test_ownership_tool_is_dry_run_by_default_and_applies_atomically` |
| 14 | Tests duplicate helpers | frontend tests load the real modules; backend tests drive the real app | both suites |

## Review round 2 (professor feedback) and how it is closed

| # | Feedback | Fix | Tests |
|---|---|---|---|
| R1 | File access and submissions still work after a grant is revoked | Dataset file reads, output file reads and chat inputs need a *live* directory grant on top of object ownership; sensitive-read and write proposals carry a grant token that confirm re-checks; run submission and retry need live READ grants on every input path (frozen into the run as `input_paths`) | `test_revoked_read_grant_blocks_dataset_file_access`, `test_revoked_write_grant_blocks_output_file_reads`, `test_write_grant_revocation_invalidates_pending_confirmation` |
| R2 | Background work continues after an account is disabled | `OperationContext.authorize` re-checks the initiator (same user, enabled, still a member, still allowed on the target) when work starts, at checkpoints, right before every commit (`checkpoint(commit=True)`) and before a result is delivered. Dataset register/inspect jobs, dry-run jobs, maintenance inventory and chat planning all pass a guard. A lost permission ends the job as `failed` with code `permission_revoked`; nothing is committed | `test_operation_fails_closed_when_permission_is_lost`, `test_background_guard_rejects_disabled_or_switched_actor` |
| R3 | Sharing dependency checks incomplete | `access/dependencies.py` supplies the real graph: a task depends on its dataset, output directory and the tasks of historical runs it reads. Sharing a task needs those shared first; unsharing a dataset/output/task that a shared task uses is refused; handover needs the new manager to be able to read every dependency | `test_sharing_a_task_requires_its_real_dataset_to_be_shared`, `test_handover_requires_recipient_access_to_dependencies` |
| R4 | Follow Task A's identity, role, permission and audit structure | `identity/contracts.py` is the agreed Task A contract (`ActorContext`, `ProjectAccess`, `IdentityReader` with `connection=`, `AuditEvent`, `AuditSink`, fixed enums). B imports A's enums instead of defining its own; `ContractIdentityReader` adapts A's reader; archived projects are read-only; a Project Administrator managing a member's work must give an audited reason (`X-NeuroWeave-Reason`); identity and membership revisions invalidate stale proposals; audit events go to A's sink as `AuditEvent` inside the same transaction, with the execution identity | `test_contract_identity_reader_maps_task_a_types`, `test_archived_project_is_read_only`, `test_project_administrator_needs_a_reason_to_manage_member_work` |
| R5 | Frontend: account switching, chat recovery, permission controls | A 401 dispatches `neuroweave:identity-changed`; project switches keep each scope's pending turns (only a sign-out or another account clears them); turns the server reports as 403/404 are dropped; a rejected submission is not kept for recovery; task edit/run/retry/cancel/resume controls follow the server's `allowed_actions` (`useResourceActions`, fail-closed); the HTTP client asks for an administrative reason and retries once | `frontend/tests/task-b-authorization.test.mjs` (project switch, rejected submission + 401, administrative reason) |
| R6 | Quotas, worker permissions, transactions | The reservation is bound to the run *before* the worker starts (`on_created`); the worker refuses to start a run without a reserved, matching frozen grant (plan revision, output root, execution identity); identity, membership and task/output permission revisions are re-validated *inside* the `BEGIN IMMEDIATE` quota transaction; quotas add per-unit time limits and allowed Slurm partitions | `test_quota_time_limit_and_partitions_are_enforced`, `test_reservation_revalidates_identity_inside_the_transaction`, `test_worker_refuses_runs_without_a_matching_frozen_grant`, `test_run_submission_freezes_scope_and_blocks_other_users` |

Already-running computation is never stopped by these checks: revocation blocks *new* work (new steps of a not-yet-started run, new submissions, retries, commits of background checks); recovery of submitted Slurm jobs does not pass the launch guard.

## Additional brief items

| Brief item | Implementation | Tests |
|---|---|---|
| B5 external-model file-text policy | `ModelGovernance.redact_tool_result`, settings switch | `test_external_model_file_text_policy_and_usage_records`, `test_model_policy_api_permissions` |
| B5 call and token usage records | `model_usage` table, `model.call` audit | same |
| B6 sharing/handover/takeover for data, outputs, Pipelines | `ResourceAccessCard` | frontend Task B test |
| §5 cleanup of obsolete records | `scripts/task_b_cleanup_records.py` (dry run by default, unassigned records only, database rows only) | `test_cleanup_removes_only_unassigned_unused_records` |

## Wiring checklist for Developer A

B supplies everything below; A only connects its own implementation.

1. **Identity (preferred).** Implement `identity.contracts.IdentityReader` (`current_actor`, `project_access`, `project_access_for`, each accepting `connection=`) and pass it as `build_services(settings, identity_reader=a_reader, audit_sink=a_sink)`; bootstrap wraps it in `ContractIdentityReader`. Bump `identity_revision` when an account is disabled or its role changes and `membership_revision` when a membership changes; B uses them to invalidate pending proposals and submissions.
   **Identity (alternative).** Implement `access.request_context.IdentityAuthority` in A's identity module:
   `resolve_session(request)` (cookie → opaque session), `identity_for_session(session)` (live check: disabled account or revoked session → `None`), `membership_for(user_id, project_id)` (archived project or removed member → `None` or `active=False`). Then call
   `build_services(settings, identity_reader=RequestIdentityReader(authority), audit_sink=a_common_audit_sink)`.
   The middleware that binds the session and project scope is already installed by `create_app`.
2. **Platform role.** Return `Identity(user_id, enabled, platform_role=PlatformRole.ADMIN|USER)`.
3. **Common audit.** Pass A's `AuditSink` as `audit_sink`; B's events are forwarded and also kept in `business_audit_events` so nothing is lost before that.
4. **Schema order.** `LocalStore` calls A's `initialize_store` and then B's `initialize_access_schema` (additive; assigns no ownership).
5. **Shared HTTP client.** `api/http.ts` now sends `X-NeuroWeave-Project` from `businessScope.scopeHeaders()` and binds each request to the scope epoch; A keeps cookie/CSRF/401 handling there.
6. **Identity/scope changes.** A's project selector calls `selectProject(projectId)`; logout/login should dispatch `neuroweave:identity-changed` (or call `refreshBusinessScope()`). `useBusinessScopeSync` (mounted in `App.tsx`) then runs `cleanupBusinessContext` in this order: epoch bump (aborts old requests) → cancel + remove cached queries → clear pending chat turns → `neuroweave:business-scope-changed` event.
7. **Management pages.** `AccessSettingsSection` (directory scope, output write grants, execution limits) is mounted in the Settings dialog; A may move it into its administration pages. `ResourceAccessCard` provides share/handover/takeover for one resource.
8. **Existing records.** Before release run `scripts/task_b_resource_scope_report.py <db>`, produce a mapping (`task_b_assign_ownership.py <db> --template`), review it, dry-run it, then `--apply`. Unassigned records stay invisible.
9. **External models.** `NEUROWEAVE_ALLOW_FILE_TEXT_TO_EXTERNAL_MODEL` (default `true`, the previous behavior) sets the default; personal and project policies override it.
10. **Default quotas** for new users come from `NEUROWEAVE_DEFAULT_CONCURRENT_UNITS`, `..._MAX_CPUS_PER_UNIT`, `..._MAX_MEMORY_GB_PER_UNIT`, `..._MAX_GPUS_PER_UNIT` (restricted defaults 2 / 8 / 32 / 0) and optional `NEUROWEAVE_DEFAULT_MAX_TIME_MINUTES`. Quotas per user/project can also limit time per unit and Slurm partitions.
12. **Administrative reasons.** A's administration UI may call `setAdministrativeReasonPrompt(fn)` from `api/http.ts` to replace the default browser prompt.
11. **CI.** No new dependencies. Backend: `pytest bakend/tests`. Frontend: `npm test` (the Task B test uses Vite's SSR loader like the other tests).

Files that are A-owned but were touched to make B's behavior reachable (please review): `application.py`, `bootstrap.py`, `application_services.py`, `local_store.py` (schema hook and ownership hook), `store_schema.py` (unchanged), `App.tsx`, `main.tsx`, `api/http.ts`, `components/SettingsPanel.tsx`, `identity/contracts.py` (the agreed contract; A owns it and may extend it compatibly), `operation_context.py`, `operation_service.py`, `execution/run_service.py` (`on_created` and `launch_guard` hooks only; state machine unchanged).

## Security invariants

- Never trust frontend-supplied user IDs or roles.
- No production fake identity headers, default-admin bypass, or session bypass.
- No long-lived authorization cache.
- Filter unauthorized resources before pagination/counting.
- Private resources are nonexistent to unauthorized users, including direct-ID access.
- Accepted execution grants remain frozen; later revocation blocks new work but does not require browser state.
- Accepted grants cannot expand inputs, directories, outputs, or submit new tasks.
- Do not change the scientific algorithms or task state machine.
