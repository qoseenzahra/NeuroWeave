export interface ResourceLimitsSettingsProps {
  projectId: string;
  maxExecutionUnits: number;
  concurrencyQuota: number;
  onChange?: (limits: { maxExecutionUnits: number; concurrencyQuota: number }) => void;
}

export function ResourceLimitsSettings({
  projectId, maxExecutionUnits, concurrencyQuota, onChange,
}: ResourceLimitsSettingsProps) {
  return (
    <section aria-label="Execution resource limits">
      <h3>Execution limits</h3>
      <p>Project: {projectId}</p>
      <label>
        Max execution units
        <input type="number" min={1} value={maxExecutionUnits}
          onChange={(event) => onChange?.({ maxExecutionUnits: Number(event.target.value), concurrencyQuota })} />
      </label>
      <label>
        Concurrency quota
        <input type="number" min={1} value={concurrencyQuota}
          onChange={(event) => onChange?.({ maxExecutionUnits, concurrencyQuota: Number(event.target.value) })} />
      </label>
    </section>
  );
}
