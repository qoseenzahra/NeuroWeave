// UI-only synthetic fixture server. Run explicitly; Ctrl+C closes Vite.
import { createServer } from 'vite';
import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
const root = resolve(import.meta.dirname, '..');
const group = 'a'.repeat(24);
const server = await createServer({ root, configFile: false,
  resolve: { alias: { '@': root } }, css: { postcss: { plugins: [tailwindcss()] } },
  plugins: [react(), { name: 'historical-input-fixture', configureServer(vite) {
    vite.middlewares.use(async (req, res, next) => {
      const url = new URL(req.url, 'http://127.0.0.1');
      if (url.pathname === '/__historical_input_test') {
        res.setHeader('Content-Type', 'text/html');
        res.end(await vite.transformIndexHtml(url.pathname,
          '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module" src="/tests/historical-input-harness.tsx"></script></body></html>'));
      } else if (url.pathname.startsWith('/api/workflows/')) {
        res.setHeader('Content-Type', 'application/json');
        const missing = url.pathname.includes('/missing/');
        const empty = url.pathname.includes('/empty/');
        if (url.pathname.endsWith('/preview')) {
          const matches = Array.from({ length: 63 }, (_, index) => ({ sample_id: 'sample-' + index,
            label: 'Synthetic sample ' + index, relative_path: '',
            absolute_path: '/synthetic/previous-run/' + 'long_output_directory_'.repeat(5) + '/sample-' + index + '/5tt.mif',
            status: empty || (missing && index === 62) ? 'missing' : 'matched',
            message: empty || (missing && index === 62) ? '此样本没有成功的历史输出' : '按原始样本标识匹配' }));
          res.end(JSON.stringify({ run_id: 'run_fixture', group_id: group, matches,
            coverage: { total: 63, matched: empty ? 0 : missing ? 62 : 63, missing: empty ? 63 : missing ? 1 : 0, invalid: 0 },
            partial: missing || empty, can_apply: !empty, messages: ['合成预览，不包含研究数据。'] }));
        } else {
          res.end(JSON.stringify({ candidates: [{ run_id: 'run_fixture', group_id: group,
            run_title: 'Synthetic 5TT generation', run_status: 'succeeded', created_at: '2026-09-08T00:00:00Z',
            step_title: '5TT', label: '五组织类型影像', sample_count: 63, artifact_count: 63 }],
            has_more: false, next_offset: 1 }));
        }
      } else next();
    });
  } }], server: { host: '127.0.0.1', port: 18765, strictPort: true, hmr: false } });
await server.listen();
console.log('Historical input fixture: http://127.0.0.1:18765/__historical_input_test');
async function shutdown() { await server.close(); process.exit(0); }
process.once('SIGINT', shutdown); process.once('SIGTERM', shutdown);
