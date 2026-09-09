import type { SampleScope } from '@/lib/workflow';

/** Keep the full dataset identity visible without expanding a long task list. */
export function SampleScopeNotice({ scope }: { scope?: SampleScope | null }) {
  if (!scope) return null;
  return <section aria-label="样本输入覆盖范围" className="my-3 min-w-0 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
    <p className="wrap-anywhere">
      原数据集 {scope.total} 个样本；共同匹配 {scope.eligible_sample_ids.length} 个，跳过 {scope.skipped_samples.length} 个。
      {scope.eligible_sample_ids.length ? '只对共同满足各项输入的样本执行。' : '请调整输入后再运行。'}
    </p>
    {scope.skipped_samples.length > 0 && <details className="mt-2 min-w-0">
      <summary className="cursor-pointer">查看跳过的样本和原因（{scope.skipped_samples.length}）</summary>
      <ul className="mt-2 max-h-52 space-y-2 overflow-y-auto overscroll-contain pr-2 text-xs">
        {scope.skipped_samples.map(sample => <li key={sample.sample_id} className="wrap-anywhere">
          <span className="font-medium">{sample.label}（{sample.sample_id}）</span>
          <p>{sample.reasons.join('；')}</p>
        </li>)}
      </ul>
    </details>}
  </section>;
}
