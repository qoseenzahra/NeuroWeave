export interface OutputWriteGrantSettingsProps {
  projectId: string;
  writable: boolean;
  onChange?: (writable: boolean) => void;
}

export function OutputWriteGrantSettings({ projectId, writable, onChange }: OutputWriteGrantSettingsProps) {
  return (
    <section aria-label="Output write grant">
      <h3>Output write grant</h3>
      <p>Project: {projectId}</p>
      <button type="button" onClick={() => onChange?.(!writable)}>
        {writable ? "Revoke write grant" : "Grant write access"}
      </button>
    </section>
  );
}
