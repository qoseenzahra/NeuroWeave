'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import type { ExecutionBackends, ExecutionOptions, NodeAllocation, SlurmNode, Workflow } from '@/lib/workflow';

const FIELDS = [
  ['cpus', 'CPU 核数', 1, 128],
  ['memory_gb', '内存 (GB)', 1, 512],
  ['gpus', 'GPU 数量', 0, 1],
  ['time_minutes', '时限 (分钟)', 1, 1440],
] as const;

export function executionErrors(value: ExecutionOptions, backends: ExecutionBackends | null, workflow: Workflow): string[] {
  if (value.backend !== 'slurm') return [];
  const errors: string[] = [];
  const nodes = value.nodes ?? [];
  const batch = value.sample_mode === 'per_sample';
  const count = workflow.dataset?.inspection.sample_count ?? 0;
  if (!backends?.slurm.available || !backends.slurm.partitions.includes(value.partition)) errors.push('请选择可用的 Slurm 分区。');
  if (batch && (!nodes.length || !count)) errors.push('按样本运行需要有效的样本清单和至少一个节点。');
  if (nodes.length > (batch ? count : 1)) errors.push('节点数不能多于待运行样本数。');
  if (!batch && workflow.steps.some(step => Object.values(step.input_bindings ?? {}).some(
    binding => binding.binding_mode === 'per_sample' && (binding.coverage?.total ?? 0) > 1,
  ))) errors.push('当前输入包含多个样本，请选择按样本运行。');
  for (const allocation of nodes.length ? nodes : [value]) {
    const name = 'node' in allocation ? allocation.node : null;
    const node = name ? backends?.slurm.nodes?.find(item => item.name === name && item.partition === value.partition) : undefined;
    if (name && (!node || !node.schedulable)) errors.push(`节点 ${name} 当前不可调度，请重新选择。`);
    for (const [key, label, min, max] of FIELDS) {
      const capacity = key === 'cpus' ? node?.cpus
        : key === 'memory_gb' && node?.memory_mb ? Math.floor(node.memory_mb / 1024)
        : key === 'gpus' ? node?.gpus : undefined;
      const limit = Math.min(max, capacity ?? max);
      if (!Number.isInteger(allocation[key]) || allocation[key] < min || allocation[key] > limit) {
        errors.push(`${name ?? '资源申请'}：${label}需为 ${min}–${limit} 的整数。`);
      }
    }
    if (allocation.gpus && !backends?.slurm.gpu_available) errors.push('当前没有可调度的 GPU。');
    for (const step of workflow.steps) {
      for (const key of ['threads', 'omp_threads', 'n_jobs']) {
        const threads = step.selected_parameters[key];
        if (typeof threads === 'number' && (threads < 1 || threads > allocation.cpus)) {
          errors.push(`${name ?? '资源申请'}：CPU 核数应至少为方法线程数 ${threads}。`);
        }
      }
      if ((step.selected_parameters.backend === 'cuda' || step.selected_parameters.device === 'cuda') && !allocation.gpus) {
        errors.push(`${name ?? '资源申请'}：当前 CUDA 方法需要 GPU。`);
      }
    }
  }
  return [...new Set(errors)];
}

function ResourceFields({ id, value, node, disabled, onChange }: {
  id: string; value: NodeAllocation | ExecutionOptions; node?: SlurmNode; disabled: boolean;
  onChange: (key: typeof FIELDS[number][0], number: number) => void;
}) {
  return <div className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,8rem),1fr))] gap-3">
    {FIELDS.map(([key, label, min, max]) => {
      const capacity = key === 'cpus' ? node?.cpus
        : key === 'memory_gb' && node?.memory_mb ? Math.floor(node.memory_mb / 1024)
        : key === 'gpus' ? node?.gpus : undefined;
      return <div className="min-w-0 space-y-1.5" key={key}>
        <Label className="wrap-anywhere" htmlFor={id + key}>{label}</Label>
        <Input id={id + key} disabled={disabled || capacity === 0} min={min} max={Math.min(max, capacity ?? max)}
          type="number" step={1} value={Number.isFinite(value[key]) ? value[key] : ''}
          onChange={event => onChange(key, event.target.value === '' ? Number.NaN : Number(event.target.value))} />
      </div>;
    })}
  </div>;
}

export function ExecutionSettings({ value, backends, workflow, disabled, onChange }: {
  value: ExecutionOptions; backends: ExecutionBackends | null; workflow: Workflow;
  disabled: boolean; onChange: (value: ExecutionOptions) => void;
}) {
  const nodes = value.nodes ?? [];
  const available = backends?.slurm.nodes?.filter(node => node.partition === value.partition) ?? [];
  const batch = value.sample_mode === 'per_sample';
  const count = workflow.dataset?.inspection.sample_count ?? 0;
  const errors = executionErrors(value, backends, workflow);
  const allocation = (node: SlurmNode): NodeAllocation => ({
    node: node.name, cpus: Math.min(value.cpus, node.cpus ?? 128),
    memory_gb: Math.min(value.memory_gb, Math.floor((node.memory_mb ?? 512 * 1024) / 1024)),
    gpus: Math.min(value.gpus, node.gpus), time_minutes: value.time_minutes,
  });
  return <div className="min-w-0 space-y-4">
    <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,12rem),1fr))] gap-3">
      <div className="min-w-0 space-y-1.5">
        <Label htmlFor={'partition-' + workflow.workflow_id}>分区</Label>
        <NativeSelect className="w-full" id={'partition-' + workflow.workflow_id} disabled={disabled}
          value={value.partition} onChange={event => onChange({ ...value, partition: event.target.value, nodes: [], node: null })}>
          {(backends?.slurm.partitions ?? []).map(partition => <NativeSelectOption key={partition} value={partition}>{partition}</NativeSelectOption>)}
        </NativeSelect>
      </div>
      <div className="min-w-0 space-y-1.5">
        <Label htmlFor={'samples-' + workflow.workflow_id}>样本运行方式</Label>
        <NativeSelect className="w-full" id={'samples-' + workflow.workflow_id} disabled={disabled}
          value={value.sample_mode ?? 'single'} onChange={event => onChange({
            ...value, sample_mode: event.target.value as 'single' | 'per_sample', nodes: nodes.slice(0, 1), node: null,
          })}>
          <NativeSelectOption value="single">运行当前输入</NativeSelectOption>
          <NativeSelectOption value="per_sample" disabled={count < 1}>按样本运行（{count} 个样本）</NativeSelectOption>
        </NativeSelect>
      </div>
    </div>
    {!batch && <div className="space-y-1.5">
      <Label htmlFor={'node-' + workflow.workflow_id}>运行节点</Label>
      <NativeSelect className="w-full" id={'node-' + workflow.workflow_id} disabled={disabled}
        value={nodes[0]?.node ?? ''} onChange={event => {
          const node = available.find(item => item.name === event.target.value);
          onChange({ ...value, node: null, nodes: node ? [allocation(node)] : [] });
        }}>
        <NativeSelectOption value="">由 Slurm 自动选择</NativeSelectOption>
        {available.map(node => <NativeSelectOption key={node.name} value={node.name} disabled={!node.schedulable}>
          {node.name} · {node.state} · {node.cpus ?? '?'} 核 · {node.gpus} GPU
        </NativeSelectOption>)}
      </NativeSelect>
    </div>}
    {batch && <fieldset className="min-w-0 space-y-2">
      <legend className="mb-2 text-sm font-medium">选择并行节点</legend>
      <div className="flex flex-wrap gap-2">
        {available.map(node => <label key={node.name} className="flex min-w-0 items-center gap-2 rounded-lg border p-2 text-sm">
          <input type="checkbox" aria-label={`使用节点 ${node.name}`} checked={nodes.some(item => item.node === node.name)}
            disabled={disabled || !node.schedulable}
            onChange={event => onChange({ ...value, nodes: event.target.checked
              ? [...nodes, allocation(node)] : nodes.filter(item => item.node !== node.name) })} />
          <span className="wrap-anywhere">{node.name} · {node.schedulable ? node.state : '不可调度'}</span>
        </label>)}
      </div>
      <p className="text-xs leading-5 text-slate-500">样本依次分配到所选节点；每个节点同时处理一个样本，各样本内部按流程顺序执行。</p>
    </fieldset>}
    {nodes.map((item, index) => {
      const node = available.find(row => row.name === item.node);
      const assigned = batch ? Math.floor(count / nodes.length) + (index < count % nodes.length ? 1 : 0) : 1;
      return <section className="min-w-0 space-y-3 rounded-lg border bg-slate-50 p-3" key={item.node} aria-label={`${item.node} 资源配置`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">{item.node} {batch && <span className="font-normal text-slate-500">· {assigned} 个样本</span>}</h4>
          {batch && <Button size="sm" variant="ghost" disabled={disabled}
            onClick={() => onChange({ ...value, nodes: nodes.filter(row => row.node !== item.node) })}>移除节点</Button>}
        </div>
        <p className="wrap-anywhere text-xs text-slate-500">
          容量 {node?.cpus ?? '?'} 核 · {node?.memory_mb ? Math.floor(node.memory_mb / 1024) : '?'} GB · {node?.gpus ?? 0} GPU
          {node?.allocated_cpus !== undefined && ` · 已分配 ${node.allocated_cpus} 核`}
        </p>
        <ResourceFields id={workflow.workflow_id + item.node} value={item} node={node} disabled={disabled}
          onChange={(key, number) => onChange({ ...value, nodes: nodes.map(row => row.node === item.node ? { ...row, [key]: number } : row) })} />
      </section>;
    })}
    {!nodes.length && !batch && <ResourceFields id={workflow.workflow_id} value={value} disabled={disabled}
      onChange={(key, number) => onChange({ ...value, [key]: number })} />}
    <p className="text-xs leading-5 text-slate-500">资源与时限按每个步骤申请，忙碌时由 Slurm 排队。方法里的线程参数保持不变，申请 CPU 应不少于方法线程数。</p>
    {errors.length > 0 && <ul role="alert" className="list-inside list-disc space-y-1 wrap-anywhere text-xs text-red-700">
      {errors.map(error => <li key={error}>{error}</li>)}
    </ul>}
  </div>;
}
