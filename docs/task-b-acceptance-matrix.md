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

## Wiring checklist for Developer A

B supplies everything below; A only connects its own implementation.

1. **Identity.** Implement `access.request_context.IdentityAuthority` in A's identity module:
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
9. **Default quotas** for new users come from `NEUROWEAVE_DEFAULT_CONCURRENT_UNITS`, `..._MAX_CPUS_PER_UNIT`, `..._MAX_MEMORY_GB_PER_UNIT`, `..._MAX_GPUS_PER_UNIT` (restricted defaults 2 / 8 / 32 / 0).
10. **CI.** No new dependencies. Backend: `pytest bakend/tests`. Frontend: `npm test` (the Task B test uses Vite's SSR loader like the other tests).

Files that are A-owned but were touched to make B's behavior reachable (please review): `application.py`, `bootstrap.py`, `application_services.py`, `local_store.py` (schema hook and ownership hook), `store_schema.py` (unchanged), `App.tsx`, `main.tsx`, `api/http.ts`, `components/SettingsPanel.tsx`.

## Security invariants

- Never trust frontend-supplied user IDs or roles.
- No production fake identity headers, default-admin bypass, or session bypass.
- No long-lived authorization cache.
- Filter unauthorized resources before pagination/counting.
- Private resources are nonexistent to unauthorized users, including direct-ID access.
- Accepted execution grants remain frozen; later revocation blocks new work but does not require browser state.
- Accepted grants cannot expand inputs, directories, outputs, or submit new tasks.
- Do not change the scientific algorithms or task state machine.
