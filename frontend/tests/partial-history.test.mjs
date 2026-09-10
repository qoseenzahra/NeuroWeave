import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { resolve } from 'node:path';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const root = resolve(import.meta.dirname, '..');
const server = await createServer({ root, configFile: false, resolve: { alias: { '@': root } },
  server: { middlewareMode: true, hmr: false }, appType: 'custom' });
try {
  const scope = { total: 500, eligible_sample_ids: ['sample-B'],
    skipped_samples: [{ sample_id: 'sample-A', label: 'A', reasons: ['5TT 缺失'] }] };
  await test('resource validation uses eligible samples and requires per-sample scheduling', async () => {
    const { executionErrors } = await server.ssrLoadModule('/components/workflow/execution-settings.tsx');
    const workflow = { dataset: { inspection: { sample_count: 500 } }, steps: [], sample_scope: scope };
    const node = { node: 'node01', cpus: 4, memory_gb: 2, gpus: 0, time_minutes: 10, parallel_samples: 4 };
    const options = { backend: 'slurm', partition: 'all', sample_mode: 'per_sample', nodes: [node] };
    const backends = { slurm: { available: true, partitions: ['all'], gpu_available: false,
      nodes: [{ name: 'node01', partition: 'all', schedulable: true, cpus: 4, memory_mb: 8192, gpus: 0 }] } };
    assert.deepEqual(executionErrors(options, backends, workflow), []);
    assert(executionErrors({ ...options, backend: 'local' }, backends, workflow).some(e => e.includes('按样本运行')));
    assert(executionErrors(options, backends, { ...workflow, sample_scope: { ...scope, eligible_sample_ids: [] } })
      .some(e => e.includes('没有共同匹配')));
    assert(executionErrors({ ...options, nodes: [node, { ...node, node: 'node02' }] }, backends, workflow)
      .some(e => e.includes('节点数不能多于')));
  });
  await test('skipped reasons are collapsed and scroll within a bounded region', async () => {
    const { SampleScopeNotice } = await server.ssrLoadModule('/components/workflow/sample-scope-notice.tsx');
    const html = renderToStaticMarkup(createElement(SampleScopeNotice, { scope }));
    assert(html.includes('共同匹配 1 个'));
    assert(html.includes('5TT 缺失'));
    assert(html.includes('max-h-52') && html.includes('overflow-y-auto'));
    assert(!/<details[^>]*\sopen(?:[\s=>])/.test(html));
  });
  await test('one original sample can select per-sample mode and a compute node', async () => {
    const { ExecutionSettings, executionErrors } = await server.ssrLoadModule('/components/workflow/execution-settings.tsx');
    const workflow = { workflow_id: 'one', dataset: { inspection: { sample_count: 1 } }, steps: [] };
    const options = { backend: 'slurm', partition: 'all', sample_mode: 'per_sample',
      nodes: [{ node: 'node03', cpus: 4, memory_gb: 2, gpus: 0, time_minutes: 10, parallel_samples: 4 }] };
    const backends = { slurm: { available: true, partitions: ['all'], gpu_available: false,
      nodes: [{ name: 'node03', partition: 'all', schedulable: true, state: 'idle', cpus: 4, memory_mb: 8192, gpus: 0 }] } };
    assert.deepEqual(executionErrors(options, backends, workflow), []);
    const html = renderToStaticMarkup(createElement(ExecutionSettings, { workflow, value: options, backends, disabled: false, onChange() {} }));
    assert.match(html, /<option\b[^>]*value="per_sample"[^>]*>按样本运行（1 个样本）<\/option>/);
    assert(!/<option\b[^>]*disabled[^>]*value="per_sample"|<option\b[^>]*value="per_sample"[^>]*disabled/.test(html));
    assert(html.includes('使用节点 node03') && html.includes('最多同时处理 1 个'));
    assert(html.includes('两种运行方式都可指定计算节点'));
    const partial = renderToStaticMarkup(createElement(ExecutionSettings, { workflow: { ...workflow, sample_scope: scope }, value: options, backends, disabled: false, onChange() {} }));
    assert(!partial.includes('两种运行方式都可指定计算节点'));
  });
} finally { await server.close(); }
