import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolve } from 'node:path';
import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { filterRunGroups, groupRunSteps, monitorPage } from '../lib/run-monitor.ts';

function step(sample, index, status = 'queued', extra = {}) {
  return { step_id: sample + '-' + index, sample_id: sample, sample_label: sample,
    title: '步骤 ' + index, runner_id: 'fixture', method_id: 'fixture',
    node_name: 'node01', status, progress: status === 'succeeded' ? 100 : 0,
    message: '', artifacts: [], error_code: '', error_message: '',
    started_at: null, finished_at: null, ...extra };
}

await test('sample summaries retain failures, partial progress and distinct sample identities', () => {
  const groups = groupRunSteps([
    step('a', 0, 'succeeded'), step('a', 1, 'running', { progress: 50 }),
    step('a', 2), step('b', 0, 'failed'), step('b', 1),
    step('c', 0, 'succeeded'), step('c', 1, 'cancelled'),
    step('d', 0, 'succeeded'), step('d', 1, 'succeeded'),
    step('e', 0, 'queued', { sample_label: 'a' }),
  ]);
  assert.equal(groups.length, 5);
  assert.deepEqual(groups.map(group => group.status), ['running', 'failed', 'cancelled', 'succeeded', 'queued']);
  assert.equal(groups[0].progress, 50);
  assert.equal(groups[3].progress, 100);
  assert.deepEqual(groups[0].steps.map(item => item.step_id), ['a-0', 'a-1', 'a-2']);
});

await test('filter searches sample IDs, labels, nodes and jobs without reordering samples', () => {
  const groups = groupRunSteps([
    step('a', 0, 'running', { sample_label: '患者甲', scheduler: { job_id: 98765 } }),
    step('b', 0, 'failed', { node_name: 'node02' }),
    step('c', 0, 'succeeded'),
  ]);
  assert.equal(filterRunGroups(groups, 'all', ' 98765 ')[0].sampleId, 'a');
  assert.equal(filterRunGroups(groups, 'all', '患者甲')[0].sampleId, 'a');
  assert.equal(filterRunGroups(groups, 'failed', 'NODE02')[0].sampleId, 'b');
  assert.equal(filterRunGroups(groups, 'succeeded', '98765').length, 0);
  assert.deepEqual(filterRunGroups(groups, 'all', '').map(group => group.sampleId), ['a', 'b', 'c']);
});

await test('pagination bounds large batches and clamps a page when polling shrinks a filtered list', () => {
  const items = Array.from({ length: 1001 }, (_, index) => index);
  assert.deepEqual(monitorPage(items, 0).items, [0, 1, 2, 3, 4, 5, 6, 7]);
  assert.deepEqual(monitorPage(items, 125), { page: 125, pages: 126, items: [1000] });
  assert.deepEqual(monitorPage([1, 2], 125), { page: 0, pages: 1, items: [1, 2] });
  assert.deepEqual(monitorPage([], 125), { page: 0, pages: 1, items: [] });
});

await test('older runs without sample IDs retain every individual step', () => {
  const groups = groupRunSteps([
    step('same', 0, 'succeeded', { sample_id: null, sample_label: '' }),
    step('same', 1, 'running', { sample_id: null, sample_label: '' }),
  ]);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups.map(group => group.label), ['步骤 0', '步骤 1']);
});

await test('the real monitor bounds 3000 steps and 1000 outputs, with details collapsed', async () => {
  // Render the production component without a browser or any backend/job requests.
  const root = resolve(import.meta.dirname, '..');
  const server = await createServer({ root, configFile: false,
    resolve: { alias: { '@': root } }, server: { middlewareMode: true },
    appType: 'custom' });
  try {
    const { RunPanel } = await server.ssrLoadModule('/components/workflow/run-panel.tsx');
    const steps = Array.from({ length: 1000 }, (_, index) =>
      [0, 1, 2].map(order => step('sample-' + index, order, 'succeeded'))).flat();
    const artifacts = Array.from({ length: 1000 }, (_, index) => ({
      artifact_id: String(index), label: '结果 ' + index, absolute_path: '/synthetic/sample-' + index + '/result.mif',
      sha256: 'a'.repeat(64),
    }));
    const run = { run_id: 'fixture', status: 'succeeded', progress: 100, steps, artifacts,
      output_directory: '/synthetic/output', error_message: '' };
    const markup = renderToStaticMarkup(createElement(RunPanel, { run, events: [] }));
    assert.equal((markup.match(/class="group\/sample /g) || []).length, 8);
    assert(!/<details[^>]*\sopen(?:[\s=>])/.test(markup), 'Details should start collapsed');
    assert(markup.includes('第 1 / 125 页'));
    assert(markup.includes('1000 / 1000 样本已完成'));
    assert(markup.includes('输出文件（1000）'));
    assert(!markup.includes('/synthetic/sample-8/result.mif'), 'Output files must also be paged');
    assert(markup.includes('max-h-96'), 'Expanding details must not grow the page without a bound');

    steps[2998] = { ...steps[2998], status: 'failed', error_message: 'synthetic failure' };
    const failed = renderToStaticMarkup(createElement(RunPanel, { run: { ...run, status: 'failed' }, events: [] }));
    assert.equal((failed.match(/class="group\/sample /g) || []).length, 1);
    assert(failed.includes('synthetic failure'), 'A failure near the end of the batch must be discoverable immediately');
    assert(failed.includes('sample-999'));
  } finally {
    await server.close();
  }
});
