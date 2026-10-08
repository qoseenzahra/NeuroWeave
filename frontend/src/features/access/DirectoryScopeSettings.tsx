export interface DirectoryScopeSettingsProps {
  projectId: string;
  roots: readonly string[];
  onChange?: (roots: readonly string[]) => void;
}

export function DirectoryScopeSettings({ projectId, roots, onChange }: DirectoryScopeSettingsProps) {
  return (
    <section aria-label="Directory scope settings">
      <h3>Directory scope</h3>
      <p>Project: {projectId}</p>
      <ul>{roots.map((root) => <li key={root}>{root}</li>)}</ul>
      <button type="button" onClick={() => onChange?.(roots)}>Save directory scope</button>
    </section>
  );
}
