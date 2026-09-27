# Historical chat scrolling and follow-up fix — 2026-09-26

This is the diagnosis and deployment record for that patch. The input-only
follow-up strategy and missing-parcellation limitation described below were later
revised: see [flexible dialogue](flexible-dialogue.md) and
[method contracts](method-contracts-and-invitations.md). They are not current
capability claims or instructions to restore the old routing policy.

Sending a message now scrolls only the chat viewport. `appendLocal` enables tail
following and the existing layout effect updates that viewport after rendering.
It no longer calls `scrollIntoView`, which could scroll the clipped outer app as
well as the message list. Reading older history and editing workflow parameters
retain their existing scroll behavior.

## Follow-up routing

The inspected conversation initially returned a tractography/connectome workflow.
Its follow-up about missing brain parcellation entered the generic tool loop,
performed 14 queries across eight rounds, and returned a budget-limit message.
The planning phase was never reached. The original tool reply also discarded the
initial routing trace, making this hard to diagnose from persisted messages.

The server now loads a compact view of the conversation's actual workflow for each
turn: selected methods, required inputs, binding sources, missing input slots,
task constraints, excluded capabilities and revision. This context is rebuilt
from server records, ignores client-supplied internal state and is not carried
across datasets. Selected bindings are not treated as proof of file validity.

A request to obtain/replace a missing prerequisite is interpreted against this
context. Pure explanations and file queries remain ordinary chat. A tool handoff
or exhausted query budget preserves bounded, valid JSON observations and triggers
one intent reassessment. It does not restart the query loop or force a workflow.
Pending file-operation proposals retain their confirmation requirement and do
not enter planning. Duplicate queries are not executed again. Routing decisions
and traces are persisted for ordinary tool answers as well as workflow answers.

Method lookup ranks matches to any query term, including declared input/output
types. Thus bilingual synonyms such as `connectome 连接组` do not require both
languages to appear in the same description. An explicit Skill scope is retained;
the response tells the model how to search the full catalog when needed.

## Separate method-contract limitation

Isolated replay reaches the planner and finds FreeSurfer/MRtrix-related methods.
At the time of that replay, the registry had no method output explicitly typed as
`parcellation_image`. FreeSurfer reconstruction then registered a subject
directory, and relevant general-purpose commands do not establish the complete
typed path into `tck2connectome`.

The planner correctly rejects substituting a supposedly existing parcellation
when the user says it is unavailable. The failure now identifies the missing
output contract rather than suggesting that no command exists or only asking for
a retry. Completing that scientific chain requires specific output registration
and appropriate spatial-transform contracts. This patch does not invent an
algorithm, relax type validation, or present a partial chain as a complete one.

## Verification and deployment scope

- Local backend: 358 passed, 3 skipped, 694 subtests passed.
- Frontend: 47 tests passed; TypeScript and production builds passed.
- Server isolated regression: 51 passed, 3 subtests passed.
- Server isolated model replay: the actual follow-up reaches planning and returns
  the precise contract limitation. A positive control returns the single
  `mrtrix.tckgen` workflow with ACT disabled.
- Browser automation could not load the server page (connection timeout); a real
  browser check of the scroll behavior remains unverified.
- The deployment candidate applies this patch to a captured server baseline,
  preserving other server code. It also restores two already-existing frontend
  dependency files missing from the deployed source tree, allowing it to build.
- Deployment checks live hashes, gates mutations, requires idle run/Slurm queues,
  backs up source/config/database, creates a new immutable worker package, and
  retains old assets, output files, workers and history. Only the 3002 test
  backend is restarted; the main service is not changed.

Private replay artifacts and deployment reports remain in
`/home/hipeson/.cache/neuroweave/chat-followup-20260926/` and are not committed.

Deployed on 3002 as `chat-followup-26392fb5b89a`. All 12 deployed source
hashes and the bilingual method query were checked after restart. The original
conversation still contains its four original messages; all three historical run
records are preserved. Main service PID was unchanged.
