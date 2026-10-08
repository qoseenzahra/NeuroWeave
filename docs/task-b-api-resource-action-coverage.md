# Task B — API / Resource-Action Coverage

| Entry point | Required authorization | Foundation |
|---|---|---|
| Conversations/messages | owner/project scope + current identity | AuthorizationService |
| Datasets | read scope; mutation denied without grant | AuthorizationService |
| Outputs | read scope + write grant + confirmation | AuthorizationService |
| Tasks | owner/project role + submit/retry/cancel | AuthorizationService |
| Runs/logs/reports/artifacts | inherit parent permissions | AuthorizationService |
| Pipeline draft/version/source/trash | owner/project policy | AuthorizationService |
| Historical results | parent dataset/task permission | AuthorizationService |
| File preview/export | directory/read scope | AuthorizationService |
| File mutation | write grant + human confirmation | Integration required |
| Background/autosave | re-check current identity at execution | Integration required |
| Model tools | current user/project scope | Integration required |

## Non-negotiable rules

1. Never authorize from frontend-supplied user IDs or roles.
2. Never use a long-lived permission cache for business authorization.
3. Filter unauthorized records before pagination/counting.
4. Private resources are invisible to non-authorized users, including direct-ID access.
5. Accepted execution snapshots retain their frozen scope; revocation blocks new work.
6. Built-in catalogs remain read-only/trusted, while execution still checks inputs, outputs and quota.
