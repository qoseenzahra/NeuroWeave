"""A consented subset of original sample identities, shared by review and execution.

Only an explicitly applied partial historical binding enables this policy. The
intersection uses saved matching decisions; files changed since selection still
fail provenance/preflight checks rather than silently shrinking an approved run.
"""
from __future__ import annotations

from .workflow_models import SampleScope, SkippedSample, Workflow


def partial_sample_scope(workflow: Workflow) -> SampleScope | None:
    if not any(binding.history and binding.history.allow_partial
               for step in workflow.steps for binding in step.input_bindings.values()):
        return None
    dataset = workflow.dataset
    if not dataset or not dataset.inspection.samples:
        raise ValueError("部分样本运行需要完整的原始样本清单")
    samples = dataset.inspection.samples
    if (len(samples) != dataset.inspection.sample_count
            or len({s.sample_id for s in samples}) != len(samples)):
        raise ValueError("原始样本清单不完整或标识重复")
    reasons = {s.sample_id: [] for s in samples}
    for step in workflow.steps:
        method = next((m for m in step.method_options if m.id == step.selected_method_id), None)
        if method is None:
            continue
        for slot in method.input_slots:
            # Inactive conditional inputs do not narrow the selected algorithm.
            condition = all(step.selected_parameters.get(k) in values for k, values in slot.required_when.items())
            if slot.required_when and not condition and not slot.required:
                continue
            binding = step.input_bindings.get(slot.id)
            required = slot.required or (bool(slot.required_when) and condition)
            if binding is None:
                if required:
                    for messages in reasons.values():
                        messages.append(f"{step.title} / {slot.label}：尚未绑定必需输入")
                continue
            if binding.source == "upstream_output" or binding.binding_mode != "per_sample":
                continue
            matches = {}
            for match in binding.sample_matches:
                matches.setdefault(match.sample_id, []).append(match)
            for sample in samples:
                own = matches.get(sample.sample_id, [])
                if len(own) != 1 or own[0].status != "matched" or not own[0].absolute_path:
                    detail = own[0].message if len(own) == 1 else "没有唯一匹配的输入"
                    reasons[sample.sample_id].append(f"{step.title} / {slot.label}：{detail or '输入未匹配'}")
    return SampleScope(total=len(samples),
        eligible_sample_ids=[s.sample_id for s in samples if not reasons[s.sample_id]],
        skipped_samples=[SkippedSample(sample_id=s.sample_id, label=s.label, reasons=reasons[s.sample_id])
                         for s in samples if reasons[s.sample_id]])


def restrict_sample_bindings(workflow: Workflow, scope: SampleScope | None) -> Workflow:
    """Use a copy for preflight; retain full coverage and provenance in the plan."""
    if scope is None:
        return workflow
    selected = workflow.model_copy(deep=True)
    ids = set(scope.eligible_sample_ids)
    for step in selected.steps:
        method = next((m for m in step.method_options if m.id == step.selected_method_id), None)
        if method:
            for slot in method.input_slots:
                if (slot.required_when and not slot.required
                        and not all(step.selected_parameters.get(k) in v for k, v in slot.required_when.items())):
                    step.input_bindings.pop(slot.id, None)
        for binding in step.input_bindings.values():
            if binding.binding_mode != "per_sample":
                continue
            binding.sample_matches = [m for m in binding.sample_matches if m.sample_id in ids]
            if binding.history:
                binding.history.artifacts = [a for a in binding.history.artifacts if a.sample_id in ids]
    return selected
