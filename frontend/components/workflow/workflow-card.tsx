'use client';

import { useEffect, useState } from 'react';
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleDashed,
  Code2,
  Database,
  FlaskConical,
  GitBranch,
  FileInput,
  FileOutput,
  FileText,
  Link2,
  LoaderCircle,
  LockKeyhole,
  Play,
  RefreshCw,
  RotateCcw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  Terminal,
  TriangleAlert,
  Trash2,
  UnlockKeyhole,
} from 'lucide-react';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { ExecutionSettings, executionErrors } from '@/components/workflow/execution-settings';
import { ArtifactPathPicker } from '@/components/dataset/artifact-path-picker';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import type {
  ExecutionBackends,
  ExecutionOptions,
  MethodOption,
  InputSlotSpec,
  ParameterOption,
  ParameterSpec,
  ParameterValue,
  RunEvent,
  Workflow,
  WorkflowRun,
  WorkflowStep,
} from '@/lib/workflow';

type WorkflowCardProps = {
  apiBase: string;
  workflow: Workflow;
  onChange: (workflow: Workflow) => void;
  disabled?: boolean;
  onBusyChange?: (workflowId: string, busy: boolean) => void;
};

type ApiError = {
  detail?: string | { code?: string; message?: string; current?: Workflow };
};

const STATUS_COPY: Record<Workflow['status'], string> = {
  awaiting_method_choice: '等待选择方法',
  awaiting_input_binding: '等待补充输入',
  chain_ready: '可以锁定流程',
  awaiting_parameter_review: '等待审核参数',
  awaiting_dry_run: '等待 Dry-run',
  ready: '可以最终确认',
  confirmed: '方案已确认',
};

const RUN_STATUS_COPY: Record<WorkflowRun['status'], string> = {
  queued: '等待运行',
  running: '正在运行',
  cancel_requested: '正在取消',
  cancelled: '已取消',
  succeeded: '运行成功',
  failed: '运行失败',
};

const ACTIVE_RUN_STATUSES = new Set<WorkflowRun['status']>([
  'queued',
  'running',
  'cancel_requested',
]);

const DEFAULT_EXECUTION: ExecutionOptions = {
  backend: 'local',
  partition: 'all',
  cpus: 4,
  memory_gb: 8,
  gpus: 0,
  time_minutes: 60,
};

const SCHEDULER_STATUS_COPY: Record<string, string> = {
  PENDING: '排队中',
  CONFIGURING: '正在分配资源',
  RUNNING: '正在计算',
  COMPLETING: '正在结束',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
  FAILED: '失败',
  TIMEOUT: '超出时限',
  OUT_OF_MEMORY: '内存不足',
  NODE_FAIL: '节点故障',
  PREEMPTED: '被抢占',
  SUSPENDED: '已暂停',
};

function selectedMethod(step: WorkflowStep) {
  return step.method_options.find((method) => method.id === step.selected_method_id);
}

function optionKey(value: ParameterValue) {
  return `${typeof value}:${String(value)}`;
}

function decodeOption(spec: ParameterSpec, key: string): ParameterValue {
  return spec.options.find((option) => optionKey(option.value) === key)?.value ?? key;
}

function isParameterVisible(spec: ParameterSpec, values: Record<string, ParameterValue>) {
  return Object.entries(spec.visible_when ?? {}).every(([parameterId, allowed]) => {
    const current = values[parameterId];
    return (
      current !== undefined && current !== null &&
      allowed.some((candidate) => optionKey(candidate) === optionKey(current))
    );
  });
}

function conditionMatches(
  condition: Record<string, ParameterValue[]>,
  values: Record<string, ParameterValue>,
) {
  return Object.entries(condition).every(([parameterId, allowed]) => {
    const current = values[parameterId];
    return current !== undefined && current !== null && allowed.some((item) => optionKey(item) === optionKey(current));
  });
}

function inputRequired(slot: InputSlotSpec, values: Record<string, ParameterValue>) {
  return slot.required ||
    (Object.keys(slot.required_when).length > 0 && conditionMatches(slot.required_when, values));
}

export function WorkflowCard({ apiBase, workflow, onChange, disabled = false, onBusyChange }: WorkflowCardProps) {
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [runBusy, setRunBusy] = useState<string | null>(null);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [runEvents, setRunEvents] = useState<RunEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [execution, setExecution] = useState<ExecutionOptions>(DEFAULT_EXECUTION);
  const [backendRefresh, setBackendRefresh] = useState(0);
  const backendKey = `${apiBase}:${workflow.workflow_id}:${workflow.status}:${backendRefresh}`;
  const [backendSnapshot, setBackendSnapshot] = useState<{
    key: string;
    backends: ExecutionBackends | null;
    error: string | null;
  } | null>(null);
  const backends = backendSnapshot?.key === backendKey ? backendSnapshot.backends : null;
  const backendError = backendSnapshot?.key === backendKey ? backendSnapshot.error : null;

  useEffect(() => {
    if (workflow.status !== 'confirmed') return;
    const controller = new AbortController();
    let current = true;
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    const loadBackends = async () => {
      try {
        const response = await fetch(`${apiBase}/api/execution/backends`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error('暂时无法查询 Slurm 状态');
        const payload = (await response.json()) as ExecutionBackends;
        if (!payload.slurm || !Array.isArray(payload.slurm.partitions)) {
          throw new Error('服务器尚未提供 Slurm 配置');
        }
        if (!current) return;
        setBackendSnapshot({ key: backendKey, backends: payload, error: null });
        setExecution((previous) => ({
          ...previous,
          partition: payload.slurm.partitions.includes(previous.partition)
            ? previous.partition
            : payload.slurm.partitions[0] ?? '',
          gpus: payload.slurm.gpu_available ? previous.gpus : 0,
        }));
      } catch (requestError) {
        if (current) {
          setBackendSnapshot({
            key: backendKey,
            backends: null,
            error: requestError instanceof Error && requestError.name !== 'AbortError'
              ? requestError.message
              : 'Slurm 状态查询超时，请重试',
          });
        }
      } finally {
        window.clearTimeout(timeout);
      }
    };
    void loadBackends();
    return () => {
      current = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [apiBase, workflow.status, backendKey]);

  const slurmReady = Boolean(
    backends && backends.slurm.enabled !== false && backends.slurm.available && backends.slurm.partitions.length,
  );
  const slurmReason = backendError ?? (backends
    ? backends.slurm.reason || (slurmReady ? '' : 'Slurm 未启用或没有可用分区')
    : '正在检查 Slurm 状态…');
  const resourceErrors = executionErrors(execution, backends, workflow);
  const executionBlocked = execution.backend === 'slurm' && (!slurmReady || resourceErrors.length > 0);

  useEffect(() => {
    let current = true;
    setRun(null);
    setRunEvents([]);
    setExecution(DEFAULT_EXECUTION);
    const loadLatestRun = async () => {
      try {
        const response = await fetch(
          `${apiBase}/api/runs?workflow_id=${encodeURIComponent(workflow.workflow_id)}&limit=1`,
        );
        if (!response.ok) return;
        const payload = (await response.json()) as { runs?: WorkflowRun[] };
        const latest = payload.runs?.[0] ?? null;
        if (!current) return;
        setRun(latest);
        if (latest) {
          const eventResponse = await fetch(`${apiBase}/api/runs/${latest.run_id}/events`);
          if (eventResponse.ok && current) {
            const eventPayload = (await eventResponse.json()) as { events?: RunEvent[] };
            setRunEvents(eventPayload.events ?? []);
          }
        }
      } catch {
        // Workflow planning remains usable when the optional run service is unavailable.
      }
    };
    void loadLatestRun();
    return () => {
      current = false;
    };
  }, [apiBase, workflow.workflow_id]);

  useEffect(() => {
    if (!run || !ACTIVE_RUN_STATUSES.has(run.status)) return;
    let current = true;
    const refresh = async () => {
      try {
        const [runResponse, eventResponse] = await Promise.all([
          fetch(`${apiBase}/api/runs/${run.run_id}`),
          fetch(`${apiBase}/api/runs/${run.run_id}/events`),
        ]);
        if (runResponse.ok && current) setRun((await runResponse.json()) as WorkflowRun);
        if (eventResponse.ok && current) {
          const payload = (await eventResponse.json()) as { events?: RunEvent[] };
          setRunEvents(payload.events ?? []);
        }
      } catch {
        // Keep the latest persisted snapshot visible and retry on the next interval.
      }
    };
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [apiBase, run?.run_id, run?.status]);

  const mutate = async (
    action: string,
    path: string,
    method: 'POST' | 'PATCH',
    body: Record<string, unknown> = {},
  ) => {
    if (disabled || busyAction) return;
    onBusyChange?.(workflow.workflow_id, true);
    setBusyAction(action);
    setError(null);
    try {
      const response = await fetch(`${apiBase}${path}`, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...body, expected_revision: workflow.revision }),
      });
      const payload = (await response.json()) as Workflow | ApiError;
      if (!response.ok) {
        const detail = (payload as ApiError).detail;
        if (typeof detail === 'object' && detail?.current) {
          onChange(detail.current);
          throw new Error(detail.message ?? '流程已在别处更新，已载入最新版本');
        }
        throw new Error(typeof detail === 'string' ? detail : '工作流更新失败');
      }
      onChange(payload as Workflow);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '工作流更新失败');
    } finally {
      setBusyAction(null);
      onBusyChange?.(workflow.workflow_id, false);
    }
  };

  const chooseMethod = (stepId: string, methodId: string) =>
    mutate(
      `method:${stepId}`,
      `/api/workflows/${workflow.workflow_id}/steps/${stepId}/method`,
      'PATCH',
      { method_id: methodId },
    );

  const updateParameter = (stepId: string, parameterId: string, value: ParameterValue) =>
    mutate(
      `parameter:${stepId}:${parameterId}`,
      `/api/workflows/${workflow.workflow_id}/steps/${stepId}/parameters`,
      'PATCH',
      { parameters: { [parameterId]: value } },
    );

  const bindInput = (stepId: string, slotId: string, rootId: string, relativePath: string) =>
    mutate(
      `input:${stepId}:${slotId}`,
      `/api/workflows/${workflow.workflow_id}/steps/${stepId}/inputs/${slotId}`,
      'PATCH',
      { root_id: rootId, relative_path: relativePath },
    );

  const startRun = async () => {
    if (executionBlocked) {
      setError(!slurmReady ? slurmReason : '请检查 Slurm 分区及资源申请');
      return;
    }
    setRunBusy('start');
    setError(null);
    try {
      const response = await fetch(
        `${apiBase}/api/workflows/${workflow.workflow_id}/runs`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_revision: workflow.revision,
            execution: execution.backend === 'slurm' ? execution : { backend: 'local' },
          }),
        },
      );
      const payload = (await response.json()) as WorkflowRun | ApiError;
      if (!response.ok || !('run_id' in payload)) {
        const detail = (payload as ApiError).detail;
        throw new Error(
          typeof detail === 'string'
            ? detail
            : typeof detail === 'object' && detail?.message
              ? detail.message
              : '无法启动运行',
        );
      }
      setRun(payload);
      setRunEvents([]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '无法启动运行');
    } finally {
      setRunBusy(null);
    }
  };

  const controlRun = async (action: 'cancel' | 'resume-monitoring') => {
    if (!run) return;
    setRunBusy(action);
    setError(null);
    const failureMessage = action === 'cancel' ? '无法取消运行' : '无法恢复监控';
    try {
      const response = await fetch(`${apiBase}/api/runs/${run.run_id}/${action}`, {
        method: 'POST',
      });
      const payload = (await response.json()) as WorkflowRun | ApiError;
      if (!response.ok || !('run_id' in payload)) {
        const detail = (payload as ApiError).detail;
        throw new Error(typeof detail === 'string' ? detail : failureMessage);
      }
      setRun(payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : failureMessage);
    } finally {
      setRunBusy(null);
    }
  };

  const locked = workflow.locked_at !== null;
  const configuredCount = workflow.steps.filter((step) => step.selected_method_id).length;
  const controlsDisabled = disabled || Boolean(busyAction) || workflow.status === 'confirmed';
  const runActive = Boolean(run && ACTIVE_RUN_STATUSES.has(run.status));

  return (
    <Card className="mt-5 w-full border-blue-100 bg-white shadow-[0_18px_50px_rgba(15,23,42,0.08)] ring-blue-100">
      <CardHeader className="border-b border-slate-100 bg-gradient-to-r from-blue-50/80 via-white to-cyan-50/60">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-blue-600 text-white shadow-[0_8px_20px_rgba(37,99,235,0.22)]">
            <GitBranch className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle>{workflow.title}</CardTitle>
              <Badge
                className={cn(
                  'rounded-md shadow-none',
                  workflow.status === 'confirmed'
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-blue-50 text-blue-700',
                )}
              >
                {STATUS_COPY[workflow.status]}
              </Badge>
              <Badge variant="outline" className="rounded-md font-mono text-[10px]">
                {workflow.plan_kind === 'atomic' ? '单步任务' : '组合任务'}
              </Badge>
              <Badge
                className={cn(
                  'rounded-md text-[10px] shadow-none',
                  workflow.execution_mode === 'runner'
                    ? 'bg-emerald-50 text-emerald-700'
                    : workflow.execution_mode === 'mixed'
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'bg-amber-50 text-amber-700',
                )}
              >
                {workflow.execution_mode === 'runner'
                  ? 'Runner 结构化'
                  : workflow.execution_mode === 'mixed'
                    ? '混合流程'
                    : '规划型结构化'}
              </Badge>
              <Badge
                className="rounded-md bg-violet-50 text-[10px] text-violet-700 shadow-none"
                title={workflow.planner_source}
              >
                能力树规划
              </Badge>
            </div>
            <CardDescription className="mt-1 leading-5">
              {workflow.summary} · {configuredCount}/{workflow.steps.length} 个步骤已选定方法
            </CardDescription>
            {workflow.dataset && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
                <Database className="size-3.5 text-blue-600" />
                <span className="font-medium text-slate-700">{workflow.dataset.display_name}</span>
                {workflow.dataset.inspection.is_bids && <Badge variant="outline">BIDS</Badge>}
                {workflow.dataset.inspection.has_dwi && <Badge variant="outline">DWI</Badge>}
                {workflow.dataset.inspection.has_t1w && <Badge variant="outline">T1w</Badge>}
                {workflow.dataset.inspection.has_fod && <Badge variant="outline">FOD</Badge>}
                {workflow.dataset.inspection.has_five_tt && <Badge variant="outline">5TT</Badge>}
                <Badge variant="outline">
                  {workflow.dataset.inspection.sample_count} 样本
                </Badge>
              </div>
            )}
          </div>
          <span className="font-mono text-[10px] text-slate-400">R{workflow.revision}</span>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {workflow.warnings.map((warning) => (
          <Alert className="border-amber-200 bg-amber-50 text-amber-900" key={warning}>
            <TriangleAlert />
            <AlertDescription className="text-amber-800">{warning}</AlertDescription>
          </Alert>
        ))}

        <div className="space-y-3">
          {workflow.status !== 'confirmed' && (
            <p className="text-sm leading-6 text-slate-600">
              {locked
                ? '需要精简流程时，先解锁，再移除不需要的步骤。'
                : '可移除不需要的步骤。保留步骤所需的输入，可在锁定流程后选择已有文件。'}
              {Boolean(workflow.excluded_capabilities?.length) && ' 已移除的步骤不会因重新规划或补全依赖而恢复。'}
            </p>
          )}
          {workflow.steps.map((step, index) => {
            const method = selectedMethod(step);
            const methodBusy = busyAction === `method:${step.id}`;
            return (
              <section
                className={cn(
                  'relative rounded-xl border bg-slate-50/60 p-4',
                  step.status === 'needs_method' ? 'border-blue-200' : 'border-slate-200',
                )}
                key={step.id}
              >
                {index < workflow.steps.length - 1 && (
                  <span className="absolute -bottom-4 left-[29px] z-10 grid size-5 place-items-center rounded-full border border-slate-200 bg-white text-slate-400">
                    <ChevronRight className="size-3 rotate-90" />
                  </span>
                )}
                <div className="flex items-start gap-3">
                  <span
                    className={cn(
                      'grid size-8 shrink-0 place-items-center rounded-full border text-xs font-semibold',
                      method
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : 'border-blue-200 bg-blue-50 text-blue-700',
                    )}
                  >
                    {method ? <Check className="size-4" /> : step.order}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900">{step.title}</h3>
                        <p className="mt-0.5 text-xs leading-5 text-slate-500">{step.description}</p>
                      </div>
                      {method && (
                        <div className="flex flex-wrap items-center gap-1.5">
                          {step.origin === 'dependency' && (
                            <Badge className="rounded-md bg-cyan-50 text-[10px] text-cyan-700 shadow-none">
                              自动补充上游
                            </Badge>
                          )}
                          <Badge
                            className={cn(
                              'rounded-md text-[10px] shadow-none',
                              method.execution_mode === 'planning'
                                ? 'bg-amber-50 text-amber-700'
                                : 'bg-emerald-50 text-emerald-700',
                            )}
                          >
                            {method.execution_mode === 'planning'
                              ? '仅规划'
                              : method.execution_recipe
                                ? `Runner 流程 · ${method.execution_recipe.steps.length} 步`
                                : 'Runner'}
                          </Badge>
                          <Badge variant="outline" className="rounded-md bg-white font-mono text-[10px]">
                            {method.skill_id}
                          </Badge>
                        </div>
                      )}
                      {!locked && workflow.status !== 'confirmed' && (
                        <Button
                          aria-label={`移除步骤：${step.title}`}
                          disabled={controlsDisabled || workflow.steps.length <= 1}
                          onClick={() => void mutate(
                            `remove:${step.id}`,
                            `/api/workflows/${workflow.workflow_id}/steps/${step.id}/remove`,
                            'POST',
                          )}
                          size="sm"
                          variant="outline"
                          title={workflow.steps.length <= 1 ? '至少保留一个步骤' : '移除后可手动选择下游输入'}
                        >
                          {busyAction === `remove:${step.id}` ? <LoaderCircle className="animate-spin" /> : <Trash2 />}
                          移除步骤
                        </Button>
                      )}
                    </div>

                    {!locked && (step.method_options.length > 1 || !method) && (
                      <RadioGroup
                        aria-label={`${step.title}方法`}
                        className="mt-3 grid gap-2"
                        disabled={controlsDisabled}
                        onValueChange={(value) => void chooseMethod(step.id, String(value))}
                        value={step.selected_method_id ?? ''}
                      >
                        {step.method_options.map((option) => (
                          <MethodChoice key={option.id} method={option} stepId={step.id} />
                        ))}
                      </RadioGroup>
                    )}

                    {!locked && step.method_options.length === 1 && method && (
                      <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600">
                        <span className="font-medium text-slate-800">{method.label}</span>
                        <span className="ml-2">{method.description}</span>
                      </div>
                    )}

                    {methodBusy && (
                      <p className="mt-2 flex items-center gap-2 text-xs text-blue-600">
                        <LoaderCircle className="size-3.5 animate-spin" />
                        正在更新流程并检查下游兼容性…
                      </p>
                    )}

                    {locked && method && (
                      <div className="mt-3 rounded-lg border border-emerald-100 bg-emerald-50/60 p-3">
                        <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-emerald-600">
                          已确定方法
                        </p>
                        <p className="mt-1 text-sm font-medium text-slate-800">{method.label}</p>
                        <p className="mt-1 text-xs leading-5 text-slate-500">{method.description}</p>
                        {method.execution_recipe && (
                          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-emerald-700">
                            {method.execution_recipe.steps.map((recipeStep, index) => (
                              <span className="inline-flex items-center gap-1" key={recipeStep.id}>
                                {index > 0 && <span className="text-emerald-300">→</span>}
                                <span className="rounded-md bg-white/80 px-1.5 py-0.5 ring-1 ring-emerald-100">
                                  {recipeStep.title}
                                </span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {locked && method && <MethodEvidence method={method} />}
                    {method && (locked || step.method_options.length === 1) && <MethodGuidance method={method} includeInputs={!locked} />}

                    {method && (locked || Boolean(step.manual_input_types?.length)) && ((method.input_slots?.length ?? 0) > 0 || (method.output_slots?.length ?? 0) > 0) && (
                      <MethodArtifacts
                        apiBase={apiBase}
                        busyAction={busyAction}
                        disabled={controlsDisabled || !locked}
                        method={method}
                        onBind={(slotId, rootId, relativePath) =>
                          void bindInput(step.id, slotId, rootId, relativePath)
                        }
                        onCompleteDependencies={() =>
                          void mutate(
                            'complete-dependencies',
                            `/api/workflows/${workflow.workflow_id}/complete-dependencies`,
                            'POST',
                          )
                        }
                        selectedParameters={step.selected_parameters}
                        step={step}
                        workflow={workflow}
                      />
                    )}

                    {locked && method && method.parameters.length > 0 && (
                      <StepParameters
                        busyAction={busyAction}
                        disabled={controlsDisabled}
                        method={method}
                        parametersReviewed={Boolean(workflow.parameters_reviewed_at)}
                        selectedParameters={step.selected_parameters}
                        stepId={step.id}
                        onChange={(parameterId, value) =>
                          void updateParameter(step.id, parameterId, value)
                        }
                      />
                    )}

                    {locked && method && step.command_preview && (
                      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2.5 text-slate-200">
                        <div className="mb-1.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.1em] text-slate-400">
                          <Code2 className="size-3.5" />
                          {method.execution_mode === 'planning'
                            ? '规划参数快照 · 不会执行'
                            : method.execution_recipe
                              ? '受信任 Runner 流程参数预览 · 确认后按步骤运行'
                              : '受信任 Runner 参数预览 · 确认后可运行'}
                        </div>
                        <code className="block overflow-x-auto whitespace-nowrap text-[11px] leading-5">
                          {step.command_preview}
                        </code>
                      </div>
                    )}
                  </div>
                </div>
              </section>
            );
          })}
        </div>

        {workflow.dry_run_report && (
          <Alert
            className={cn(
              workflow.dry_run_report.valid
                ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                : 'border-amber-200 bg-amber-50 text-amber-900',
            )}
          >
            {workflow.dry_run_report.valid ? <CheckCircle2 /> : <TriangleAlert />}
            <AlertDescription>
              <p className="font-medium">
                Dry-run {workflow.dry_run_report.valid ? '通过' : '未通过'} · 已校验{' '}
                {workflow.dry_run_report.commands.length} 个步骤
              </p>
              {workflow.dry_run_report.warnings.map((warning) => (
                <p className="mt-1 text-xs" key={warning}>
                  {warning}
                </p>
              ))}
            </AlertDescription>
          </Alert>
        )}

        {run && <RunPanel events={runEvents} run={run} />}

        {error && (
          <Alert variant="destructive">
            <TriangleAlert />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </CardContent>

      <CardFooter className="flex-wrap justify-between gap-3 bg-slate-50/80">
        {workflow.status === 'confirmed' && workflow.dry_run_report?.execution_enabled && !runActive && (
          <div className="w-full space-y-3 rounded-lg border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-center gap-3">
              <Label htmlFor={`execution-${workflow.workflow_id}`}>运行位置</Label>
              <NativeSelect
                disabled={Boolean(runBusy)}
                id={`execution-${workflow.workflow_id}`}
                onChange={(event) => setExecution((previous) => ({
                  ...previous,
                  backend: event.target.value as ExecutionOptions['backend'],
                }))}
                value={execution.backend}
              >
                <NativeSelectOption value="local">本地服务器</NativeSelectOption>
                <NativeSelectOption disabled={!slurmReady} value="slurm">Slurm 计算节点</NativeSelectOption>
              </NativeSelect>
              <Button
                disabled={Boolean(runBusy) || (!backends && !backendError)}
                onClick={() => setBackendRefresh((previous) => previous + 1)}
                size="sm"
                variant="ghost"
              >
                <RefreshCw className="size-3.5" />
                刷新可用资源
              </Button>
            </div>
            {!slurmReady && <output className="block text-xs text-slate-500">Slurm：{slurmReason}</output>}
            {execution.backend === 'slurm' && (
              <ExecutionSettings value={execution} backends={backends} workflow={workflow}
                disabled={Boolean(runBusy)} onChange={setExecution} />
            )}
          </div>
        )}
        <div className="flex items-center gap-2 text-xs text-slate-500">
          {workflow.status === 'confirmed' ? (
            <CheckCircle2 className="size-4 text-emerald-600" />
          ) : locked ? (
            <LockKeyhole className="size-4 text-blue-600" />
          ) : (
            <CircleDashed className="size-4 text-slate-400" />
          )}
          {workflow.status === 'confirmed'
            ? workflow.dry_run_report?.execution_enabled
              ? runActive
                ? '运行状态、日志和结果会持续保存'
                : '方案已确认，可以启动受信任 Runner'
              : '方案已保存；当前方法尚未接入可执行 Runner'
            : workflow.dry_run_report?.valid
              ? '安全检查已通过，可以最终确认'
              : locked
                ? workflow.status === 'awaiting_input_binding'
                  ? '流程链已确定；请补充必需输入，再设置并确认参数'
                  : '流程链已确定；参数变更会使审核和 Dry-run 失效'
                : '先完成所有兼容方法的选择'}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {workflow.status !== 'confirmed' && !locked && (
            <Button
              className="gap-2"
              disabled={controlsDisabled}
              onClick={() =>
                void mutate('replan', `/api/workflows/${workflow.workflow_id}/replan`, 'POST')
              }
              size="sm"
              variant="outline"
            >
              {busyAction === 'replan' ? <LoaderCircle className="animate-spin" /> : <RotateCcw />}
              重新规划
            </Button>
          )}
          {workflow.can_unlock && (
            <Button
              className="gap-2"
              disabled={controlsDisabled}
              onClick={() =>
                void mutate('unlock', `/api/workflows/${workflow.workflow_id}/unlock`, 'POST')
              }
              size="sm"
              variant="outline"
            >
              {busyAction === 'unlock' ? <LoaderCircle className="animate-spin" /> : <UnlockKeyhole />}
              解锁流程
            </Button>
          )}
          {workflow.can_lock && (
            <Button
              className="gap-2 bg-blue-600 hover:bg-blue-700"
              disabled={controlsDisabled}
              onClick={() =>
                void mutate('lock', `/api/workflows/${workflow.workflow_id}/lock`, 'POST')
              }
              size="sm"
            >
              {busyAction === 'lock' ? <LoaderCircle className="animate-spin" /> : <LockKeyhole />}
              确定流程链
            </Button>
          )}
          {workflow.can_review_parameters && (
            <Button
              className="gap-2 bg-blue-600 hover:bg-blue-700"
              disabled={controlsDisabled}
              onClick={() =>
                void mutate('review', `/api/workflows/${workflow.workflow_id}/review-parameters`, 'POST')
              }
              size="sm"
            >
              {busyAction === 'review' ? <LoaderCircle className="animate-spin" /> : <ShieldCheck />}
              确认参数
            </Button>
          )}
          {workflow.can_dry_run && (!workflow.dry_run_report || !workflow.dry_run_report.valid) && (
            <Button
              className="gap-2 bg-indigo-600 hover:bg-indigo-700"
              disabled={controlsDisabled}
              onClick={() =>
                void mutate('dry-run', `/api/workflows/${workflow.workflow_id}/dry-run`, 'POST')
              }
              size="sm"
            >
              {busyAction === 'dry-run' ? <LoaderCircle className="animate-spin" /> : <FlaskConical />}
              运行 Dry-run
            </Button>
          )}
          {workflow.can_dry_run && workflow.dry_run_report?.valid && (
            <Button
              className="gap-2"
              disabled={controlsDisabled}
              onClick={() =>
                void mutate('dry-run', `/api/workflows/${workflow.workflow_id}/dry-run`, 'POST')
              }
              size="sm"
              variant="outline"
            >
              {busyAction === 'dry-run' ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}
              重新检查
            </Button>
          )}
          {workflow.can_confirm && (
            <Button
              className="gap-2 bg-emerald-600 hover:bg-emerald-700"
              disabled={controlsDisabled}
              onClick={() =>
                void mutate('confirm', `/api/workflows/${workflow.workflow_id}/confirm`, 'POST')
              }
              size="sm"
            >
              {busyAction === 'confirm' ? <LoaderCircle className="animate-spin" /> : <CheckCircle2 />}
              最终确认方案
            </Button>
          )}
          {workflow.status === 'confirmed' && workflow.dry_run_report?.execution_enabled && !runActive && (
            <Button
              className="gap-2 bg-blue-600 hover:bg-blue-700"
              disabled={Boolean(runBusy) || executionBlocked}
              onClick={() => void startRun()}
              size="sm"
            >
              {runBusy === 'start' ? <LoaderCircle className="animate-spin" /> : <Play />}
              {run ? '再次运行' : '开始运行'}
            </Button>
          )}
          {runActive && (
            <Button
              className="gap-2"
              disabled={Boolean(runBusy) || run?.status === 'cancel_requested'}
              onClick={() => void controlRun('cancel')}
              size="sm"
              variant="outline"
            >
              {runBusy === 'cancel' ? <LoaderCircle className="animate-spin" /> : <Square />}
              取消运行
            </Button>
          )}
          {runActive && run?.execution?.backend === 'slurm' && (
            <Button
              disabled={Boolean(runBusy)}
              onClick={() => void controlRun('resume-monitoring')}
              size="sm"
              variant="outline"
            >
              {runBusy === 'resume-monitoring' && <LoaderCircle className="animate-spin" />}
              恢复监控
            </Button>
          )}
        </div>
      </CardFooter>
    </Card>
  );
}

function RunPanel({ events, run }: { events: RunEvent[]; run: WorkflowRun }) {
  const active = ACTIVE_RUN_STATUSES.has(run.status);
  const recentEvents = events.filter((event) => event.message).slice(-8);
  return (
    <section className="min-w-0 wrap-anywhere rounded-xl border border-blue-100 bg-blue-50/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {active ? (
            <LoaderCircle className="size-4 animate-spin text-blue-600" />
          ) : run.status === 'succeeded' ? (
            <CheckCircle2 className="size-4 text-emerald-600" />
          ) : (
            <CircleAlert className="size-4 text-amber-600" />
          )}
          <h3 className="text-sm font-semibold text-slate-900">{RUN_STATUS_COPY[run.status]}</h3>
          <Badge variant="outline" className="rounded-md bg-white font-mono text-[10px]">
            {run.run_id.slice(0, 12)}
          </Badge>
          {run.execution?.backend === 'slurm' && (
            <Badge variant="outline" className="rounded-md bg-white text-xs">
              Slurm · {run.execution.partition}
            </Badge>
          )}
        </div>
        <span className="text-xs tabular-nums text-slate-500">{Math.round(run.progress)}%</span>
      </div>
      {run.execution?.sample_mode === 'per_sample' && (
        <p className="mt-2 wrap-anywhere text-xs text-slate-600">
          并行样本上限：{run.execution.nodes?.map(node => `${node.node}：${node.parallel_samples ?? 1}`).join(' · ')}
        </p>
      )}
      <Progress className="mt-3" value={run.progress}>
        <ProgressLabel className="text-xs text-slate-600">流程进度</ProgressLabel>
        <ProgressValue className="text-xs" />
      </Progress>

      <div className="mt-3 grid gap-2">
        {run.steps.map((step) => (
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5" key={step.step_id}>
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="min-w-0 font-medium text-slate-800">{step.title}</span>
              <span className="shrink-0 text-slate-500">{Math.round(step.progress)}%</span>
            </div>
            {(step.sample_id || step.node_name) && <p className="mt-1 text-xs text-blue-700">
              {step.sample_label || step.sample_id} {step.node_name && ` · 节点 ${step.node_name}`}
            </p>}
            <p className="mt-1 text-[11px] text-slate-500">{step.message}</p>
            {step.scheduler?.job_id && (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-blue-700">
                <span className="font-mono">Job {step.scheduler.job_id}</span>
                {step.scheduler.state && (
                  <span title={step.scheduler.state}>
                    {SCHEDULER_STATUS_COPY[step.scheduler.state.toUpperCase()] ?? step.scheduler.state}
                  </span>
                )}
                {step.scheduler.node_list && <span>节点：{step.scheduler.node_list}</span>}
                {step.scheduler.reason && <span>原因：{step.scheduler.reason}</span>}
              </div>
            )}
            {step.error_message && (
              <p className="mt-1 text-[11px] text-red-700">{step.error_message}</p>
            )}
          </div>
        ))}
      </div>

      {recentEvents.length > 0 && (
        <Collapsible className="mt-3 rounded-lg border border-slate-800 bg-slate-950 text-slate-200">
          <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left">
            <span className="flex items-center gap-2 text-xs font-medium">
              <Terminal className="size-3.5" />
              运行日志
            </span>
            <ChevronDown className="size-4 text-slate-400" />
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-1 border-t border-slate-800 px-3 py-2.5 font-mono text-[10px] leading-4 text-slate-300">
            {recentEvents.map((event) => (
              <p className={event.level === 'error' ? 'text-red-300' : ''} key={event.event_id}>
                [{event.event_id}] {event.message}
              </p>
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}

      {run.artifacts.length > 0 && (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
          <p className="flex items-center gap-2 text-xs font-semibold text-emerald-800">
            <FileText className="size-3.5" />
            输出文件
          </p>
          {run.artifacts.map((artifact) => (
            <div className="mt-2" key={artifact.artifact_id}>
              <p className="text-xs font-medium text-slate-800">{artifact.label}</p>
              <p className="break-all font-mono text-[10px] leading-4 text-slate-500">
                {artifact.absolute_path}
              </p>
              {artifact.sha256 && (
                <p className="truncate font-mono text-[9px] text-slate-400">
                  SHA-256 {artifact.sha256}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {run.error_message && (
        <Alert variant="destructive" className="mt-3">
          <TriangleAlert />
          <AlertDescription>{run.error_message}</AlertDescription>
        </Alert>
      )}
      <p className="mt-3 break-all font-mono text-[9px] text-slate-400">
        输出目录：{run.output_directory}
      </p>
    </section>
  );
}

function MethodChoice({ method, stepId }: { method: MethodOption; stepId: string }) {
  const controlId = `${stepId}-${method.id}`;
  return (
    <Label
      className={cn(
        'group items-start rounded-lg border p-3 transition-colors',
        method.compatible
          ? 'border-slate-200 bg-white has-[[data-checked]]:border-blue-300 has-[[data-checked]]:bg-blue-50/60'
          : 'cursor-not-allowed border-slate-200 bg-slate-100 opacity-65',
      )}
      htmlFor={controlId}
    >
      <RadioGroupItem
        className="mt-0.5"
        disabled={!method.compatible}
        id={controlId}
        value={method.id}
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-slate-900">{method.label}</span>
          {method.recommended && method.compatible && (
            <Badge className="h-5 rounded-md bg-blue-100 px-1.5 text-[10px] text-blue-700 shadow-none">
              <Sparkles className="mr-1 size-3" />
              模型推荐
            </Badge>
          )}
          {!method.compatible && (
            <Badge className="h-5 rounded-md bg-amber-100 px-1.5 text-[10px] text-amber-800 shadow-none">
              暂不可执行
            </Badge>
          )}
          {method.execution_mode === 'planning' && (
            <Badge className="h-5 rounded-md bg-amber-50 px-1.5 text-[10px] text-amber-700 shadow-none">
              规划型
            </Badge>
          )}
          {method.execution_recipe && (
            <Badge className="h-5 rounded-md bg-emerald-50 px-1.5 text-[10px] text-emerald-700 shadow-none">
              Runner 流程 · {method.execution_recipe.steps.length} 步
            </Badge>
          )}
        </span>
        <span className="mt-1 block text-xs font-normal leading-5 text-slate-500">
          {method.description}
        </span>
        <span className="mt-1 block text-[10px] font-normal text-slate-400">
          {method.structure_level === 'reviewed'
            ? '人工审核结构'
            : method.structure_level === 'evidence'
              ? `来源可追溯${method.command_references?.length ? ` · ${method.command_references.length} 条参考命令` : ''}`
              : '类别级规划参数'}
        </span>
        {method.recommended && method.recommendation_reason && method.compatible && (
          <span className="mt-1 block text-[11px] font-normal leading-5 text-blue-700">
            {method.recommendation_reason}
          </span>
        )}
        {!method.compatible && method.blocked_reasons.length > 0 && (
          <span className="mt-1 block text-[11px] font-normal leading-5 text-amber-700">
            {method.blocked_reasons.join('；')}
          </span>
        )}
        <MethodGuidance method={method} />
      </span>
    </Label>
  );
}

function MethodGuidance({ method, includeInputs = true }: { method: MethodOption; includeInputs?: boolean }) {
  const warnings = [...(includeInputs ? method.input_warnings ?? [] : []), ...(method.scope_warnings ?? [])];
  if (!warnings.length) return null;
  return <span className="mt-2 block space-y-1 wrap-anywhere text-[11px] font-normal leading-5 text-amber-700">
    {warnings.map((warning) => <span className="block" key={warning}>{warning}</span>)}
  </span>;
}

function MethodEvidence({ method }: { method: MethodOption }) {
  const commands = method.command_references ?? [];
  const sources = method.source_references ?? [];
  if (commands.length === 0 && sources.length === 0 && !method.structure_level) return null;

  return (
    <Collapsible className="mt-3 rounded-lg border border-slate-200 bg-white">
      <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left">
        <span className="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <Link2 className="size-3.5 text-blue-600" />
          方法依据与参考命令
          <Badge variant="outline" className="h-5 rounded-md text-[10px] font-normal">
            {method.structure_level === 'reviewed'
              ? '人工审核'
              : method.structure_level === 'evidence'
                ? '来自 Skill'
                : '类别参数'}
          </Badge>
        </span>
        <ChevronDown className="size-4 text-slate-400" />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 border-t border-slate-100 px-3 py-3">
        {commands.length > 0 && (
          <div>
            <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-400">
              Skill 中的参考命令 · 不会直接执行
            </p>
            <div className="mt-2 space-y-2">
              {commands.map((reference, index) => (
                <div className="rounded-md bg-slate-950 px-2.5 py-2" key={`${reference.source_path}:${reference.line_start}:${index}`}>
                  <code className="block overflow-x-auto whitespace-pre-wrap break-words text-[10px] leading-4 text-slate-200">
                    {reference.command}
                  </code>
                  <p className="mt-1 text-[9px] text-slate-500">
                    {reference.source_path}
                    {reference.line_start ? `:${reference.line_start}` : ''} · {reference.kind}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
        {sources.length > 0 && (
          <div>
            <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-400">
              来源文件
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {sources.map((source, index) => (
                <Badge className="max-w-full rounded-md bg-slate-50 text-[9px] font-normal text-slate-600" key={`${source.path}:${source.line_start}:${index}`}>
                  <span className="truncate">
                    {source.path}{source.line_start ? `:${source.line_start}` : ''}
                  </span>
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

function MethodArtifacts({
  apiBase,
  busyAction,
  disabled,
  method,
  onBind,
  onCompleteDependencies,
  selectedParameters,
  step,
  workflow,
}: {
  apiBase: string;
  busyAction: string | null;
  disabled: boolean;
  method: MethodOption;
  onBind: (slotId: string, rootId: string, relativePath: string) => void;
  onCompleteDependencies: () => void;
  selectedParameters: Record<string, ParameterValue>;
  step: WorkflowStep;
  workflow: Workflow;
}) {
  const values = Object.fromEntries(
    method.parameters
      .map((spec) => [spec.id, selectedParameters[spec.id] ?? spec.default])
      .filter((entry): entry is [string, ParameterValue] => entry[1] !== null),
  );
  const inputSlots = method.input_slots ?? [];
  const outputSlots = (method.output_slots ?? []).filter(
    (slot) =>
      Object.keys(slot.generated_when).length === 0 || conditionMatches(slot.generated_when, values),
  );
  const bindings = step.input_bindings ?? {};
  const missing = new Set(step.missing_required_inputs ?? []);
  const canCompleteUpstream = inputSlots.some(
    (slot) =>
      missing.has(slot.id) && !step.manual_input_types?.includes(slot.type) &&
      ['raw_dwi', 'bids_dwi', 'preprocessed_dwi'].includes(slot.type),
  );

  return (
    <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <section className="rounded-lg border border-slate-200 bg-white p-3.5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FileInput className="size-4 text-blue-600" />
            <div>
              <p className="text-xs font-semibold text-slate-800">方法输入</p>
              <p className="mt-0.5 text-[10px] text-slate-400">
                流程锁定后，可从当前数据集选择并批量匹配
              </p>
            </div>
          </div>
          {missing.size > 0 ? (
            <Badge className="bg-amber-50 text-amber-700 shadow-none">
              <CircleAlert className="mr-1 size-3" />
              缺少 {missing.size} 项
            </Badge>
          ) : (
            <Badge className="bg-emerald-50 text-emerald-700 shadow-none">
              <Check className="mr-1 size-3" />
              输入已就绪
            </Badge>
          )}
        </div>
        <div className="space-y-2">
          {inputSlots.map((slot) => {
            const required = inputRequired(slot, values) || missing.has(slot.id);
            const binding = bindings[slot.id];
            const inputBusy = busyAction === `input:${step.id}:${slot.id}`;
            return (
              <div
                className={cn(
                  'rounded-lg border p-3',
                  missing.has(slot.id)
                    ? 'border-amber-200 bg-amber-50/60'
                    : binding
                      ? 'border-emerald-100 bg-emerald-50/40'
                      : 'border-slate-200 bg-slate-50',
                )}
                key={slot.id}
              >
                <div className="flex flex-col items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <p className="text-xs font-medium text-slate-800">{slot.label}</p>
                      <Badge variant="outline" className="h-5 px-1.5 font-mono text-[9px]">
                        {slot.type}
                      </Badge>
                      <Badge
                        className={cn(
                          'h-5 px-1.5 text-[9px] shadow-none',
                          required
                            ? 'bg-blue-50 text-blue-700'
                            : 'bg-slate-100 text-slate-500',
                        )}
                      >
                        {required ? '必需' : '可选'}
                      </Badge>
                    </div>
                    <p className="mt-1 text-[11px] leading-4 text-slate-500">{slot.description}</p>
                    {binding && (
                      <div className="mt-2 flex items-start gap-1.5 text-[10px] leading-4 text-emerald-700">
                        <Link2 className="mt-0.5 size-3 shrink-0" />
                        <span className="min-w-0 break-all">
                          {binding.source === 'upstream_output'
                            ? `来自上游 ${binding.upstream_step_id}.${binding.output_slot_id}`
                            : binding.binding_mode === 'per_sample'
                              ? `${binding.coverage?.matched ?? 0} 个样本 · ${binding.path_template}`
                              : binding.relative_path || binding.label}
                        </span>
                      </div>
                    )}
                    {!binding && required && (
                      <p className="mt-2 text-[10px] text-amber-700">尚未找到满足条件的输入。</p>
                    )}
                    {!binding && step.manual_input_types?.includes(slot.type) && (
                      <p className="mt-2 text-sm leading-5 text-amber-800">
                        已移除生成此输入的步骤。
                        {slot.source_options.includes('existing_path')
                          ? workflow.locked_at ? '请选择已有文件。' : '锁定流程后，请在此选择已有文件。'
                          : '当前方法不支持选择已有文件，请解锁并选择支持此输入的方法。'}
                      </p>
                    )}
                  </div>
                  {slot.source_options.includes('existing_path') && (
                    inputBusy ? (
                      <LoaderCircle className="size-4 animate-spin text-blue-600" />
                    ) : (
                      <ArtifactPathPicker
                        apiBase={apiBase}
                        dataset={workflow.dataset}
                        disabled={disabled}
                        onSelected={(rootId, relativePath) =>
                          onBind(slot.id, rootId, relativePath)
                        }
                        stepId={step.id}
                        slot={slot}
                        workflowId={workflow.workflow_id}
                      />
                    )
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {canCompleteUpstream && workflow.dependency_policy !== 'complete' && (
          <Alert className="mt-3 border-blue-200 bg-blue-50 text-blue-900">
            <GitBranch />
            <AlertDescription>
              <p className="text-xs font-medium">可以补充最小上游流程</p>
              <p className="mt-1 text-[11px] text-blue-700">
                系统只添加生成缺失 DWI 输入所必需的步骤，添加前不会执行软件。
              </p>
              <Button
                className="mt-2 gap-1.5"
                disabled={disabled || busyAction === 'complete-dependencies'}
                onClick={onCompleteDependencies}
                size="sm"
                variant="outline"
              >
                {busyAction === 'complete-dependencies' ? (
                  <LoaderCircle className="animate-spin" />
                ) : (
                  <GitBranch />
                )}
                补充最小上游
              </Button>
            </AlertDescription>
          </Alert>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-3.5">
        <div className="mb-3 flex items-center gap-2">
          <FileOutput className="size-4 text-violet-600" />
          <div>
            <p className="text-xs font-semibold text-slate-800">计划输出</p>
            <p className="mt-0.5 text-[10px] text-slate-400">按当前参数预计生成</p>
          </div>
        </div>
        <div className="space-y-2">
          {outputSlots.map((slot) => (
            <div className="rounded-lg border border-violet-100 bg-violet-50/40 p-3" key={slot.id}>
              <div className="flex flex-wrap items-center gap-1.5">
                <p className="text-xs font-medium text-slate-800">{slot.label}</p>
                {slot.primary && (
                  <Badge className="h-5 bg-violet-100 px-1.5 text-[9px] text-violet-700 shadow-none">
                    主要输出
                  </Badge>
                )}
              </div>
              <p className="mt-1 text-[11px] leading-4 text-slate-500">{slot.description}</p>
              {slot.path_template && (
                <p className="mt-2 break-all font-mono text-[9px] leading-4 text-violet-600">
                  {slot.path_template}
                </p>
              )}
            </div>
          ))}
          {outputSlots.length === 0 && (
            <p className="rounded-lg border border-dashed border-slate-200 px-3 py-6 text-center text-xs text-slate-400">
              该方法尚未声明结构化输出
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function StepParameters({
  busyAction,
  disabled,
  method,
  onChange,
  parametersReviewed,
  selectedParameters,
  stepId,
}: {
  busyAction: string | null;
  disabled: boolean;
  method: MethodOption;
  onChange: (parameterId: string, value: ParameterValue) => void;
  parametersReviewed: boolean;
  selectedParameters: Record<string, ParameterValue>;
  stepId: string;
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const values = Object.fromEntries(
    method.parameters
      .map((spec) => [spec.id, selectedParameters[spec.id] ?? spec.default])
      .filter((entry): entry is [string, ParameterValue] => entry[1] !== null),
  );
  const visible = method.parameters.filter((spec) => isParameterVisible(spec, values));
  const basic = visible.filter((spec) => spec.level !== 'advanced');
  const advanced = visible.filter((spec) => spec.level === 'advanced');
  const advancedGroups = Object.entries(
    advanced.reduce<Record<string, ParameterSpec[]>>((groups, spec) => {
      const group = spec.group || '高级参数';
      groups[group] = [...(groups[group] ?? []), spec];
      return groups;
    }, {}),
  );

  const renderControl = (spec: ParameterSpec) => (
    <ParameterControl
      busy={busyAction === `parameter:${stepId}:${spec.id}`}
      controlId={`parameter-${stepId}-${spec.id}`}
      disabled={disabled}
      key={spec.id}
      onChange={(value) => onChange(spec.id, value)}
      spec={spec}
      value={selectedParameters[spec.id] ?? spec.default}
    />
  );

  return (
    <div className="mt-4 rounded-lg border border-slate-200 bg-white p-3.5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Settings2 className="size-4 text-blue-600" />
          <div>
            <p className="text-xs font-semibold text-slate-800">
              {method.execution_mode === 'planning' ? '步骤参数' : '命令参数'}
            </p>
            <p className="mt-0.5 text-[10px] text-slate-400">
              默认展示 {basic.length} 个常用参数
              {advanced.length > 0 ? ` · ${advanced.length} 个高级参数` : ''}
            </p>
          </div>
        </div>
        {parametersReviewed && (
          <Badge className="bg-emerald-50 text-emerald-700 shadow-none">
            <ShieldCheck className="mr-1 size-3" />
            已审核
          </Badge>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">{basic.map(renderControl)}</div>

      {advanced.length > 0 && (
        <Collapsible className="mt-3" onOpenChange={setAdvancedOpen} open={advancedOpen}>
          <CollapsibleTrigger
            className="flex w-full items-center justify-between rounded-lg border border-blue-100 bg-blue-50/60 px-3 py-2 text-left text-xs font-medium text-blue-700 transition-colors hover:bg-blue-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
          >
            <span className="flex items-center gap-2">
              <SlidersHorizontal className="size-3.5" />
              高级参数
              <Badge className="h-5 bg-white px-1.5 text-[10px] text-blue-600 shadow-none">
                {advanced.length}
              </Badge>
            </span>
            <ChevronDown
              className={cn('size-4 transition-transform', advancedOpen && 'rotate-180')}
            />
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-3">
            <div className="space-y-4 rounded-lg border border-slate-100 bg-slate-50/40 p-3">
              {advancedGroups.map(([group, specs]) => (
                <section key={group}>
                  <div className="mb-2 flex items-center gap-2">
                    <span className="h-px flex-1 bg-slate-200" />
                    <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                      {group}
                    </p>
                    <span className="h-px flex-1 bg-slate-200" />
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">{specs.map(renderControl)}</div>
                </section>
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}

function ParameterControl({
  busy,
  controlId,
  disabled,
  onChange,
  spec,
  value,
}: {
  busy: boolean;
  controlId: string;
  disabled: boolean;
  onChange: (value: ParameterValue) => void;
  spec: ParameterSpec;
  value: ParameterValue | null;
}) {
  if (spec.type === 'boolean') {
    return (
      <div className="flex min-w-0 min-h-20 items-start justify-between gap-3 rounded-lg bg-slate-50 p-3">
        <div className="min-w-0 flex-1">
          <Label htmlFor={controlId}>
            {spec.label}
            {!spec.required && <span className="ml-1 font-normal text-slate-400">（可选）</span>}
          </Label>
          <p className="mt-1 text-[11px] leading-4 text-slate-500">{spec.description}</p>
        </div>
        {busy ? (
          <LoaderCircle className="mt-0.5 size-4 animate-spin text-blue-600" />
        ) : (
          <Switch
            checked={Boolean(value)}
            disabled={disabled}
            id={controlId}
            onCheckedChange={(checked) => onChange(checked)}
          />
        )}
      </div>
    );
  }

  const useSelect =
    spec.control === 'select' ||
    ((!spec.control || spec.control === 'auto') && spec.options.length > 0);
  const selectedOption = spec.options.find(
    (option) => optionKey(option.value) === optionKey(value),
  );

  return (
    <div className="min-w-0 min-h-20 rounded-lg bg-slate-50 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <Label htmlFor={controlId}>
          {spec.label}
          {!spec.required && <span className="ml-1 font-normal text-slate-400">（可选）</span>}
          {spec.unit && <span className="ml-1 font-normal text-slate-400">({spec.unit})</span>}
        </Label>
        {busy && <LoaderCircle className="size-3.5 animate-spin text-blue-600" />}
      </div>
      {useSelect ? (
        <NativeSelect
          className="w-full"
          disabled={busy || disabled}
          id={controlId}
          onChange={(event) => onChange(decodeOption(spec, event.target.value))}
          value={value === null ? '' : optionKey(value)}
        >
          {spec.options.map((option: ParameterOption) => (
            <NativeSelectOption key={optionKey(option.value)} value={optionKey(option.value)}>
              {option.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      ) : (
        <DirectParameterInput
          busy={busy}
          controlId={controlId}
          disabled={disabled}
          key={`${spec.id}:${String(value)}`}
          onChange={onChange}
          spec={spec}
          value={value}
        />
      )}
      <p className="mt-1.5 text-[11px] leading-4 text-slate-500">{spec.description}</p>
      {selectedOption?.description && (
        <p className="mt-1 text-[10px] leading-4 text-blue-700">
          {selectedOption.description}
        </p>
      )}
    </div>
  );
}

function DirectParameterInput({
  busy,
  controlId,
  disabled,
  onChange,
  spec,
  value,
}: {
  busy: boolean;
  controlId: string;
  disabled: boolean;
  onChange: (value: ParameterValue) => void;
  spec: ParameterSpec;
  value: ParameterValue | null;
}) {
  const [draft, setDraft] = useState(value === null ? '' : String(value));

  const commit = () => {
    if (spec.type === 'string') {
      if (draft !== value) onChange(draft);
      return;
    }
    const parsed = spec.type === 'integer' ? Number.parseInt(draft, 10) : Number(draft);
    if (!draft.trim() && !spec.required) {
      if (value !== null) onChange(null);
      return;
    }
    if (!Number.isFinite(parsed)) {
      setDraft(value === null ? '' : String(value));
      return;
    }
    if (parsed !== value) onChange(parsed);
  };

  return (
    <Input
      aria-describedby={`${controlId}-description`}
      disabled={busy || disabled}
      id={controlId}
      max={spec.maximum ?? undefined}
      min={spec.minimum ?? undefined}
      onBlur={commit}
      onChange={(event) => setDraft(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') event.currentTarget.blur();
      }}
      placeholder={spec.placeholder}
      step={spec.step ?? undefined}
      type={spec.type === 'string' ? 'text' : 'number'}
      value={draft}
    />
  );
}
