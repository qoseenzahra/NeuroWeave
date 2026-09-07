// Uses the existing Vite/React packages and an available Playwright installation.
// LOCALFLOW_BROWSER_TOOLS can point at a shared node_modules directory.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';
import { createServer } from 'vite';
const require = createRequire(import.meta.url);
const browserRequire = process.env.LOCALFLOW_BROWSER_TOOLS
  ? createRequire(join(process.env.LOCALFLOW_BROWSER_TOOLS, '_history-test.cjs')) : require;
const { chromium } = browserRequire('playwright');
const server = await createServer({ root: resolve(import.meta.dirname, '..'), configFile: false,
  server: { host: '127.0.0.1', port: 0 },
  plugins: [{ name: 'isolated-history-test', configureServer(vite) {
    vite.middlewares.use('/__history_test', (_req, res) => {
      res.setHeader('Content-Type', 'text/html');
      res.end('<div id="root"></div><script type="module" src="/tests/history-harness.tsx"></script>');
    });
  } }],
});
let browser;
try {
  await server.listen();
  browser = await chromium.launch({ headless: true, executablePath: process.env.LOCALFLOW_BROWSER_EXECUTABLE || undefined });
  const page = await browser.newPage();
  const requests = [];
  let failRefresh = false, releaseAlpha;
  const alpha = new Promise((resolveAlpha) => { releaseAlpha = resolveAlpha; });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/conversations?*', async (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams.get('q') ?? '';
    requests.push(url.search);
    if (q === 'alpha') await alpha;
    const archived = url.searchParams.get('archived') === 'true';
    const second = url.searchParams.has('cursor');
    const conversations = Array.from({ length: q || archived ? 1 : second ? 2 : 20 }, (_, index) => ({
      conversation_id: `${q || (archived ? 'archive' : 'active')}-${second ? index + 20 : index}`,
      title: q || (archived ? 'archived' : `row-${second ? index + 20 : index}`), archived,
      message_count: 1, last_message_preview: 'preview', created_at: '2026-01-01', updated_at: '2026-01-01',
    }));
    try { await route.fulfill({ status: failRefresh ? 500 : 200, contentType: 'application/json',
      body: JSON.stringify({ conversations, has_more: !q && !archived && !second, next_cursor: !q && !archived && !second ? 'page2' : null }) });
    } catch { /* The alpha request is deliberately cancelled by a newer search. */ }
  });
  const rows = () => page.locator('#rows').textContent();
  const waitRows = (value) => page.waitForFunction((text) => document.querySelector('#rows')?.textContent === text, value);
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__history_test`);
  await page.getByRole('button', { name: 'Open', exact: true }).waitFor();
  assert.equal(requests.length, 0, 'Hidden history must not fetch');
  await page.getByRole('button', { name: 'Open', exact: true }).click();
  await waitRows(Array.from({ length: 20 }, (_, i) => `row-${i}`).join('|'));
  await page.getByRole('button', { name: 'More', exact: true }).click();
  await waitRows(Array.from({ length: 22 }, (_, i) => `row-${i}`).join('|'));
  const loadedRequests = requests.length;
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Open', exact: true }).click();
  assert.equal(requests.length, loadedRequests, 'Reopening should retain cached pages');
  assert.equal((await rows()).split('|').length, 22);
  await page.getByRole('button', { name: 'Scope', exact: true }).click();
  await waitRows('archived');
  await page.getByRole('button', { name: 'Scope', exact: true }).click();
  await waitRows(Array.from({ length: 22 }, (_, i) => `row-${i}`).join('|'));
  const alphaStarted = page.waitForRequest((request) => request.url().includes('q=alpha'));
  await page.getByLabel('Search').fill('alpha'); await alphaStarted;
  await page.getByLabel('Search').fill('beta'); await waitRows('beta'); releaseAlpha();
  assert.equal(await rows(), 'beta', 'Stale search must not replace the current filter');
  failRefresh = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await page.waitForFunction(() => Boolean(document.querySelector('#error')?.textContent));
  assert.equal(await rows(), 'beta', 'Refresh failures preserve displayed history');
  failRefresh = false;
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#loading')?.textContent === 'false' && !document.querySelector('#error')?.textContent);
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  const beforeHiddenRefresh = requests.length;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  assert.equal(requests.length, beforeHiddenRefresh);
  const reopened = page.waitForRequest((request) => request.url().includes('q=beta'));
  await page.getByRole('button', { name: 'Open', exact: true }).click(); await reopened;
  await waitRows('beta');
  assert.deepEqual(errors, []);
  console.log('History browser checks passed: lazy load, pagination, cached scopes, stale search, retry, mutation invalidation.');
} finally { await browser?.close(); await server.close(); }
