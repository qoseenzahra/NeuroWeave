import { describe, expect, it } from "vitest";
import { can, scopeKey } from "./authorization";

describe("business authorization", () => {
  it("uses server-provided allowed actions", () => {
    const resource = {
      id: "task-1",
      scope: "private" as const,
      allowedActions: ["read", "cancel"] as const,
    };
    expect(can(resource, "cancel")).toBe(true);
    expect(can(resource, "retry")).toBe(false);
  });

  it("isolates cached business scope by user and project", () => {
    expect(scopeKey("u1", "p1")).not.toBe(scopeKey("u2", "p1"));
    expect(scopeKey("u1", "p1")).not.toBe(scopeKey("u1", "p2"));
  });

  it("never invents permission when resource is absent", () => {
    expect(can(undefined, "read")).toBe(false);
  });
});
