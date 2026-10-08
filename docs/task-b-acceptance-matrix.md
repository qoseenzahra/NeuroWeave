# Task B Acceptance / Wiring Matrix

## Implemented on the B branch

| Area | Guard / contract | Tests |
|---|---|---|
| Private/project resources | owner/project authorization and allowed actions | test_access_policies.py |
| Permission filtering | unauthorized objects removed before count/pagination | test_access_policies.py |
| Directory grants | explicit READ/WRITE grants | test_filesystem_authorization.py |
| Directory overlap | parent/child and duplicate roots rejected | test_filesystem_authorization.py |
| File proposals | initiator, project, grant revision, file revision rechecked | test_filesystem_authorization.py |
| Execution | submitter/project/input/output/quota/unit checks | test_execution_authorization.py |
| Execution management | member cannot manage another user's task | test_execution_authorization.py |
| Frozen execution scope | accepted plan stores authorization revision/scope | test_execution_authorization.py |
| Background operations | current identity and membership rechecked | test_background_authorization.py |
| Model tools | current user/project/resource policy rechecked | test_model_tools_authorization.py |
| Frontend actions | server-provided allowed_actions only; scope isolation key | authorization.test.ts |

## Required wiring with Developer A

1. Implement IdentityReader from A's authoritative identity/membership contracts.
2. Inject it into AuthorizationService and BackgroundOperationGuard.
3. Provide authoritative disabled-account and project-archival state.
4. Connect the common audit sink.
5. Put submission/quota reservation and file confirmation inside the shared transaction boundary.
6. Pass server-generated allowed_actions to business resource responses.
7. Re-check authorization in actual routes/services, including autosave, retry, cancel, restore, trash and background jobs.
8. Mount frontend access components into A-owned management pages without modifying A-owned entry points concurrently.
9. Replace test-only factories with A's real identity/project membership implementation.
10. Run the full backend/frontend test suites after integration.

## Security invariants

- Never trust frontend-supplied user IDs or roles.
- No production fake identity headers, default-admin bypass, or session bypass.
- No long-lived authorization cache.
- Filter unauthorized resources before pagination/counting.
- Private resources are nonexistent to unauthorized users, including direct-ID access.
- Accepted execution grants remain frozen; later revocation blocks new work but does not require browser state.
- Accepted grants cannot expand inputs, directories, outputs, or submit new tasks.
- Do not change the scientific algorithms or task state machine.
