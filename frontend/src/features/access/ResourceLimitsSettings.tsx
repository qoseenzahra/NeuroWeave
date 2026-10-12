import { useState } from 'react';
import { ui } from '../../lib/libraryText';
import type { QuotaPolicy } from './accessApi';

export interface ResourceLimitsSettingsProps {
  /** Quota subject: `default`, `user:<id>` or `project:<id>`. */
  subject: string;
  policy: QuotaPolicy;
  reservedUnits?: number;
  canManage: boolean;
  onSave?: (policy: QuotaPolicy) => void;
  busy?: boolean;
}

const FIELDS: { key: Exclude<keyof QuotaPolicy, 'allowed_nodes'>; label: string; min: number }[] = [
  { key: 'max_concurrent_units', label: '并发执行单元上限', min: 1 },
  { key: 'max_cpus_per_unit', label: '每单元 CPU 上限', min: 1 },
  { key: 'max_memory_gb_per_unit', label: '每单元内存上限（GB）', min: 1 },
  { key: 'max_gpus_per_unit', label: '每单元 GPU 上限', min: 0 },
];

/** Concurrency quota (in actual execution units) and per-unit resource limits. */
export function ResourceLimitsSettings({ subject, policy, reservedUnits, canManage, onSave, busy }: ResourceLimitsSettingsProps) {
  const [draft, setDraft] = useState<QuotaPolicy>(policy);
  return (
    <section aria-label={ui('执行资源限制')} className="space-y-1.5">
      <p className="text-meta font-medium text-muted">{ui('执行资源限制')}</p>
      <p className="text-micro text-subtle">{subject}</p>
      {reservedUnits !== undefined && (
        <p className="text-meta text-subtle">{ui('当前占用 {0} / {1} 个执行单元', reservedUnits, policy.max_concurrent_units)}</p>
      )}
      <div className="grid grid-cols-2 gap-1.5">
        {FIELDS.map((field) => (
          <label key={field.key} className="text-micro text-muted">
            {ui(field.label)}
            <input type="number" min={field.min} disabled={!canManage || busy}
              className="mt-0.5 w-full rounded-control border border-line bg-raised p-1.5 text-meta"
              value={draft[field.key]}
              onChange={(event) => setDraft({ ...draft, [field.key]: Number(event.target.value) })} />
          </label>
        ))}
      </div>
      {canManage && onSave && (
        <button type="button" className="rounded-control border border-line px-2 py-1 text-meta" disabled={busy} onClick={() => onSave(draft)}>
          {ui('保存限制')}
        </button>
      )}
    </section>
  );
}
