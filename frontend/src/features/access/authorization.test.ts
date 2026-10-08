import assert from "node:assert/strict";
import test from "node:test";
import { can, scopeKey } from "./authorization";

test("business authorization uses server-provided allowed actions", () => {
  const resource = {
    id: "task-1",
    scope: "private" as const,
    allowedActions: ["read", "cancel"] as const,
  };
  assert.equal(can(resource, "cancel"), true);
  assert.equal(can(resource, "retry"), false);
});

test("business scope is isolated by user and project", () => {
  assert.notEqual(scopeKey("u1", "p1"), scopeKey("u2", "p1"));
  assert.notEqual(scopeKey("u1", "p1"), scopeKey("u1", "p2"));
});

test("missing resource never receives an invented permission", () => {
  assert.equal(can(undefined, "read"), false);
});
