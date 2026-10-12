// Task B frontend checks against the real modules (no duplicated helpers).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolve } from 'node:path';
import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient } from '@tanstack/react-query';

class MemoryStorage {
  constructor() { this.map = new Map(); }
  get length() { return this.map.size; }
  key(i) { return [...this.map.keys()][i] ?? null; }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
  setItem(k, v) { this.map.set(k, String(v)); }
  removeItem(k) { this.map.delete(k); }
  clear() { this.map.clear(); }
}
globalThis.localStorage = new MemoryStorage();
const events = [];
globalThis.window = Object.assign(new EventTarget(), { setInterval, clearInterval });
window.addEventListener('neuroweave:chat-progress', (event) => events.push(event.detail));

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; };

const server = await createServer({
  root: resolve(import.meta.dirname, '..'), configFile: false,
  server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom',
});
try {
  const load = (path) => server.ssrLoadModule('/src/' + path);
  const scope = await load('features/access/businessScope.ts');
  const { request } = await load('api/http.ts');
  const chat = await load('features/chat/chatApi.ts');
  const turns = await load('features/chat/chatTurns.ts');
  const auth = await load('features/access/authorization.ts');
  const { cleanupBusinessContext } = await load('features/access/useScopeCleanup.ts');
  const library = await load('features/library/libraryApi.ts');
  const { ResourcePolicyPanel } = await load('features/access/ResourcePolicyPanel.tsx');
  const { DirectoryScopeSettings } = await load('features/access/DirectoryScopeSettings.tsx');
  const original = globalThis.fetch;
  const reset = () => { scope.resetBusinessScopeForTests(); events.length = 0; localStorage.clear(); globalThis.fetch = original; };

  await test('scope changes bump the epoch, abort old requests and change cache identity', () => {
    reset();
    scope.setBusinessScope({ userId: 'alice', projectId: null });
    const signal = scope.scopeSignal();
    const aliceHash = scope.scopedQueryHash(['conversations', { archived: false }]);
    assert.equal(scope.setBusinessScope({ userId: 'alice', projectId: null }), false, 'same scope is not a change');
    assert.equal(scope.setBusinessScope({ userId: 'bob', projectId: null }), true);
    assert.equal(signal.aborted, true);
    assert.notEqual(scope.scopedQueryHash(['conversations', { archived: false }]), aliceHash);
    scope.setBusinessScope({ userId: 'bob', projectId: 'p1' });
    assert.match(scope.scopedStorageKey('pipeline-draft', 'd1'), /bob:p1:d1$/);
    scope.setBusinessScope(null);
    assert.equal(scope.scopedStorageKey('pipeline-draft', 'd1'), null);
  });

  await test('the shared HTTP client discards a response that arrives after a scope change', async () => {
    reset();
    scope.setBusinessScope({ userId: 'alice', projectId: null });
    const gate = deferred();
    globalThis.fetch = async (_url, init) => { await gate.promise; assert.equal(init.signal.aborted, true); return json({ secret: 'alice' }); };
    const pending = request('/api/conversations');
    scope.setBusinessScope({ userId: 'bob', projectId: null });
    gate.resolve();
    await assert.rejects(pending, (error) => error.name === 'StaleScopeError');
  });

  await test('the selected project is sent as a scope header, never as an identity', async () => {
    reset();
    let headers;
    globalThis.fetch = async (_url, init) => { headers = init.headers; return json({ ok: true }); };
    scope.selectProject('p1');
    await request('/api/datasets');
    assert.equal(headers['X-NeuroWeave-Project'], 'p1');
    assert.equal(Object.keys(headers).some((name) => /user/i.test(name)), false);
  });

  await test('normal chat submission resolves the authenticated scope and sends the turn (issue 03)', async () => {
    reset();
    const calls = [];
    globalThis.fetch = async (url, init = {}) => {
      calls.push(`${init.method ?? 'GET'} ${url}`);
      if (url.endsWith('/api/chat/scope')) return json({ userId: 'alice', projectId: null });
      if (url.endsWith('/api/chat/turns')) return json({ turn_id: 't1', conversation_id: 'c1', status: 'queued', message: '', result: null, error: null });
      return json({ turn_id: 't1', conversation_id: 'c1', status: 'succeeded', message: '', result: { content: 'hi' }, error: null });
    };
    const result = await chat.sendChat({ message: 'hello', conversation_id: null, workspace_id: null, client_turn_id: 't1',
      interaction_mode: 'chat', selected_skills: [], dataset_id: null, language: 'en' });
    assert.equal(result.content, 'hi');
    assert.ok(calls.includes('POST /api/chat/turns'), calls.join(', '));
    assert.deepEqual(turns.pendingTurns({ userId: 'alice', projectId: null }), []);
  });

  await test('late chat results and progress are not delivered after an account switch (issue 08)', async () => {
    reset();
    scope.setBusinessScope({ userId: 'alice', projectId: null });
    const poll = deferred();
    globalThis.fetch = async (url, init = {}) => {
      if (url.endsWith('/api/chat/scope')) return json({ userId: 'alice', projectId: null });
      if (init.method === 'POST') return json({ turn_id: 't2', conversation_id: 'c2', status: 'queued', message: '', result: null, error: null });
      await poll.promise;
      return json({ turn_id: 't2', conversation_id: 'c2', status: 'succeeded', message: '', result: { content: 'private' }, error: null });
    };
    const submitted = chat.sendChat({ message: 'x', conversation_id: null, workspace_id: null, client_turn_id: 't2',
      interaction_mode: 'chat', selected_skills: [], dataset_id: null, language: 'en' });
    await new Promise((r) => setTimeout(r, 10));
    const before = events.length;
    scope.setBusinessScope({ userId: 'bob', projectId: null });
    poll.resolve();
    await assert.rejects(submitted, (error) => error.name === 'StaleScopeError');
    assert.equal(events.slice(before).some((turn) => turn.result), false, 'no private progress after the switch');
  });

  await test('cleanup removes every cached query of the previous scope', () => {
    reset();
    const client = new QueryClient({ defaultOptions: { queries: { queryKeyHashFn: scope.scopedQueryHash } } });
    scope.setBusinessScope({ userId: 'alice', projectId: null });
    client.setQueryData(['conversation', 'c1'], { title: 'alice private' });
    localStorage.setItem('neuroweave:pending-chat-turns:alice:personal', '["t1"]');
    scope.setBusinessScope({ userId: 'bob', projectId: null });
    assert.equal(client.getQueryData(['conversation', 'c1']), undefined, 'hash is scoped');
    cleanupBusinessContext(client, { userId: 'alice', projectId: null }, scope.currentScope());
    assert.equal(client.getQueryCache().getAll().length, 0);
    assert.equal(localStorage.getItem('neuroweave:pending-chat-turns:alice:personal'), null);
  });

  await test('draft recovery copies are bound to the signed-in user', async () => {
    reset();
    globalThis.fetch = async () => json({ items: [], deleted_ids: [], deleted_items: [] });
    scope.setBusinessScope({ userId: 'alice', projectId: null });
    localStorage.setItem(scope.scopedStorageKey('pipeline-draft', 'a1'), JSON.stringify({ id: 'a1', revision: 1, updated_at: 'x', editor: { name: 'a' } }));
    scope.setBusinessScope({ userId: 'bob', projectId: null });
    localStorage.setItem('neuroweave:pipeline-draft:legacy', JSON.stringify({ id: 'legacy', revision: 1, updated_at: 'x', editor: { name: 'l' } }));
    assert.deepEqual((await library.drafts()).items.map((d) => d.id), []);
    scope.setBusinessScope({ userId: 'alice', projectId: null });
    assert.deepEqual((await library.drafts()).items.map((d) => d.id), ['a1']);
  });

  await test('allowed actions drive buttons; takeover is offered only to platform administrators', () => {
    const shared = { allowed_actions: ['read', 'export'], access: { creator_id: 'alice', manager_id: 'alice', project_id: 'p1', scope: 'project', permission_revision: 0 } };
    assert.equal(auth.can(shared, 'read'), true);
    assert.equal(auth.can(shared, 'cancel'), false);
    assert.equal(auth.can(undefined, 'read'), false);
    assert.deepEqual(auth.managementActions(shared), []);
    assert.deepEqual(auth.managementActions(shared, { platformAdmin: true }), ['takeover']);
    assert.deepEqual(auth.scopeLabel(shared, 'bob'), { scope: 'project', owner: 'other', managerId: 'alice', creatorId: 'alice' });
    const member = renderToStaticMarkup(createElement(ResourcePolicyPanel, { resource: shared, currentUserId: 'bob', onShare() {}, onHandover() {}, onTakeover() {} }));
    assert.ok(!member.includes('<button'), member);
    const owner = renderToStaticMarkup(createElement(ResourcePolicyPanel, {
      resource: { ...shared, allowed_actions: ['read', 'share', 'handover'] }, currentUserId: 'alice', onShare() {}, onHandover() {} }));
    assert.equal((owner.match(/<button/g) ?? []).length, 2);
  });

  await test('directory settings hide management controls without server permission', () => {
    const grants = [{ grant_id: 'g1', root: '/data/a', scope: 'read', revision: 1 }];
    const viewer = renderToStaticMarkup(createElement(DirectoryScopeSettings, { projectId: 'p1', grants, canManage: false, onCreate() {}, onRevoke() {} }));
    assert.ok(viewer.includes('/data/a') && !viewer.includes('<form') && !viewer.includes('<button'));
    const admin = renderToStaticMarkup(createElement(DirectoryScopeSettings, { projectId: 'p1', grants, canManage: true, onCreate() {}, onRevoke() {} }));
    assert.ok(admin.includes('<form') && admin.includes('<button'));
  });
  reset();
} finally {
  await server.close();
}
