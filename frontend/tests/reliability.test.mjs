import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { resolve } from 'node:path';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const root = resolve(import.meta.dirname, '..');
const server = await createServer({ root, configFile: false,
  resolve: { alias: { '@': root } }, server: { middlewareMode: true, hmr: false }, appType: 'custom' });
try {
  await test('workflow lazy loader limits concurrency, deduplicates requests, and releases failed slots', async () => {
    const { loadWorkflow } = await server.ssrLoadModule('/lib/load-workflow.ts');
    const previous = globalThis.fetch;
    const releases = [];
    let active = 0, peak = 0, count = 0;
    globalThis.fetch = async () => {
      ++count; ++active; peak = Math.max(peak,active);
      await new Promise(resolve => releases.push(resolve));
      --active;
      return Response.json({ workflow_id: String(count) });
    };
    try {
      const a = loadWorkflow('/api','a');
      const same = loadWorkflow('/api','a');
      const b = loadWorkflow('/api','b');
      const c = loadWorkflow('/api','c');
      assert.equal(a,same);
      assert.equal(count,2);
      releases.shift()();
      await a;
      assert.equal(count,3);
      releases.splice(0).forEach(release => release());
      await Promise.all([a,b,c]);
      assert.equal(peak,2);
      globalThis.fetch = async () => { throw new Error('offline'); };
      await assert.rejects(loadWorkflow('/api','d'), /offline/);
      globalThis.fetch = async () => Response.json({ workflow_id:'d' });
      assert.equal((await loadWorkflow('/api','d')).workflow_id,'d');
    } finally { globalThis.fetch = previous; }
  });

  await test('incremental monitor merges changed steps and artifacts without losing unaffected samples', async () => {
    const { mergeRunUpdate } = await server.ssrLoadModule('/lib/use-run-monitoring.ts');
    const a = { step_id:'a',status:'succeeded',artifacts:[{artifact_id:'a'}] };
    const b = { step_id:'b',status:'running',artifacts:[] };
    const previous = { run_id:'one',steps:[a,b],artifacts:a.artifacts,plan_snapshot:{large:true} };
    const merged = mergeRunUpdate(previous,{run:{run_id:'one',artifacts:[],state_revision:2},reset:false,
      steps:[{...b,status:'succeeded',artifacts:[{artifact_id:'b'}]}]});
    assert.deepEqual(merged.steps.map(step => step.step_id),['a','b']);
    assert.equal(merged.steps[0],a);
    assert.deepEqual(merged.artifacts.map(item => item.artifact_id),['a','b']);
    assert.deepEqual(merged.plan_snapshot,{});
    const reset = mergeRunUpdate(merged,{run:{run_id:'one',artifacts:[]},reset:true,steps:[b]});
    assert.deepEqual(reset.steps,[b]);
  });

  await test('real log panel shows only its bounded live page when thousands of events exist', async () => {
    const { RunLogs } = await server.ssrLoadModule('/components/workflow/run-logs.tsx');
    const events = Array.from({length:1250},(_,i) => ({event_id:i+1,level:'info',message:'event-'+(i+1)}));
    const html = renderToStaticMarkup(createElement(RunLogs,{apiBase:'',runId:'one',events}));
    assert(html.includes('[1250]'));
    assert(!html.includes('[1230]'));
    assert.equal((html.match(/<p(?:\s|>)/g)||[]).length,20);
    assert(html.includes('更早日志'));
    assert(!/<details[^>]*\sopen(?:[\s=>])/.test(html));
  });
} finally { await server.close(); }
