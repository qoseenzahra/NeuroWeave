"""Resolve reviewed planning identities to existing calls, never infer an algorithm.

The catalog is an explicit, auditable mapping. Availability remains a runtime
decision; merely importing a similarly named package never creates a mapping.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .workflow_models import ExecutionRecipeSpec, MethodSourceReference


def source_fingerprint(method) -> str:
    # Presentation fields may be translated independently. Scientific scope,
    # parameters and input/output declarations must be re-reviewed on change.
    data = method.model_dump(mode='json', include={'method_id', 'skill_id', 'capability',
        'input_slots', 'output_slots', 'parameters', 'included_capabilities', 'description'})
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class PlanningResolver:
    def __init__(self, path: Path):
        self.path = path
        self.records = {}
        if not path.is_file():
            return
        payload = json.loads(path.read_text(encoding='utf-8'))
        if payload.get('schema_version') != 1:
            raise RuntimeError('Unsupported planning resolution catalog')
        for entry in payload['methods']:
            key = (entry['capability'], entry['method_id'])
            if key in self.records:
                raise RuntimeError('Duplicate planning resolution: ' + repr(key))
            self.records[key] = entry

    def resolve(self, methods, lookup):
        result = []
        native_keys = {(m.capability,m.method_id) for m in methods if m.execution_mode=='runner'}
        for source in methods:
            if source.execution_mode != 'planning':
                result.append(source)
                continue
            entry = self.records.get((source.capability, source.method_id))
            if entry is None:
                result.append(source.model_copy(update={'execution_resolution': {
                    'state': 'unreviewed', 'reason': '此规划尚未核对具体执行入口。',
                    'source_method_id': source.method_id}}))
                continue
            if entry['source_fingerprint'] != source_fingerprint(source):
                result.append(source.model_copy(update={'execution_resolution': {
                    'state': 'unreviewed', 'reason': '原规划的输入、参数或范围已改变，需要重新核对执行映射。',
                    'source_method_id': source.method_id}}))
                continue
            alternatives = entry.get('alternatives', [])
            if not alternatives:
                result.append(source.model_copy(update={'execution_resolution': {
                    'state': entry['state'], 'reason': entry['reason'],
                    'source_method_id': source.method_id,
                    'requirements': entry.get('requirements', [])}}))
                continue
            for alternative in alternatives:
                target = lookup(alternative['capability'], alternative['method_id'])
                if target is None or target.execution_mode != 'runner':
                    raise RuntimeError('Planning mapping requires an existing executable definition: '
                                       + repr(alternative))
                recipe = ExecutionRecipeSpec.model_validate(alternative['recipe']) if alternative.get('recipe') else None
                if recipe is None and (source.capability, target.method_id) in native_keys:
                    # A generic directory entry must not duplicate or displace an
                    # already selectable concrete implementation in the same menu.
                    continue
                if recipe is None:
                    parameters, inputs, outputs = target.parameters, target.input_slots, target.output_slots
                else:
                    parameters = recipe.parameters if 'parameters' in recipe.model_fields_set else [p for p in target.parameters
                        if not recipe.exposed_parameters or p.id in recipe.exposed_parameters]
                    inputs = recipe.input_slots or target.input_slots
                    outputs = recipe.output_slots or target.output_slots
                method_id = source.method_id if len(alternatives) == 1 else source.method_id + '--via-' + alternative['key']
                resolved = target.model_copy(deep=True, update={
                    'capability': source.capability, 'method_id': method_id, 'skill_id': source.skill_id,
                    'label': alternative.get('label') or source.label,
                    'description': alternative.get('description') or target.description,
                    'default_recommended': False, 'execution_recipe': recipe,
                    'parameters': parameters, 'input_slots': inputs, 'output_slots': outputs,
                    'input_types': [slot.type for slot in inputs], 'output_types': [slot.type for slot in outputs],
                    'included_capabilities': alternative.get('included_capabilities', target.included_capabilities),
                    'source_references': [*source.source_references, *target.source_references,
                        MethodSourceReference(path='bakend/resources/planning_resolution.json', kind='script',
                            label='已核对的规划执行映射', line_start=1)],
                    'execution_resolution': {'state': 'mapped', 'reason': entry['reason'],
                        'source_method_id': source.method_id, 'target_method_id': target.method_id},
                })
                result.append(resolved)
        return sorted(result, key=lambda m: bool(m.execution_resolution))
