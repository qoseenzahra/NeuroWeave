import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';
import { mkdir } from 'node:fs/promises';
import { createServer } from 'vite';
import tailwindcss from '@tailwindcss/postcss';
import react from '@vitejs/plugin-react';
import { checkDatasetLock } from './dataset-lock-browser.mjs';
const require = createRequire(import.meta.url);
const browserRequire = process.env.LOCALFLOW_BROWSER_TOOLS
  ? createRequire(join(process.env.LOCALFLOW_BROWSER_TOOLS, '_layout-test.cjs')) : require;
const { chromium } = browserRequire('playwright');
const project = resolve(import.meta.dirname, '..');
const output = resolve(project, '../runtime/layout-checks');
await mkdir(output, { recursive: true });
const longName = 'synthetic_long_sample_name_'.repeat(5);
const root = { root_id: 'root', label: '服务器数据根目录', path: '/synthetic', readable: true, writable: false };
const dataset = { dataset_id: 'dataset', root_id: 'root', relative_path: '', absolute_path: '/synthetic',
  display_name: 'Synthetic dataset', created_at: '', updated_at: '', inspection: {
    sample_count: 4, samples: [], sample_layout: 'directory', file_count: 300, total_bytes: 200000000,
    is_bids: false, has_dwi: true, has_t1w: true, has_fod: true, has_five_tt: true,
    warnings: ['未识别到成对反向相位编码数据。请检查所选方法的输入要求。'], input_types: [], features: {},
  } };
const slot = { id: 'fod', type: 'fod_image', label: 'FOD 文件', description: '选择已生成的 FOD 作为本步骤输入。',
  required: true, required_when: {}, cardinality: 'one', binding: 'file', formats: ['.mif'],
  companions: [], source_options: ['existing_path'], validation: [] };
const workflow = { workflow_id: 'fixture', template_id: 'test', revision: 1, title: '合成样本布局验证',
  summary: '验证长内容和节点运行设置', original_request: '', status: 'confirmed', dataset_id: 'dataset', dataset,
  planner_source: 'test', execution_mode: 'runner', plan_kind: 'atomic', requested_capabilities: [],
  steps: [{ id: 'step', order: 1, title: '已有 FOD 纤维追踪', description: '', capability: 'dwi.tractography',
    origin: 'requested', selection: 'auto', depends_on: [], status: 'confirmed', selected_method_id: 'method',
    selected_parameters: { threads: 4, mode: 'a', enabled: true }, input_bindings: {}, missing_required_inputs: [],
    method_options: [{ id: 'method', skill_id: 'dwi', label: '使用已有 FOD 进行纤维追踪', description: '',
      runner_id: 'mrtrix.tckgen', execution_mode: 'runner', input_types: ['fod_image'], output_types: [],
      input_slots: [slot], output_slots: [], parameters: [
        { id: 'threads', argument: '-threads', type: 'integer', control: 'number', label: '线程数量', description: '每个步骤使用的线程。',
          required: true, default: 4, minimum: 1, maximum: 128, options: [], visible_when: {}, level: 'basic', group: '常用参数' },
        { id: 'mode', argument: '-mode', type: 'string', control: 'select', label: '方法选项', description: longName,
          required: true, default: 'a', options: [{ value: 'a', label: longName, description: longName }],
          visible_when: {}, level: 'basic', group: '常用参数' },
        { id: 'enabled', argument: '-enabled', type: 'boolean', control: 'switch', label: longName, description: longName,
          required: true, default: true, options: [], visible_when: {}, level: 'basic', group: '常用参数' },
      ], compatible: true, blocked_reasons: [],
      requires_features: [], recommended: true, source_references: [], command_references: [] }] }],
  warnings: [], can_lock: false, can_unlock: false, can_review_parameters: false, can_dry_run: false, can_confirm: false,
  locked_at: '2026-01-01', confirmed_at: '2026-01-01', parameters_reviewed_at: '2026-01-01',
  dry_run_report: { valid: true, execution_enabled: true, commands: [], warnings: [], checked_at: '2026-01-01' },
  created_at: '2026-01-01', updated_at: '2026-01-01' };
const nodes = ['mgr', 'node01', 'node02', 'node03'].map(name => ({
  name, partition: 'all', state: 'idle', schedulable: true, cpus: 128, allocated_cpus: 0,
  memory_mb: name === 'mgr' ? 490000 : 245000, gpus: name === 'mgr' ? 0 : 1,
}));
workflow.steps[0].method_options.push({
  ...workflow.steps[0].method_options[0], id: 'manual-input', label: '手动绑定已有文件的方法',
  recommended: false, input_warnings: ['扫描未识别到输入，可以选择方法后手动绑定文件。'],
  scope_warnings: ['此方法包含已移除的操作，选择后仍按方法原有定义执行。'],
});
const server = await createServer({ root: project, configFile: false,
  define: { 'process.env.NEXT_PUBLIC_LOCALFLOW_API_URL': '""' },
  resolve: { alias: { '@': project } }, css: { postcss: { plugins: [tailwindcss()] } },
  server: { host: '127.0.0.1', port: 0 }, plugins: [react(), {
    name: 'layout-test', configureServer(vite) {
      vite.middlewares.use('/__layout_test', async (_req, res) => {
        res.setHeader('Content-Type', 'text/html');
        res.end(await vite.transformIndexHtml('/__layout_test',
          '<!doctype html><html><head></head><body><div id="root"></div><script type="module" src="/tests/layout-harness.tsx"></script></body></html>'));
      });
    },
  }] });
let browser;
try {
  await server.listen();
  browser = await chromium.launch({ headless: true, executablePath: process.env.LOCALFLOW_BROWSER_EXECUTABLE || undefined });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => { errors.push(error.message); console.error(error.message); });
  await page.addInitScript(fixture => { window.fixture = fixture; }, { dataset, workflow, slot });
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    let data;
    if (url.pathname === '/api/datasets/roots') data = { roots: [root] };
    else if (url.pathname === '/api/datasets') data = { datasets: [dataset, ...Array.from({ length: 5 }, (_, i) => ({
      ...dataset, dataset_id: 'ds-' + i, display_name: 'Long_registered_dataset_' + longName, relative_path: longName,
    }))] };
    else if (url.pathname === '/api/datasets/directories') data = { root, relative_path: '', parent_relative_path: null,
      breadcrumbs: [{ label: '服务器数据根目录', relative_path: '' }], directory_count: 1, file_count: 1,
      directories: [{ name: longName, relative_path: longName, readable: true }],
      files: [{ name: 'wmfod.mif', relative_path: 'wmfod.mif', readable: true, size_bytes: 100 }] };
    else if (url.pathname.endsWith('/preview')) data = { binding_mode: 'per_sample', selected_relative_path: 'wmfod.mif',
      path_template: longName + '/{sample}/wmfod.mif', coverage: { total: 4, matched: 4, missing: 0, invalid: 0 },
      matches: nodes.map((node, index) => ({ sample_id: String(index), label: longName, relative_path: longName + '/wmfod.mif', status: 'matched' })),
      can_apply: true, messages: [] };
    else if (url.pathname === '/api/execution/backends') data = {
      local: { available: true }, slurm: { enabled: true, available: true, partitions: ['all'], gpu_available: true, nodes },
    };
    else if (url.pathname === '/api/runs') data = { runs: [] };
    else if (url.pathname === '/api/workflows/fixture/steps/step/method') data = {
      ...workflow, revision: 2, status: 'chain_ready', locked_at: null, can_lock: true,
      steps: workflow.steps.map(step => ({ ...step, selected_method_id: route.request().postDataJSON().method_id })),
    };
    else if (url.pathname === '/api/health') data = { status: 'ok', mode: 'demo', model: 'test' };
    else if (url.pathname === '/api/skills') data = { skills: [] };
    else if (url.pathname === '/api/conversations') data = { conversations: [], has_more: false, next_cursor: null };
    else throw new Error('Unexpected test API request: ' + url.pathname);
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
  });
  const checkHorizontal = async selector => {
    const bounds = await page.locator(selector).evaluateAll(elements => elements.map(element => {
      const box = element.getBoundingClientRect();
      return { name: element.getAttribute('data-slot') || element.tagName, left: box.left, right: box.right,
        client: element.clientWidth, scroll: element.scrollWidth };
    }));
    for (const item of bounds) {
      assert(item.left >= -1 && item.right <= (await page.viewportSize()).width + 1, JSON.stringify(item));
      assert(item.scroll <= item.client + 2, 'Horizontal overflow: ' + JSON.stringify(item));
    }
  };
  for (const viewport of [{ width: 1440, height: 900 }, { width: 780, height: 600 },
    { width: 640, height: 450 }, { width: 390, height: 600 }, { width: 320, height: 420 }]) {
    await page.setViewportSize(viewport);
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__layout_test`);
    await page.getByRole('button', { name: '选择数据集', exact: true }).click();
    await page.getByText('已登记数据集', { exact: true }).waitFor();
    await checkHorizontal('[data-slot="dialog-content"], [data-slot="dialog-content"] section');
    await page.screenshot({ path: join(output, `dataset-${viewport.width}.png`) });
    await page.getByRole('button', { name: '重新扫描并选择', exact: true }).click({ trial: true });
    await page.getByRole('button', { name: 'Synthetic dataset', exact: false }).click();
    await page.getByRole('button', { name: '选择已有路径', exact: true }).first().click();
    await page.getByRole('button', { name: 'wmfod.mif', exact: true }).click();
    await checkHorizontal('[data-slot="dialog-content"]');
    await page.getByRole('button', { name: '应用到 4 个样本', exact: true }).click();
    await page.getByTestId('selected-path').getByText('wmfod.mif', { exact: true }).waitFor();
    await page.getByLabel('运行位置', { exact: true }).selectOption('slurm');
    await page.getByLabel('运行节点', { exact: true }).selectOption('node01');
    await page.getByRole('region', { name: 'node01 资源配置' }).getByLabel('CPU 核数', { exact: true }).fill('16');
    await page.getByLabel('样本运行方式', { exact: true }).selectOption('per_sample');
    await page.getByLabel('使用节点 node02', { exact: true }).check();
    await page.getByRole('region', { name: 'node02 资源配置' }).getByLabel('CPU 核数', { exact: true }).fill('32');
    await checkHorizontal('[data-slot="card"], [data-slot="card-content"], [data-slot="card-footer"], section[aria-label]');
    await page.getByRole('button', { name: /开始.*运行|启动.*运行/ }).click({ trial: true });
    await page.screenshot({ path: join(output, `execution-${viewport.width}.png`), fullPage: true });
    for (const name of ['测试方法选择', '测试参数审核']) {
      await page.getByRole('button', { name, exact: true }).click();
      if (name === '测试方法选择') {
        const choice = page.getByRole('radio', { name: /手动绑定已有文件的方法/ });
        assert(await choice.isEnabled(), 'Input warnings must not disable a registered method');
        await choice.click();
        await page.getByRole('radio', { name: /手动绑定已有文件的方法/, checked: true }).waitFor();
      }
      await checkHorizontal('[data-slot="card"], [data-slot="card-content"], [data-slot="card-footer"]');
      const buttons = page.locator('[data-slot="card"] button:not(:disabled)');
      for (let index = 0; index < await buttons.count(); index++) {
        if (await buttons.nth(index).isVisible()) await buttons.nth(index).click({ trial: true });
      }
    }
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__layout_test?surface=app`);
    await page.getByLabel('对话输入', { exact: true }).click({ trial: true });
    await checkHorizontal('main');
    const openSkills = page.getByRole('button', { name: '打开 Skill 面板', exact: true });
    if (await openSkills.isVisible()) {
      await openSkills.click();
      await page.locator('aside').getByRole('button', { name: '关闭 Skill 面板', exact: true }).click();
    }
    await page.screenshot({ path: join(output, `app-${viewport.width}.png`) });
  }
  await checkDatasetLock({ page, root, dataset, workflow,
    appUrl: `http://127.0.0.1:${server.httpServer.address().port}/__layout_test?surface=app` });
  assert.deepEqual(errors, []);
  console.log('Responsive dataset/input selectors and per-node settings passed at five viewport sizes.');
} finally {
  await browser?.close();
  await server.close();
}
