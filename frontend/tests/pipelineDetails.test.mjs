import assert from 'node:assert/strict';
import {test} from 'node:test';
import {resolve} from 'node:path';
import {readFile} from 'node:fs/promises';
import {createServer} from 'vite';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
const root=resolve(import.meta.dirname,'..');
const server=await createServer({root,configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
try {
  const {useLanguageStore}=await server.ssrLoadModule('/src/stores/languageStore.ts');
  const language=useLanguageStore.getInitialState().language;
  const method=JSON.parse(await readFile(resolve(root,'../methods/mrtrix3/mrtrix.command.mrconvert/method.json'),'utf8'));
  method.runtime_status={available:true};
  method.parameters=method.parameters.map(p=>({options:[],...p}));
  const source={name:'Original',description:'Description',expected_version:5,
    steps:[{id:'first',method_id:method.id,parameters:{nthreads:2},inputs:{},position:{x:80,y:80}},
      {id:'second',method_id:method.id,parameters:{},inputs:{input:{step_id:'first',output_slot_id:'output'}},position:{x:580,y:80}}]};
  const pipeline={id:'builtin',version:'1',label:source.name,description:source.description,
    draft_id:'original-recovery',draft_revision:9,parameters:[],input_slots:[],output_slots:[],
    steps:source.steps.map(s=>({id:s.id,method_ref:s.method_id,title:s.id}))};
  await test('copy gets independent identity and recovery while keeping the complete graph',async()=>{
    const {copyPipeline}=await server.ssrLoadModule('/src/features/library/pipelineCopy.ts');
    const copied=copyPipeline(pipeline,source);
    assert.equal(copied.id,'');assert.equal(copied.version,'');
    assert.equal(copied.draft_id,undefined);assert.equal(copied.draft_revision,undefined);
    assert.equal(copied.editor.expected_version,undefined);
    assert.deepEqual(copied.editor.steps,source.steps);
    copied.editor.steps[0].parameters.nthreads=7;
    copied.editor.steps[1].inputs.input.output_slot_id='changed';
    assert.equal(source.steps[0].parameters.nthreads,2);
    assert.equal(source.steps[1].inputs.input.output_slot_id,'output');
  });
  await test('read-only detail canvas retains selection, ports and links without editing actions',async()=>{
    const {PipelineDetails}=await server.ssrLoadModule('/src/features/library/PipelineDetails.tsx');
    const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
    client.setQueryData(['pipeline-source','builtin','1'],{editor:source});
    client.setQueryData(['library-method',method.id,language],method);
    client.setQueryData(['pipeline-versions','builtin'],{items:[]});
    const noop=()=>{};
    const html=renderToStaticMarkup(createElement(QueryClientProvider,{client},createElement(PipelineDetails,{pipeline,onClose:noop,onSelect:noop,onEdit:noop,onLaunch:noop,onChange:noop})));
    assert.equal((html.match(/data-pipeline-node=/g)??[]).length,2);
    assert.match(html,/marker-end="url\(#pipeline-arrow\)"/);
    assert.match(html,/查看步骤：|Inspect step:/);
    assert.match(html,/data-pipeline-input="input"[^>]*disabled|disabled[^>]*data-pipeline-input="input"/);
    assert.match(html,/基于此 Pipeline 创建|Create from this Pipeline/);
    assert.doesNotMatch(html,/自动排列|移动或选择|保存草稿|发布可用版本|移除节点及连线|Auto arrange|Move or select|Save draft|Publish usable version/);
    client.clear();
  });
} finally {await server.close();}
