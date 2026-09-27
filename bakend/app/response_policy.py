"""Separate conversational purpose from scientific execution capability.

This is semantic model output, not keyword routing or permission to execute.
Only plan/revise may enter graph planning; the Runner retains its own approval.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ResponsePolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['answer', 'explore', 'inspect', 'plan', 'revise', 'clarify'] = 'answer'
    relation: Literal['independent', 'continue', 'switch'] = 'independent'
    focus: str = Field(default='', max_length=800)
    needs_catalog: bool = False
    needs_files: bool = False
    # An invitation to request a draft is conversational, never an execution grant.
    offer_workflow: bool = False

    @property
    def plans(self):
        return self.action in {'plan', 'revise'}

    @property
    def needs_tools(self):
        return self.needs_catalog or self.needs_files or self.action == 'inspect'

    @classmethod
    def from_intent(cls, intent):
        # Older/offline intent producers omit policy. Keep their declared intent,
        # never upgrade a valid conversational decision from lexical hints.
        if intent.get('response_policy') is not None:
            return cls.model_validate(intent['response_policy'])
        return cls(action='plan' if intent.get('decision') == 'task' else 'answer',
                   needs_catalog=intent.get('decision') != 'task')


POLICY_PROMPT = """
Decide the conversational purpose before deciding whether to build a workflow.
Task mode enables tools and planning; it does not require a workflow on every turn.
Use response_policy with these fields:
- action: answer (explain/interpret/converse), explore (compare approaches, trade-offs,
  feasibility or next-step choices), inspect (query files or request file management),
  plan (an actionable request for a new reviewable workflow), revise (an actionable
  change to a prior workflow), or clarify (a material ambiguity prevents a useful answer).
- relation: continue (explicit/implicit reference to current work), switch (change of
  topic or goal), independent (no dependence on the previous workflow).
- focus: resolve references such as "that method", "instead", "the second option"
  using recent discussion and actual workflow state. State what THIS turn asks for.
- needs_catalog: true if the answer needs platform-specific methods, parameters,
  availability, or input/output facts; false for a general conceptual explanation.
- needs_files: true only if file/dataset inspection is actually relevant/requested.
- offer_workflow: true for answer/explore when the user discusses a concrete processing
  goal and a proposed approach could be turned into a reviewable workflow. This includes
  discussing missing inputs, alternatives or feasibility without requesting a plan yet.
  It is an invitation only, not decision=task. False for greetings, pure definitions,
  file listings/management, already requested plans, unresolved goals with no useful
  approach, or when the user asks for no follow-up suggestions.
These are response strategies, not a fixed sequence of stages. A user may move freely
between them. Do not classify by question words, language, or keyword occurrence.
"What if I have no parcellation?" can ask for alternatives; it is NOT automatically
permission to append producers. Explain viable choices before a route is selected.
"Generate the missing parcellation" requests a plan; "why is it necessary?" requests
an explanation. "Drop SIFT2", "use a different algorithm", "change the target" and
"first do only this step" have different scopes; resolve the actual intent.
For explore, explain reasonable scientific approaches even if the platform cannot yet
automatically compose them. Distinguish scientific feasibility, registered methods,
validated workflow construction, and runtime availability. They are different facts.
Set decision=task ONLY for plan/revise; all other actions are conversational. A method
name, selected Skill, missing input or keyword hint alone never requires planning.
In continue, retain still-relevant explicit user restrictions and honor current changes.
In switch/independent, do not inherit an old goal or its unrelated input restrictions.
An uncertain choice can be answered with options. Clarify only when proceeding would
choose between materially different user goals; do not repeatedly ask for file paths.
If the user asks both a question and for a concrete plan, plan/revise and address the
question in the explanation. Nothing here authorizes execution or filesystem changes.
"""


def response_guidance(policy):
    if policy is None:
        return ''
    invitation = ''
    if policy.offer_workflow and policy.action in {'answer', 'explore'}:
        invitation = (
            "\nAfter answering, end with ONE short, optional planning invitation in the user's language. "
            "Give a complete request the user can copy/send, tailored to the goal, approach, inputs "
            "and restrictions actually discussed in THIS answer. For example: "
            "如果你需要按上述方案生成可审阅的流程，请发送：‘请基于已有 T1w，用 FreeSurfer 生成解剖脑区分区；保留现有纤维追踪结果，不重新追踪。’ "
            "The example is a format, NOT a default recommendation. Never introduce its software, "
            "inputs or restrictions unless they match this conversation. Avoid vague requests like "
            "继续 or 按上面做. If several approaches remain, name one explicitly as an option, "
            "not as the user's selected route. State any material integration/availability uncertainty "
            "in the answer; an invitation does not promise that every proposed step is executable. "
            "Generating a draft still requires input binding, parameter review and dry-run; it never "
            "starts computation. Do not say a workflow has already been created.")
    return ("\nCurrent response policy (server-selected): " + policy.model_dump_json() +
            "\nAnswer the current question directly. For answer/explore, do not claim a workflow "
            "card is needed or missing, do not auto-append steps, and do not treat a platform "
            "integration gap as scientific impossibility. Use queried catalog/file facts for "
            "platform-specific claims; label general alternatives and unresolved assumptions. "
            "For plan/revise, explain requested changes and leave execution to explicit UI confirmation. "
            "A revised workflow is a new reviewable draft, not a silent edit of the old plan. "
            "For switch/independent, do not inherit unrelated old workflow goals or restrictions. "
            "An exhausted/failed/partial query is not proof of absence. If requested file facts "
            "were not observed, explicitly say they remain unverified; never guess directory contents." + invitation)


class PlanningAlternative(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    method_ids: list[str] = Field(default_factory=list, max_length=8)
    explanation: str = Field(min_length=1, max_length=1200)
    limitation: str = Field(min_length=1, max_length=800)


class PlanningAdvice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    explanation: str = Field(min_length=1, max_length=1600)
    alternatives: list[PlanningAlternative] = Field(default_factory=list, max_length=3)
    question: str = Field(default='', max_length=400)
