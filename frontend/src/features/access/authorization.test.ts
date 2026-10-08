import { can, scopeKey } from "./authorization";

function assert(condition: boolean): void {
  if (!condition) {
    throw new Error("Task B authorization assertion failed");
  }
}

const resource = {
  id: "task-1",
  scope: "private" as const,
  allowedActions: ["read", "cancel"] as const,
};

assert(can(resource, "cancel") === true);
assert(can(resource, "retry") === false);
assert(scopeKey("u1", "p1") !== scopeKey("u2", "p1"));
assert(scopeKey("u1", "p1") !== scopeKey("u1", "p2"));
assert(can(undefined, "read") === false);
