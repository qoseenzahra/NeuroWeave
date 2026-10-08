import type { AuthorizedResource, ResourceAction } from "./authorization";

export interface ResourcePolicyPanelProps {
  resource: AuthorizedResource;
  onAction?: (action: ResourceAction) => void;
}

export function ResourcePolicyPanel({ resource, onAction }: ResourcePolicyPanelProps) {
  return (
    <section aria-label="Resource permissions">
      <strong>{resource.scope === "project" ? "Project resource" : "Private resource"}</strong>
      <div>
        {resource.allowedActions.map((action) => (
          <button key={action} type="button" onClick={() => onAction?.(action)}>
            {action}
          </button>
        ))}
      </div>
    </section>
  );
}
