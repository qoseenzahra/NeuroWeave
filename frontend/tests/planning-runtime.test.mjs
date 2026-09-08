import test from 'node:test';
import assert from 'node:assert/strict';
import { methodExecutionLabel } from '../lib/workflow.ts';

await test('planning badges identify the actual unmet condition', () => {
  const labels = {
    missing_runtime: '缺少运行环境',
    missing_implementation: '缺少原始实现',
    source_error: '原定义待修正',
    external_service: '需外部服务',
    interactive: '交互管理',
    needs_protocol: '待明确分析协议',
  };
  for (const [state, expected] of Object.entries(labels)) {
    assert.equal(methodExecutionLabel({ execution_mode: 'planning', execution_resolution: { state } }), expected);
  }
});

await test('a mapped runner reports its real compiled stages and old snapshots remain readable', () => {
  assert.equal(methodExecutionLabel({ execution_mode: 'runner', execution_recipe: { steps: [{}, {}, {}] } }), 'Runner 流程 · 3 步');
  assert.equal(methodExecutionLabel({ execution_mode: 'runner' }), 'Runner');
  assert.equal(methodExecutionLabel({ execution_mode: 'planning' }), '仅规划');
});
