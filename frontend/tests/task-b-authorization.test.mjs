import test from 'node:test';
import assert from 'node:assert/strict';

function can(resource, action) {
  return Boolean(resource?.allowedActions?.includes(action));
}

function scopeKey(userId, projectId) {
  return `neuroweave:${userId}:${projectId ?? 'personal'}`;
}

test('Task B frontend authorization and scope isolation', () => {
  const resource = { id: 'task-1', allowedActions: ['read', 'cancel'] };
  assert.equal(can(resource, 'cancel'), true);
  assert.equal(can(resource, 'retry'), false);
  assert.notEqual(scopeKey('u1', 'p1'), scopeKey('u2', 'p1'));
  assert.notEqual(scopeKey('u1', 'p1'), scopeKey('u1', 'p2'));
  assert.equal(can(undefined, 'read'), false);
});
