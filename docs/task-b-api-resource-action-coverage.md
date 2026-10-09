# Task B — API / Resource-Action Coverage

This document distinguishes **wired behavior** from policy helpers that still need integration. A helper or component alone is not evidence that a production business flow is protected.

| Entry point | Required authorization | Current branch evidence/status |
|---|---|---|
| Conversation create/list | current identity; filter private resources before pagination | Wired in conversation API/service; anonymous GET/POST expected 401; list filters policies before page slicing |
| Conversation direct read/update/delete/compact | owner/project scope; conceal unauthorized private IDs | Wired in conversation service/routes; unauthorized resource IDs map to 404; workspace binding checks UPDATE first |
| Existing conversation chat turn | current identity + write permission on target conversation | Wired in `begin_turn`; requires UPDATE before appending user message |
| Message-level endpoints / recovery | parent conversation permission and recipient re-check | Not separately verified end-to-end |
| Datasets | read scope; mutation denied without grant | Policy foundation only; route/service integration required |
| Outputs | read scope + write grant + confirmation | Policy foundation only; route/service integration required |
| Tasks | owner/project role + submit/retry/cancel | Helper tests only; real task lifecycle integration required |
| Runs/logs/reports/artifacts | inherit parent permissions | Not yet verified end-to-end |
| Pipeline draft/version/source/trash | owner/project policy | Policy foundation only; real route integration required |
| Historical results | parent dataset/task permission | Not yet verified end-to-end |
| File preview/export | current directory/read scope | Grant helpers exist; actual file-flow integration required |
| File mutation/restore/confirmation | current write grant + human confirmation + atomic recheck | Proposal helpers exist; actual file-flow integration required |
| Background/autosave | re-check identity, membership, project and resource revision | Guard helper exists; real worker integration required |
| Model tools and usage audit | current user/project/resource scope and recipient; persist usage/audit | Authorizer helper exists; real model/tool integration required |
| User/project switch cleanup | scoped persistence, cancel stale requests, ignore late responses | Scoped helper/hook exists; application-level invocation by A remains required |

## Non-negotiable rules

1. Never authorize from frontend-supplied user IDs or roles.
2. Never use a long-lived permission cache for business authorization.
3. Filter unauthorized records before pagination/counting.
4. Private resources are invisible to non-authorized users, including direct-ID access.
5. Accepted execution snapshots retain their frozen scope; revocation blocks new work but does not retroactively cancel accepted jobs.
6. Built-in catalogs remain read-only/trusted, while execution still checks inputs, outputs and quota.
7. The production identity reader remains fail-closed until Developer A injects the authoritative session, account, project-membership and archival contracts. Test doubles are used only in tests.
