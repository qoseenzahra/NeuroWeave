"""Typed, versioned pipeline composition. No user-supplied commands or code.

Public ports and parameter conditions are derived from registered Method contracts.
Saving a definition never submits a job; using it creates an ordinary reviewable workflow.
"""
from __future__ import annotations
import copy
import json
import re
import math
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field
from .pipeline_shared_inputs import merge_shared_inputs
from .parameter_rules import effective_parameters, matches
from .capability_registry import CapabilityMethod
from .workflow_models import ExecutionRecipeSpec, Workflow, WorkflowStep


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str
    output_slot_id: str


class ComposeStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,50}$")
    method_id: str
    parameters: dict = Field(default_factory=dict)
    inputs: dict[str, Link] = Field(default_factory=dict)


class InputPort(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str = Field(min_length=1, max_length=51)
    input_slot_id: str = Field(min_length=1, max_length=160)


class ComposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    steps: list[ComposeStep] = Field(min_length=1, max_length=50)
    shared_inputs: list[list[InputPort]] = Field(default_factory=list, max_length=500)
    expected_version: int | None = None


class UsePipeline(BaseModel):
    dataset_id: str | None = None
    workspace_id: str | None = None
    version: int | None = None


def remap_conditions(value, namespace):
    value = copy.deepcopy(value)
    for field in ('visible_when', 'required_when', 'enabled_when', 'generated_when'):
        value[field] = {namespace + key: options for key, options in value.get(field, {}).items()}
    if 'required_when_any' in value:
        value['required_when_any'] = [{namespace + key: options for key, options in condition.items()} for condition in value['required_when_any']]
    if 'conflicts_with' in value:
        value['conflicts_with'] = [namespace + key for key in value['conflicts_with']]
    return value


def check_parameter(spec, value):
    if value is None:
        return
    valid = (isinstance(value, str) if spec.type == 'string' else type(value) is bool
             if spec.type == 'boolean' else type(value) is int if spec.type == 'integer'
             else type(value) in (int, float))
    if type(value) in (int, float) and not math.isfinite(value):
        raise ValueError('数值必须有限：' + spec.id)
    if not valid or (spec.options and value not in [option.value for option in spec.options]):
        raise ValueError('参数类型或枚举值不合法：' + spec.id)
    if spec.minimum is not None and value < spec.minimum or spec.maximum is not None and value > spec.maximum:
        raise ValueError('参数超出范围：' + spec.id)


class PipelineLibrary:
    def __init__(self, store, registry):
        self.store, self.registry = store, registry
        with store._lock, store._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS pipeline_library (id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id, version))')

    def compile(self, request: ComposeRequest, identity='preview', version=1):
        if not request.name.strip():
            raise ValueError('名称不能为空')
        registry = self.registry.definitions
        registry.load()
        seen, consumed = {}, set()
        producer_values = {}
        inputs, outputs, parameters, steps, output_bindings = [], [], [], [], {}
        for step in request.steps:
            if step.id in seen:
                raise ValueError('步骤 ID 重复：' + step.id)
            method = registry.method(step.method_id)
            if self.registry.method_for('method', method.id) is None:
                raise ValueError('未注册的方法')
            specs = {p.id: p for p in method.parameters}
            if set(step.parameters) - set(specs):
                raise ValueError('包含方法未定义的参数')
            prefix = step.id + '__'
            for p in method.parameters:
                item = remap_conditions(p.model_dump(mode='json'), prefix)
                item.update(id=prefix+p.id, label=step.id+' · '+p.label, group=step.id)
                if p.id in step.parameters:
                    check_parameter(p, step.parameters[p.id])
                    item['default'] = step.parameters[p.id]
                parameters.append(item)
            bindings = {}
            if set(step.inputs) - {s.id for s in method.input_slots}:
                raise ValueError('包含方法未定义的输入')
            for slot in method.input_slots:
                link = step.inputs.get(slot.id)
                if link:
                    producer = seen.get(link.step_id)
                    output = next((s for s in producer.output_slots if s.id == link.output_slot_id), None) if producer else None
                    if output is None:
                        raise ValueError('输入必须连接到前面步骤的真实输出；不允许环或向后引用')
                    if output.type != slot.type:
                        raise ValueError(f'输入输出类型不匹配：{output.type} → {slot.type}')
                    if slot.cardinality != 'one':
                        raise ValueError('多个文件输入请作为 Pipeline 外部输入提供')
                    # Conditional ports are real ports. Validate their effective producer
                    # parameters now; RecipeCompiler checks them again before execution.
                    if not matches(output.generated_when, producer_values[link.step_id]):
                        expected = ', '.join(f'{key}={allowed}' for key, allowed in output.generated_when.items())
                        raise ValueError(f'{link.step_id}（{producer.label}）的输出 {output.label} 当前不会生成；'
                                         f'需要 {expected}，请调整上游参数或移除此连接')
                    bindings[slot.id] = {'source':'step_output','step_id':link.step_id,'output_slot_id':link.output_slot_id}
                    consumed.add((link.step_id,link.output_slot_id))
                else:
                    item = remap_conditions(slot.model_dump(mode='json'), prefix)
                    item.update(id=prefix+slot.id, label=step.id+' · '+slot.label)
                    inputs.append(item)
                    bindings[slot.id] = {'source':'workflow_input','slot_id':prefix+slot.id}
            steps.append({'id':step.id,'title':method.label,'capability':'method','method_id':method.id,
                          'method_ref':method.id,'method_version':method.version,'workspace':step.id,
                          'inherit_parameters':False,'fixed_parameters':{},
                          'parameter_bindings':{p.id:prefix+p.id for p in method.parameters},'input_bindings':bindings})
            seen[step.id] = method
            producer_values[step.id] = effective_parameters(method, step.parameters)
        inputs = merge_shared_inputs(request.shared_inputs, inputs, steps)
        for step_id, method in seen.items():
            for slot in method.output_slots:
                if (step_id,slot.id) in consumed:
                    continue
                item = remap_conditions(slot.model_dump(mode='json'),step_id+'__')
                item.update(id=step_id+'__'+slot.id,label=step_id+' · '+slot.label)
                outputs.append(item)
                output_bindings[item['id']]={'step_id':step_id,'output_slot_id':slot.id}
        payload={'schema_version':1,'id':identity,'version':str(version),'kind':'pipeline',
                 'label':request.name.strip(),'description':request.description,'category':['我的 Pipeline'],
                 'parameters':parameters,'input_slots':inputs,'output_slots':outputs,'steps':steps,
                 'output_bindings':output_bindings,'editor':request.model_dump(mode='json')}
        self.as_method(payload)  # Validate against the same recipe schema used by Runner.
        return payload

    @staticmethod
    def as_method(p):
        identity=p['id']+'@'+str(p['version'])
        recipe=ExecutionRecipeSpec.model_validate({**p,'recipe_id':identity,'operation_value':'',
            'interface_capability':'method','interface_method_id':p['steps'][0].get('method_ref',p['steps'][0].get('method_id')),
            'steps':[{**s,'method_id':s.get('method_ref',s.get('method_id'))} for s in p['steps']]})
        return CapabilityMethod(capability='library.'+identity,method_id=identity,skill_id='pipeline-library',
            definition_id=p['id'],definition_version=str(p['version']),entry_kind='pipeline',label=p['label'],
            description=p.get('description',''),runner_id='pipeline:'+identity,execution_recipe=recipe,
            parameters=recipe.parameters,input_slots=recipe.input_slots,output_slots=recipe.output_slots,
            input_types=[s.type for s in recipe.input_slots],output_types=[s.type for s in recipe.output_slots])

    def records(self):
        with self.store._connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM pipeline_library ORDER BY id, version')]

    def bindings(self):
        self.registry.definitions.load()
        return [self.as_method(p) for p in [*self.registry.definitions.pipelines.values(), *self.records()]]

    def get(self, identity, version=None):
        self.registry.definitions.load()
        if identity in self.registry.definitions.pipelines:
            return copy.deepcopy(self.registry.definitions.pipelines[identity])
        with self.store._connect() as db:
            row=db.execute('SELECT payload FROM pipeline_library WHERE id=? AND (? IS NULL OR version=?) ORDER BY version DESC LIMIT 1',
                           (identity,version,version)).fetchone()
        if row is None:raise KeyError('Pipeline 不存在')
        return json.loads(row[0])

    def save(self, request, identity=None):
        with self.store._lock, self.store._connect() as db:
            if identity is None:
                identity='user-'+uuid4().hex[:16];version=1
            else:
                row=db.execute('SELECT MAX(version) FROM pipeline_library WHERE id=?',(identity,)).fetchone()
                if row[0] is None:raise KeyError('只能更新用户 Pipeline')
                if row[0]!=request.expected_version:raise ValueError('Pipeline 版本已变化，请刷新后保存')
                version=row[0]+1
            p=self.compile(request,identity,version)
            db.execute('INSERT INTO pipeline_library VALUES (?,?,?)',(identity,version,json.dumps(p,ensure_ascii=False)))
            return p

    def catalog(self, kind, q='', offset=0, limit=50, category='', software='', language='zh'):
        from .catalog_taxonomy import catalog_entries, facets, category_labels
        items = [item for item in catalog_entries(self.registry.definitions, self.records()) if item['kind'] == kind]
        terms = q.casefold().split()
        # Index both locale projections, so switching language never hides a
        # canonical command, Chinese task phrase or English scientific term.
        from .catalog_locale import localize
        if terms:
            items = [item for item in items if all(term in (json.dumps(item, ensure_ascii=False) +
                json.dumps(localize(item, 'en'), ensure_ascii=False) +
                json.dumps(localize(item, 'zh'), ensure_ascii=False)).casefold() for term in terms)]
        software_facets = facets(items, language)['software']
        if software:
            items = [item for item in items if software in item['software']]
        navigation = facets(items, language)
        navigation['software'] = software_facets
        if category:
            prefix = category.split('/')
            items = [item for item in items if any(path[:len(prefix)] == prefix
                for path in item.get('categories', [item['category_ids']]))]
        items.sort(key=lambda item: (item['category_ids'], item['label'].casefold(), item['id']))
        page=[]
        for original in items[offset:offset+limit]:
            item=localize(original, language)
            item['category']=category_labels(item['category_ids'], language)
            page.append(item)
        return {'items': page, 'total': len(items), 'has_more': offset+limit<len(items),
                'next_cursor': offset+limit if offset+limit<len(items) else None, 'facets': navigation}

    def from_workflow(self, workflow, name):
        # Reuse the real compiler to flatten nested recipes and retain the exact
        # selected methods/parameters; existing file paths become external ports.
        from .execution.recipe_compiler import RecipeCompiler
        units=RecipeCompiler(self.registry).compile(workflow)
        ids={unit.step.id:'s'+str(i+1) for i,unit in enumerate(units)}
        steps=[]
        for unit in units:
            method=self.registry.definitions.method(unit.method.definition_id or unit.method.runner_id)
            links={}
            for slot,b in unit.step.input_bindings.items():
                if b.source=='upstream_output' and b.upstream_step_id in ids:
                    links[slot]={'step_id':ids[b.upstream_step_id],'output_slot_id':b.output_slot_id}
            steps.append({'id':ids[unit.step.id],'method_id':method.id,
                          'parameters':{k:v for k,v in unit.step.selected_parameters.items() if k in {p.id for p in method.parameters}},'inputs':links})
        # Preserve explicit shared public ports when exporting a used Pipeline.
        # Read recipe identities rather than guessing equality from path strings.
        shared = {}
        exported = {step['id']: step for step in steps}
        for parent in workflow.steps:
            selected = next((m for m in parent.method_options if m.id == parent.selected_method_id), None)
            if not selected or not selected.execution_recipe:
                continue
            for stage in selected.execution_recipe.steps:
                child_id = ids.get(parent.id + '__' + stage.id)
                if child_id is None:
                    continue
                for slot, binding in stage.input_bindings.items():
                    if (binding.source == 'workflow_input' and (binding.slot_id or '').startswith('shared_input_')
                            and slot not in exported[child_id]['inputs']):
                        shared.setdefault((parent.id, binding.slot_id), []).append({'step_id': child_id, 'input_slot_id': slot})
        return self.save(ComposeRequest(name=name or workflow.title,description=workflow.summary,steps=steps,
                         shared_inputs=[group for group in shared.values() if len(group) > 1]))

    def workflow(self, identity, request, service, workspace_service):
        p=self.get(identity,request.version)
        for step in p['steps']:
            current=self.registry.definitions.method(step.get('method_ref',step.get('method_id')))
            if step.get('method_version',current.version)!=current.version:
                raise ValueError('方法版本已变化，请复制 Pipeline 并重新校验')
        method=self.as_method(p)
        dataset=service.dataset_service.get(request.dataset_id) if request.dataset_id else None
        workspace=workspace_service.get(request.workspace_id) if request.workspace_id else None
        option=service._option(method,set(dataset.inspection.input_types if dataset else []),
                               dataset.inspection.features if dataset else {},dataset is not None)
        # Immutable recipe snapshot is locked immediately; user can bind files and review
        # parameters through the normal workflow UI before dry-run or confirmation.
        now=datetime.now(timezone.utc).isoformat()
        wf=Workflow(workflow_id='wf_'+uuid4().hex[:12],template_id='pipeline:'+identity,title=p['label'],
            summary=p.get('description',''),original_request=p['label'],status='awaiting_parameter_review',
            dataset_id=request.dataset_id,dataset=dataset,workspace_id=request.workspace_id,
            workspace_root_path=workspace.root_path if workspace else None,output_relative_path='.',
            planner_source='pipeline-library',locked_at=now,created_at=now,updated_at=now,
            requested_capabilities=[method.capability],steps=[WorkflowStep(id='pipeline',order=1,title=p['label'],
                description=p.get('description',''),capability=method.capability,selection='auto',status='method_selected',
                method_options=[option],selected_method_id=method.method_id,selected_parameters=service._default_parameters(option))])
        service._revalidate_chain(wf);service._resolve_workflow_inputs(wf);service._refresh(wf)
        self.store.save_workflow(wf,event_type='pipeline_instantiated')
        return wf
