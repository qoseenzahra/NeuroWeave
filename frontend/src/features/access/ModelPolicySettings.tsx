import { ui } from '../../lib/libraryText';
import type { ModelPolicy, UsageSummary } from './accessApi';

export interface ModelPolicySettingsProps {
  policy: ModelPolicy;
  usage?: UsageSummary;
  onChange?: (allow: boolean) => void;
  busy?: boolean;
}

/** Whether file text may be sent to an external model, plus recorded usage. */
export function ModelPolicySettings({ policy, usage, onChange, busy }: ModelPolicySettingsProps) {
  return (
    <section aria-label={ui('外部模型策略')} className="space-y-1.5">
      <p className="text-meta font-medium text-muted">{ui('外部模型策略')}</p>
      <label className="flex items-center gap-2 text-meta">
        <input type="checkbox" checked={policy.allow_external_file_text} disabled={!policy.can_manage || busy || !onChange}
          onChange={(event) => onChange?.(event.target.checked)} />
        {ui('允许把文件内容发送给外部模型')}
      </label>
      {usage && <p className="text-micro text-subtle">{ui('已记录 {0} 次模型调用，共 {1} 个 token', usage.calls, usage.total_tokens)}</p>}
    </section>
  );
}
