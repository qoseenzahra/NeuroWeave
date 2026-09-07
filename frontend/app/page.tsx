'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  ArchiveRestore,
  Bot,
  Braces,
  Check,
  ChevronRight,
  Database,
  FileScan,
  History,
  LoaderCircle,
  ListChecks,
  ListTree,
  Menu,
  MessageCircle,
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  RefreshCw,
  Search,
  SendHorizontal,
  Sparkles,
  Trash2,
  WandSparkles,
  X,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { DatasetPicker } from '@/components/dataset/dataset-picker';
import { CapabilityRecommendationCard } from '@/components/workflow/capability-recommendation-card';
import { WorkflowCard } from '@/components/workflow/workflow-card';
import type {
  CapabilityRecommendation,
  CapabilityRoutingTrace,
} from '@/lib/capability';
import type { Dataset } from '@/lib/dataset';
import { cn } from '@/lib/utils';
import { useConversationHistory, type ConversationListItem } from '@/lib/use-conversation-history';
import type { Workflow } from '@/lib/workflow';

type Skill = {
  name: string;
  display_name: string;
  description: string;
  layer: string;
  skill_type: string;
  runtime: string;
  status: string;
  summary_en?: string;
  summary_zh?: string;
  dependencies?: string[];
  source?: 'NeuroClaw' | 'LocalFlow';
  script_count?: number;
  has_handler?: boolean;
  executable?: boolean;
  structure_mode?: 'advisory' | 'planning' | 'runner';
  runner_count?: number;
  ready_runner_count?: number;
  planning_method_count?: number;
  execution_state?: 'ready' | 'needs_environment' | 'planning';
  runtime_reasons?: string[];
};

type CatalogStats = {
  total: number;
  sources: Record<string, number>;
  with_scripts: number;
  with_handlers: number;
  structured?: number;
  planning_structured?: number;
  runner_structured?: number;
  capability_catalog?: {
    capabilities: number;
    methods: number;
    planning_methods: number;
    runner_methods: number;
    evidence_backed_methods: number;
    reference_commands: number;
    artifact_types: number;
  };
  execution_enabled: boolean;
};

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  skills?: string[];
  interactionMode?: InteractionMode;
  workflowRecommended?: boolean;
  clarificationRequired?: boolean;
  capabilityRouting?: CapabilityRoutingTrace;
  capabilityRecommendation?: CapabilityRecommendation;
  workflow?: Workflow;
};

type StoredConversationMessage = {
  message_id: number;
  sequence: number;
  role: 'user' | 'assistant';
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

type ConversationSnapshot = {
  conversation: {
    conversation_id: string;
    title: string;
    archived: boolean;
    created_at: string;
    updated_at: string;
  };
  messages: StoredConversationMessage[];
};

type InteractionMode = 'chat' | 'task';

type Health = {
  status: string;
  mode: 'demo' | 'model';
  model: string;
  prompt_version?: string;
  skill_catalog?: CatalogStats;
  execution?: {
    enabled: boolean;
    runner_count: number;
    ready_runner_count?: number;
  };
};

const API_BASE =
  process.env.NEXT_PUBLIC_LOCALFLOW_API_URL ??
  (process.env.NODE_ENV === 'production' ? '' : 'http://127.0.0.1:8010');

const FALLBACK_SKILLS: Skill[] = [
  {
    name: 'dataset-inspector',
    display_name: '数据集巡检',
    description: '扫描数据集结构，识别文件类型、规模、字段和常见质量问题。',
    layer: 'workflow',
    skill_type: 'data-understanding',
    runtime: 'Python',
    status: 'ready',
  },
  {
    name: 'table-cleaning',
    display_name: '表格清洗',
    description: '为 CSV、TSV 或 Excel 数据设计缺失值、类型和异常值处理流程。',
    layer: 'workflow',
    skill_type: 'data-cleaning',
    runtime: 'Python / pandas',
    status: 'ready',
  },
  {
    name: 'image-batch-processing',
    display_name: '影像批处理',
    description: '规划科研影像的批量转换、预处理、质量控制与结果目录。',
    layer: 'workflow',
    skill_type: 'image-processing',
    runtime: 'External tools / Python',
    status: 'draft',
  },
  {
    name: 'report-builder',
    display_name: '结果报告',
    description: '将处理日志、统计摘要、图表和异常项组织成可审阅报告。',
    layer: 'output',
    skill_type: 'reporting',
    runtime: 'Python',
    status: 'ready',
  },
];

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    '你好，我是 NeuroWeave。NeuroClaw 的现有 Skill 能力库已接入，你可以从左侧搜索并选择一个或多个 Skill，再告诉我希望如何处理数据。\n\n本次会话的原始消息由本地后端保存；对话较长时，较早内容会整理成工作摘要，同时保留近期原始消息。',
};

function iconForSkill(skill: Skill) {
  if (skill.skill_type.includes('image')) return FileScan;
  if (skill.skill_type.includes('report')) return Braces;
  return Database;
}

function newMessageId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function conversationTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return new Intl.DateTimeFormat('zh-CN',
    sameDay
      ? { hour: '2-digit', minute: '2-digit' }
      : { month: 'numeric', day: 'numeric' },
  ).format(date);
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

export default function Home() {
  const [skills, setSkills] = useState<Skill[]>(FALLBACK_SKILLS);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState('');
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'NeuroClaw' | 'LocalFlow'>('all');
  const [catalogStats, setCatalogStats] = useState<CatalogStats | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [chosenDataset, setSelectedDataset] = useState<Dataset | null>(null);
  const currentWorkflow = [...messages].reverse().find((message) => message.workflow)?.workflow;
  // A workflow's persisted snapshot owns its inputs, including after reopening history.
  const selectedDataset = currentWorkflow ? currentWorkflow.dataset ?? null : chosenDataset;
  const [isDatasetUpdating, setIsDatasetUpdating] = useState(false);
  const [busyWorkflows, setBusyWorkflows] = useState<string[]>([]);
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('chat');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState('新数据处理对话');
  const [conversationSearch, setConversationSearch] = useState('');
  const [historyScope, setHistoryScope] = useState<'active' | 'archived'>('active');
  const [editingConversation, setEditingConversation] = useState<ConversationListItem | null>(null);
  const [renameTitle, setRenameTitle] = useState('');
  const [archiveTarget, setArchiveTarget] = useState<ConversationListItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ConversationListItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isConversationUpdating, setIsConversationUpdating] = useState(false);
  const [sidebarView, setSidebarView] = useState<'conversations' | 'skills'>('skills');
  const [isConversationOpening, setIsConversationOpening] = useState(false);
  const {
    conversations, isHistoryLoading, hasMoreConversations, historyError,
    setHistoryError, loadConversations, loadMoreConversations, retryConversations,
  } = useConversationHistory(API_BASE, conversationSearch, historyScope === 'archived', sidebarView === 'conversations');
  const [isSending, setIsSending] = useState(false);
  const [isSkillsOpen, setIsSkillsOpen] = useState(false);
  const messageEndRef = useRef<HTMLDivElement>(null);
  const historyEndRef = useRef<HTMLDivElement>(null);
  const datasetLocked = Boolean(currentWorkflow?.locked_at || currentWorkflow?.status === 'confirmed');
  const datasetDisabled = datasetLocked || isSending || isConversationOpening || busyWorkflows.length > 0;
  const datasetContext = useRef({ workflow: currentWorkflow, blocked: datasetDisabled, conversationId });
  datasetContext.current = { workflow: currentWorkflow, blocked: datasetDisabled, conversationId };
  const datasetNotice = datasetLocked
    ? currentWorkflow?.status === 'confirmed'
      ? '流程已确认，数据集已固定；更换数据集请新建对话。'
      : '数据集已随流程锁定；请先点击「解锁流程」再更换。'
    : currentWorkflow ? '更换数据集将清除当前流程的文件输入绑定，并重新检查方法兼容性。' : null;

  const visibleSkills = useMemo(() => {
    const query = search.trim().toLowerCase();
    return skills.filter((skill) => {
      const matchesSource = sourceFilter === 'all' || skill.source === sourceFilter;
      const matchesQuery =
        !query ||
        [
          skill.name,
          skill.display_name,
          skill.description,
          skill.summary_en,
          skill.summary_zh,
          skill.skill_type,
        ]
          .join(' ')
          .toLowerCase()
          .includes(query);
      return matchesSource && matchesQuery;
    });
  }, [search, skills, sourceFilter]);

  const selectedDetails = useMemo(
    () => skills.filter((skill) => selectedSkills.includes(skill.name)),
    [selectedSkills, skills],
  );

  const patchConversation = useCallback(
    async (
      item: ConversationListItem,
      update: { title?: string; archived?: boolean },
    ) => {
      const response = await fetch(`${API_BASE}/api/conversations/${item.conversation_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
      });
      const payload = (await response.json()) as {
        conversation_id?: string;
        title?: string;
        archived?: boolean;
        detail?: string;
      };
      if (!response.ok || !payload.conversation_id) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : '无法更新这条对话');
      }
      return payload;
    },
    [],
  );

  const hydrateMessages = useCallback(async (records: StoredConversationMessage[]) => {
    const workflowIds = Array.from(
      new Set(
        records
          .map((record) => record.metadata.workflow_id)
          .filter((value): value is string => typeof value === 'string' && value.length > 0),
      ),
    );
    const workflows = await Promise.all(
      workflowIds.map(async (workflowId) => {
        try {
          const response = await fetch(`${API_BASE}/api/workflows/${workflowId}`);
          return response.ok ? ([workflowId, (await response.json()) as Workflow] as const) : null;
        } catch {
          return null;
        }
      }),
    );
    const workflowById = new Map(
      workflows.filter((entry): entry is readonly [string, Workflow] => entry !== null),
    );

    return records.map((record): ChatMessage => {
      const metadata = record.metadata ?? {};
      const mode = metadata.interaction_mode;
      const workflowId = metadata.workflow_id;
      return {
        id: `stored-${record.message_id}`,
        role: record.role,
        content: record.content,
        skills: record.role === 'user' ? stringArray(metadata.selected_skills) : undefined,
        interactionMode: mode === 'task' || mode === 'chat' ? mode : undefined,
        workflowRecommended:
          typeof metadata.workflow_recommended === 'boolean'
            ? metadata.workflow_recommended
            : undefined,
        clarificationRequired:
          typeof metadata.clarification_required === 'boolean'
            ? metadata.clarification_required
            : undefined,
        capabilityRouting:
          metadata.capability_routing && typeof metadata.capability_routing === 'object'
            ? (metadata.capability_routing as CapabilityRoutingTrace)
            : undefined,
        capabilityRecommendation:
          metadata.capability_recommendation &&
          typeof metadata.capability_recommendation === 'object'
            ? (metadata.capability_recommendation as CapabilityRecommendation)
            : undefined,
        workflow: typeof workflowId === 'string' ? workflowById.get(workflowId) : undefined,
      };
    });
  }, []);

  const openConversation = useCallback(
    async (item: ConversationListItem) => {
      if (isSending || isConversationOpening || isDatasetUpdating || busyWorkflows.length > 0) return;
      setIsConversationOpening(true);
      setHistoryError(null);
      try {
        const response = await fetch(`${API_BASE}/api/conversations/${item.conversation_id}`);
        if (!response.ok) throw new Error('无法读取这条对话');
        const snapshot = (await response.json()) as ConversationSnapshot;
        const restoredMessages = await hydrateMessages(snapshot.messages);
        setMessages(restoredMessages.length > 0 ? restoredMessages : [WELCOME_MESSAGE]);
        setConversationId(snapshot.conversation.conversation_id);
        setConversationTitle(snapshot.conversation.title);

        const reversedMessages = [...snapshot.messages].reverse();
        const modeMetadata = reversedMessages.find(
          (message) => 'interaction_mode' in message.metadata,
        )?.metadata;
        const skillMetadata = reversedMessages.find(
          (message) => message.role === 'user' && 'selected_skills' in message.metadata,
        )?.metadata;
        const datasetMetadata = reversedMessages.find(
          (message) => 'dataset_id' in message.metadata,
        )?.metadata;
        const savedMode = modeMetadata?.interaction_mode;
        if (savedMode === 'chat' || savedMode === 'task') setInteractionMode(savedMode);
        if (Array.isArray(skillMetadata?.selected_skills)) {
          setSelectedSkills(stringArray(skillMetadata.selected_skills));
        }
        const restoredWorkflow = [...restoredMessages].reverse().find((message) => message.workflow)?.workflow;
        if (restoredWorkflow) {
          setSelectedDataset(restoredWorkflow.dataset ?? null);
        } else if (typeof datasetMetadata?.dataset_id === 'string' && datasetMetadata.dataset_id) {
          const datasetResponse = await fetch(
            `${API_BASE}/api/datasets/${datasetMetadata.dataset_id}`,
          );
          setSelectedDataset(
            datasetResponse.ok ? ((await datasetResponse.json()) as Dataset) : null,
          );
        } else {
          setSelectedDataset(null);
        }
        setIsSkillsOpen(false);
      } catch (error) {
        setHistoryError(error instanceof Error ? error.message : '无法读取这条对话');
      } finally {
        setIsConversationOpening(false);
      }
    },
    [hydrateMessages, isConversationOpening, isSending, isDatasetUpdating, busyWorkflows, setHistoryError],
  );

  useEffect(() => {
    const loadWorkspace = async () => {
      try {
        const [healthResponse, skillsResponse] = await Promise.all([
          fetch(`${API_BASE}/api/health?include_runtime=false`),
          fetch(`${API_BASE}/api/skills`),
        ]);
        if (!healthResponse.ok || !skillsResponse.ok) {
          throw new Error('NeuroWeave API is unavailable');
        }
        const healthData = (await healthResponse.json()) as Health;
        const skillsData = (await skillsResponse.json()) as {
          skills: Skill[];
          stats?: CatalogStats;
        };
        setHealth(healthData);
        setCatalogStats(skillsData.stats ?? healthData.skill_catalog ?? null);
        if (skillsData.skills.length > 0) setSkills(skillsData.skills);
      } catch {
        setHealth(null);
      }
    };
    void loadWorkspace();
  }, []);

  useEffect(() => {
    if (sidebarView !== 'conversations' || isHistoryLoading || historyError || !hasMoreConversations) return;
    const sentinel = historyEndRef.current;
    if (!sentinel || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadMoreConversations();
    }, {
      root: sentinel.closest('[data-slot="scroll-area-viewport"]'),
      rootMargin: '0px 0px 80px 0px',
    });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [sidebarView, isHistoryLoading, historyError, hasMoreConversations, loadMoreConversations, conversations.length]);

  const latestMessageId = messages.at(-1)?.id;
  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    // Editing a workflow updates its message object, but is not a new chat turn.
  }, [latestMessageId, isSending]);

  const toggleSkill = (name: string) => {
    setSelectedSkills((current) =>
      current.includes(name)
        ? current.filter((skill) => skill !== name)
        : [...current, name],
    );
  };

  const resetConversation = () => {
    if (isSending || isConversationOpening || isDatasetUpdating || busyWorkflows.length > 0) return;
    setMessages([WELCOME_MESSAGE]);
    setInput('');
    setConversationId(null);
    setConversationTitle('新数据处理对话');
    setHistoryError(null);
  };

  const beginRename = (conversation: ConversationListItem) => {
    setEditingConversation(conversation);
    setRenameTitle(conversation.title);
    setHistoryError(null);
  };

  const submitRename = async () => {
    const title = renameTitle.replace(/\s+/g, ' ').trim();
    if (!editingConversation || !title || isConversationUpdating) return;
    setIsConversationUpdating(true);
    setHistoryError(null);
    try {
      await patchConversation(editingConversation, { title });
      if (editingConversation.conversation_id === conversationId) {
        setConversationTitle(title);
      }
      setEditingConversation(null);
      setRenameTitle('');
      await loadConversations();
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : '无法重命名这条对话');
    } finally {
      setIsConversationUpdating(false);
    }
  };

  const confirmArchiveChange = async () => {
    if (!archiveTarget || isConversationUpdating) return;
    const shouldArchive = !archiveTarget.archived;
    setIsConversationUpdating(true);
    setHistoryError(null);
    try {
      await patchConversation(archiveTarget, { archived: shouldArchive });
      if (shouldArchive && archiveTarget.conversation_id === conversationId) {
        resetConversation();
      }
      setArchiveTarget(null);
      await loadConversations();
    } catch (error) {
      setHistoryError(
        error instanceof Error
          ? error.message
          : shouldArchive
            ? '无法归档这条对话'
            : '无法恢复这条对话',
      );
    } finally {
      setIsConversationUpdating(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget?.archived || isConversationUpdating) return;
    setIsConversationUpdating(true);
    setDeleteError(null);
    try {
      const response = await fetch(`${API_BASE}/api/conversations/${deleteTarget.conversation_id}`, {
        method: 'DELETE',
      });
      // A retry after a lost successful response may legitimately return 404.
      if (!response.ok && response.status !== 404) {
        const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
        throw new Error(typeof payload?.detail === 'string' ? payload.detail : '无法删除这条对话，请重试');
      }
      if (deleteTarget.conversation_id === conversationId) resetConversation();
      setDeleteTarget(null);
      await loadConversations();
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : '无法删除这条对话，请重试');
    } finally {
      setIsConversationUpdating(false);
    }
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || isSending || isConversationOpening || isDatasetUpdating || busyWorkflows.length > 0) return;

    const userMessage: ChatMessage = {
      id: newMessageId('user'),
      role: 'user',
      content: text,
      skills: [...selectedSkills],
      interactionMode,
    };
    const conversationWithUser = [...messages, userMessage];
    setMessages(conversationWithUser);
    setInput('');
    setIsSending(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          conversation_id: conversationId,
          selected_skills: selectedSkills,
          dataset_id: selectedDataset?.dataset_id ?? null,
          interaction_mode: interactionMode,
          language: 'zh-CN',
        }),
      });
      const payload = (await response.json()) as {
        type?: 'done' | 'recommendation' | 'workflow';
        content?: string;
        detail?: string;
        mode?: 'demo' | 'model';
        model_used?: string;
        conversation_id?: string;
        selected_skills?: string[];
        auto_selected?: boolean;
        interaction_mode?: InteractionMode;
        workflow_recommended?: boolean;
        clarification_required?: boolean;
        capability_routing?: CapabilityRoutingTrace;
        capability_recommendation?: CapabilityRecommendation;
        workflow?: Workflow;
      };
      if (!response.ok || !payload.content) {
        throw new Error(payload.detail ?? '后端没有返回有效消息');
      }
      setMessages([
        ...conversationWithUser,
        {
          id: newMessageId('assistant'),
          role: 'assistant',
          content: payload.content ?? '',
          interactionMode: payload.interaction_mode ?? interactionMode,
          workflowRecommended: payload.workflow_recommended,
          clarificationRequired: payload.clarification_required,
          capabilityRouting: payload.capability_routing,
          capabilityRecommendation: payload.capability_recommendation,
          workflow: payload.workflow,
        },
      ]);
      setHealth({
        status: 'ok',
        mode: payload.mode ?? 'demo',
        model: payload.model_used ?? 'conversation-demo',
      });
      if (payload.conversation_id) {
        if (!conversationId) {
          setConversationTitle(text.replace(/\s+/g, ' ').slice(0, 48) || '新数据处理对话');
        }
        setConversationId(payload.conversation_id);
      }
      void loadConversations();
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误';
      const errorContent = `暂时无法连接本地后端。请确认 API 已在 ${API_BASE} 启动。\n\n错误信息：${detail}`;
      setHealth(null);
      setMessages([
        ...conversationWithUser,
        {
          id: newMessageId('assistant-error'),
          role: 'assistant',
          content: errorContent,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const updateWorkflowMessage = (workflow: Workflow) => {
    setMessages((current) =>
      current.map((message) =>
        message.workflow?.workflow_id === workflow.workflow_id
          ? { ...message, workflow }
          : message,
      ),
    );
  };

  const workflowBusyChanged = (workflowId: string, busy: boolean) => {
    setBusyWorkflows((current) => busy
      ? Array.from(new Set([...current, workflowId]))
      : current.filter((id) => id !== workflowId));
  };

  const selectDataset = async (dataset: Dataset) => {
    const context = datasetContext.current;
    if (context.blocked || isDatasetUpdating) throw new Error('当前流程或对话正在更新，请先解锁流程再更换数据集。');
    if (!context.workflow) {
      setSelectedDataset(dataset);
      return;
    }
    setIsDatasetUpdating(true);
    try {
      const response = await fetch(`${API_BASE}/api/workflows/${context.workflow.workflow_id}/dataset`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_id: dataset.dataset_id, expected_revision: context.workflow.revision }),
      });
      const payload = await response.json() as Workflow & {
        detail?: string | { current?: Workflow; message?: string };
      };
      if (!response.ok) {
        if (typeof payload.detail === 'object' && payload.detail.current) updateWorkflowMessage(payload.detail.current);
        throw new Error(typeof payload.detail === 'string' ? payload.detail
          : payload.detail?.message ?? '无法更换数据集，请重新加载流程后重试。');
      }
      if (datasetContext.current.conversationId !== context.conversationId) return;
      updateWorkflowMessage(payload as Workflow);
      setSelectedDataset((payload as Workflow).dataset ?? null);
    } finally {
      setIsDatasetUpdating(false);
    }
  };

  return (
    <main className="flex h-dvh min-h-0 overflow-hidden bg-[#f4f7fb] text-slate-950">
      {isSkillsOpen && (
        <button
          aria-label="关闭 Skill 面板"
          className="fixed inset-0 z-30 bg-slate-950/30 backdrop-blur-[2px] lg:hidden"
          onClick={() => setIsSkillsOpen(false)}
          type="button"
        />
      )}

      <aside
        className={cn(
          'z-40 flex w-[344px] max-w-[calc(100vw-2rem)] min-h-0 shrink-0 flex-col border-r border-slate-200/80 bg-white transition-transform duration-200',
          'max-lg:fixed max-lg:inset-y-0 max-lg:left-0',
          isSkillsOpen ? 'max-lg:translate-x-0' : 'max-lg:-translate-x-full',
        )}
      >
        <div className="flex h-[72px] items-center gap-3 border-b border-slate-200/80 px-5">
          <div className="grid size-10 place-items-center rounded-xl bg-[#1158e6] text-white shadow-[0_8px_22px_rgba(17,88,230,0.24)]">
            <WandSparkles className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[17px] font-semibold tracking-[-0.02em]">NeuroWeave</span>
              <Badge className="h-5 rounded-md bg-blue-50 px-1.5 text-[10px] text-blue-700 shadow-none">
                LOCAL
              </Badge>
            </div>
            <p className="text-xs text-slate-500">数据处理工作台</p>
          </div>
          <Button
            aria-label="关闭 Skill 面板"
            className="lg:hidden"
            onClick={() => setIsSkillsOpen(false)}
            size="icon-sm"
            variant="ghost"
          >
            <X />
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-1 border-b border-slate-200/80 bg-slate-50/70 p-2">
          <button
            aria-pressed={sidebarView === 'conversations'}
            className={cn(
              'flex h-8 items-center justify-center gap-1.5 rounded-lg text-xs font-medium transition-colors',
              sidebarView === 'conversations'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:bg-white/70 hover:text-slate-800',
            )}
            onClick={() => setSidebarView('conversations')}
            type="button"
          >
            <History className="size-3.5" />
            对话
          </button>
          <button
            aria-pressed={sidebarView === 'skills'}
            className={cn(
              'flex h-8 items-center justify-center gap-1.5 rounded-lg text-xs font-medium transition-colors',
              sidebarView === 'skills'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:bg-white/70 hover:text-slate-800',
            )}
            onClick={() => setSidebarView('skills')}
            type="button"
          >
            <Sparkles className="size-3.5" />
            Skills
          </button>
        </div>

        {sidebarView === 'conversations' && (
          <>
            <div className="border-b border-slate-200/80 px-4 py-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold">对话历史</h2>
                  <p className="mt-0.5 text-xs text-slate-500">每次加载 20 条，向下滚动查看更多</p>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    aria-label="刷新对话历史"
                    disabled={isHistoryLoading}
                    onClick={() => void loadConversations()}
                    size="icon-sm"
                    variant="ghost"
                  >
                    <RefreshCw className={cn('size-3.5', isHistoryLoading && 'animate-spin')} />
                  </Button>
                  <Button
                    className="gap-1.5"
                    disabled={isSending}
                    onClick={resetConversation}
                    size="sm"
                  >
                    <MessageSquarePlus className="size-3.5" />
                    新建
                  </Button>
                </div>
              </div>
              <div className="relative mt-3">
                <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
                <Input
                  aria-label="搜索对话历史"
                  maxLength={1000}
                  className="h-9 bg-slate-50 pl-9 text-xs shadow-none"
                  onChange={(event) => setConversationSearch(event.target.value)}
                  placeholder="搜索标题或消息内容"
                  value={conversationSearch}
                />
              </div>
              <div className="mt-2 grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1">
                {([
                  ['active', '最近对话'],
                  ['archived', '已归档'],
                ] as const).map(([scope, label]) => (
                  <button
                    aria-pressed={historyScope === scope}
                    className={cn(
                      'h-7 rounded-md px-2 text-[11px] font-medium transition-colors',
                      historyScope === scope
                        ? 'bg-white text-slate-900 shadow-sm'
                        : 'text-slate-500 hover:text-slate-800',
                    )}
                    key={scope}
                    onClick={() => setHistoryScope(scope)}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="space-y-1.5 p-3">
                {historyError && (
                  <div role="alert" className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                    {historyError}
                    <Button className="ml-2" size="sm" variant="ghost" onClick={() => void retryConversations()} disabled={isHistoryLoading}>
                      重试
                    </Button>
                  </div>
                )}
                {isConversationOpening && (
                  <div role="status" className="flex items-center gap-2 px-3 py-2 text-xs text-slate-500">
                    <LoaderCircle className="size-4 animate-spin" /> 正在打开对话…
                  </div>
                )}
                {!isHistoryLoading && conversations.length === 0 && !historyError && (
                  <div className="px-4 py-12 text-center text-sm text-slate-400">
                    {conversationSearch.trim()
                      ? '没有匹配的对话'
                      : historyScope === 'archived'
                        ? '还没有归档的对话'
                        : '还没有保存的对话'}
                  </div>
                )}
                {conversations.map((conversation) => {
                  const active = conversation.conversation_id === conversationId;
                  return (
                    <div
                      className={cn(
                        'flex w-full items-start rounded-xl border transition-colors',
                        active
                          ? 'border-blue-200 bg-blue-50/80'
                          : 'border-transparent hover:border-slate-200 hover:bg-slate-50',
                      )}
                      key={conversation.conversation_id}
                    >
                      <button
                        aria-current={active ? 'page' : undefined}
                        className="min-w-0 flex-1 px-3 py-3 text-left"
                        disabled={isSending || isConversationUpdating || isConversationOpening}
                        onClick={() =>
                          historyScope === 'archived'
                            ? setArchiveTarget(conversation)
                            : void openConversation(conversation)
                        }
                        type="button"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p
                            className={cn(
                              'truncate text-xs font-semibold',
                              active ? 'text-blue-800' : 'text-slate-800',
                            )}
                          >
                            {conversation.title}
                          </p>
                          <span className="shrink-0 text-[10px] text-slate-400">
                            {conversationTime(conversation.updated_at)}
                          </span>
                        </div>
                        <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-slate-500">
                          {conversation.last_message_preview || '尚未发送消息'}
                        </p>
                        <p className="mt-1.5 text-[10px] text-slate-400">
                          {conversation.message_count} 条消息
                          {historyScope === 'archived' && ' · 点击恢复'}
                        </p>
                      </button>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          aria-label={`管理对话：${conversation.title}`}
                          className="mr-1 mt-2 grid size-7 shrink-0 place-items-center rounded-md text-slate-400 outline-none hover:bg-white hover:text-slate-700 focus-visible:ring-2 focus-visible:ring-blue-500"
                          disabled={isConversationUpdating || isConversationOpening || isSending}
                        >
                          <MoreHorizontal className="size-4" />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-32">
                          <DropdownMenuItem onClick={() => beginRename(conversation)}>
                            <Pencil />
                            重命名
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setArchiveTarget(conversation)}>
                            {conversation.archived ? <ArchiveRestore /> : <Archive />}
                            {conversation.archived ? '恢复对话' : '归档对话'}
                          </DropdownMenuItem>
                          {conversation.archived && (
                            <DropdownMenuItem variant="destructive" onClick={() => {
                              setDeleteError(null);
                              setDeleteTarget(conversation);
                            }}>
                              <Trash2 />
                              永久删除
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  );
                })}
                <div ref={historyEndRef} className="h-px" aria-hidden="true" />
                {isHistoryLoading && (
                  <div role="status" className="flex items-center justify-center gap-2 py-6 text-sm text-slate-400">
                    <LoaderCircle className="size-4 animate-spin" />
                    {conversations.length === 0 ? '正在读取对话…' : '正在加载更多…'}
                  </div>
                )}
                {!isHistoryLoading && hasMoreConversations && !historyError && (
                  <Button className="w-full text-xs text-slate-500" variant="ghost" onClick={() => void loadMoreConversations()}>
                    继续向下滚动，或点击加载更多
                  </Button>
                )}
                {!isHistoryLoading && !historyError && !hasMoreConversations && conversations.length > 0 && (
                  <p role="status" className="py-4 text-center text-xs text-slate-400">已加载全部 {conversations.length} 条对话</p>
                )}
              </div>
            </ScrollArea>
          </>
        )}

        <div className={cn('border-b border-slate-200/80 px-5 py-5', sidebarView !== 'skills' && 'hidden')}>
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Skills</h2>
              <p className="mt-0.5 text-xs text-slate-500">选择本次对话的处理方法</p>
            </div>
            <Badge variant="secondary" className="rounded-md font-mono text-[10px]">
              {skills.length}
            </Badge>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <Input
              aria-label="搜索 Skills"
              className="h-9 bg-slate-50 pl-9 text-sm shadow-none"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索 Skill"
              value={search}
            />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1">
            {(['all', 'NeuroClaw', 'LocalFlow'] as const).map((source) => (
              <button
                aria-pressed={sourceFilter === source}
                className={cn(
                  'h-7 rounded-md px-2 text-[10px] font-medium transition-colors',
                  sourceFilter === source
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800',
                )}
                key={source}
                onClick={() => setSourceFilter(source)}
                type="button"
              >
                {source === 'all' ? '全部' : source === 'LocalFlow' ? 'NeuroWeave' : source}
              </button>
            ))}
          </div>
        </div>

        <ScrollArea className={cn('min-h-0 flex-1', sidebarView !== 'skills' && 'hidden')}>
          <div className="space-y-2 p-3">
            {visibleSkills.map((skill) => {
              const SkillIcon = iconForSkill(skill);
              const selected = selectedSkills.includes(skill.name);
              return (
                <button
                  aria-label={`${selected ? '取消选择' : '选择'} ${skill.display_name}`}
                  aria-pressed={selected}
                  title={skill.runtime_reasons?.join('\n') || undefined}
                  className={cn(
                    'group w-full rounded-xl border p-3.5 text-left transition-colors',
                    selected
                      ? 'border-blue-200 bg-blue-50/80 shadow-[0_1px_1px_rgba(15,23,42,0.03)]'
                      : 'border-transparent hover:border-slate-200 hover:bg-slate-50',
                  )}
                  key={skill.name}
                  onClick={() => toggleSkill(skill.name)}
                  type="button"
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        'mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg border',
                        selected
                          ? 'border-blue-200 bg-white text-blue-700'
                          : 'border-slate-200 bg-white text-slate-500',
                      )}
                    >
                      <SkillIcon className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">
                            {skill.display_name}
                          </span>
                          <span className="mt-0.5 block font-mono text-[9px] uppercase tracking-wide text-slate-400">
                            {skill.source === 'NeuroClaw' ? 'NeuroClaw' : 'NeuroWeave'}
                          </span>
                        </span>
                        <span
                          className={cn(
                            'grid size-5 shrink-0 place-items-center rounded-md border transition-colors',
                            selected
                              ? 'border-blue-600 bg-blue-600 text-white'
                              : 'border-slate-200 bg-white text-transparent group-hover:border-slate-300',
                          )}
                        >
                          <Check className="size-3.5" />
                        </span>
                      </span>
                      <span className="mt-1.5 line-clamp-2 text-xs leading-5 text-slate-500">
                        {skill.summary_zh || skill.description}
                      </span>
                      <span className="mt-2.5 flex items-center gap-2 text-[10px] text-slate-400">
                        <span className="max-w-[130px] truncate rounded bg-white px-1.5 py-0.5 ring-1 ring-slate-200">
                          {skill.script_count
                            ? `${skill.script_count} 个脚本`
                            : skill.runtime === 'SKILL.md workflow'
                              ? 'SKILL.md'
                              : skill.runtime}
                        </span>
                        <span className="flex items-center gap-1">
                          <span
                            className={cn(
                              'size-1.5 rounded-full',
                              skill.execution_state === 'ready'
                                ? 'bg-emerald-500'
                                : skill.execution_state === 'needs_environment'
                                  ? 'bg-amber-400'
                                  : 'bg-blue-500',
                            )}
                          />
                          {skill.execution_state === 'ready'
                            ? `可运行 ${skill.ready_runner_count ?? 1}`
                            : skill.execution_state === 'needs_environment'
                              ? '待配置环境'
                              : '可规划'}
                        </span>
                        <span
                          className={cn(
                            'rounded px-1.5 py-0.5',
                            skill.execution_state === 'ready'
                              ? 'bg-emerald-50 text-emerald-700'
                              : skill.execution_state === 'needs_environment'
                                ? 'bg-amber-50 text-amber-700'
                                : 'bg-slate-100 text-slate-500',
                          )}
                        >
                          {skill.execution_state === 'ready'
                            ? 'Runner'
                            : skill.execution_state === 'needs_environment'
                              ? '缺少依赖'
                              : skill.structure_mode === 'planning'
                                ? '规划结构'
                                : '说明型'}
                        </span>
                      </span>
                    </span>
                  </div>
                </button>
              );
            })}
            {visibleSkills.length === 0 && (
              <div className="px-4 py-12 text-center text-sm text-slate-400">没有匹配的 Skill</div>
            )}
          </div>
        </ScrollArea>

        <div className="border-t border-slate-200/80 p-4">
          <div className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
            <span
              className={cn(
                'size-2 rounded-full',
                health ? 'bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.12)]' : 'bg-slate-300',
              )}
            />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium">{health ? '本地 API 已连接' : '等待本地 API'}</p>
              <p className="truncate text-[10px] text-slate-400">
                {sidebarView === 'conversations'
                  ? `已加载 ${conversations.length} 条对话${hasMoreConversations ? ' · 下滑加载更多' : ''}`
                  : catalogStats
                  ? `有依据 ${catalogStats.capability_catalog?.evidence_backed_methods ?? catalogStats.structured ?? 0} · Runner ${catalogStats.capability_catalog?.runner_methods ?? catalogStats.runner_structured ?? 0}`
                  : API_BASE}
              </p>
            </div>
          </div>
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[72px] shrink-0 items-center gap-3 border-b border-slate-200/80 bg-white/85 px-4 backdrop-blur-xl sm:px-6">
          <Button
            aria-label="打开 Skill 面板"
            className="lg:hidden"
            onClick={() => setIsSkillsOpen(true)}
            size="icon"
            variant="ghost"
          >
            <Menu />
          </Button>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-sm font-semibold sm:text-base">{conversationTitle}</h1>
              <ChevronRight className="hidden size-4 text-slate-300 sm:block" />
              <span className="hidden truncate text-xs text-slate-400 sm:block">
                {selectedDetails.length > 0
                  ? `已启用 ${selectedDetails.length} 个 Skill`
                  : '尚未选择 Skill'}
              </span>
            </div>
          </div>
          <div className="hidden items-center gap-2 text-xs text-slate-500 sm:flex">
            <span
              className={cn('size-1.5 rounded-full', health ? 'bg-emerald-500' : 'bg-slate-300')}
            />
            {health?.mode === 'model' ? health.model : '对话演示模式'}
          </div>
          <DatasetPicker
            key={`${conversationId ?? 'new'}:${currentWorkflow?.workflow_id ?? 'draft'}`}
            apiBase={API_BASE}
            onSelected={selectDataset}
            selectedDataset={selectedDataset}
            disabled={datasetDisabled}
            disabledReason={datasetNotice ?? '正在更新对话或流程，请稍候。'}
          />
          <Button className="gap-2" disabled={isSending || isConversationOpening || isDatasetUpdating || busyWorkflows.length > 0} onClick={resetConversation} size="sm" variant="outline">
            <MessageSquarePlus className="size-4" />
            <span className="hidden sm:inline">新建对话</span>
          </Button>
        </header>

        <ScrollArea className="min-h-0 flex-1">
          <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col px-4 py-8 sm:px-8 sm:py-10">
            <div className="mb-9 flex items-center gap-4 border-b border-slate-200/80 pb-7">
              <div className="grid size-11 shrink-0 place-items-center rounded-xl border border-blue-100 bg-blue-50 text-blue-700">
                <Sparkles className="size-5" />
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-blue-600">
                  Conversation workspace
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-[-0.025em] text-slate-900">
                  {interactionMode === 'task' ? '描述你的数据处理目标' : '与 NeuroWeave 直接对话'}
                </h2>
                <p className="mt-1 text-sm leading-6 text-slate-500">
                  {interactionMode === 'task'
                    ? `模型逐层展开能力树，再只加载相关 Skill；可推荐单步任务或多个 Skill 的组合。`
                    : '普通对话模式只返回文字回答，不会创建或推荐流程卡片。'}
                </p>
              </div>
            </div>

            <div className="space-y-8">
              {messages.map((message) => (
                <article
                  className={cn('flex gap-3.5', message.role === 'user' && 'justify-end')}
                  key={message.id}
                >
                  {message.role === 'assistant' && (
                    <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-slate-900 text-white">
                      <Bot className="size-4" />
                    </div>
                  )}
                  <div
                    className={cn(
                      'max-w-[min(720px,85%)]',
                      message.role === 'user'
                        ? 'rounded-2xl rounded-tr-md bg-[#1158e6] px-4 py-3 text-white shadow-[0_8px_24px_rgba(17,88,230,0.16)]'
                        : 'pt-1 text-slate-700',
                    )}
                  >
                    {message.role === 'assistant' && (
                      <p className="mb-1.5 text-xs font-semibold text-slate-900">NeuroWeave</p>
                    )}
                    <p className="whitespace-pre-wrap text-sm leading-7">{message.content}</p>
                    {message.role === 'assistant' && message.capabilityRouting && (
                      <div className="mt-3 inline-flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-md border border-blue-100 bg-blue-50 px-2 py-1 text-[10px] font-medium text-blue-700">
                        <ListTree className="size-3" />
                        {message.capabilityRouting.strategy === 'hierarchical' ? (
                          <span>
                            分层检索 {message.capabilityRouting.levels.length} 层 · 查看{' '}
                            {message.capabilityRouting.candidates_seen} 个候选 · 树上下文{' '}
                            {Math.round(message.capabilityRouting.payload_ratio * 100)}%
                          </span>
                        ) : message.capabilityRouting.strategy === 'semantic' ? (
                          <span>
                            语义意图匹配 · 置信度{' '}
                            {Math.round(message.capabilityRouting.confidence * 100)}%
                          </span>
                        ) : (
                          <span>本地能力回退 · 未向模型发送整棵能力树</span>
                        )}
                      </div>
                    )}
                    {message.role === 'assistant' &&
                      message.interactionMode === 'task' &&
                      message.workflowRecommended === false &&
                      !message.capabilityRecommendation &&
                      !message.workflow && (
                        <div className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-medium text-slate-500">
                          <MessageCircle className="size-3" />
                          {message.clarificationRequired
                            ? '需要补充信息后再生成流程'
                            : '模型判断：本次无需生成流程'}
                        </div>
                      )}
                    {message.capabilityRecommendation && (
                      <CapabilityRecommendationCard
                        recommendation={message.capabilityRecommendation}
                      />
                    )}
                    {message.workflow && (
                      <WorkflowCard
                        apiBase={API_BASE}
                        onChange={updateWorkflowMessage}
                        disabled={isDatasetUpdating || isConversationOpening || isSending}
                        onBusyChange={workflowBusyChanged}
                        workflow={message.workflow}
                      />
                    )}
                    {message.skills && message.skills.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5 border-t border-white/20 pt-2.5">
                        {message.skills.map((skillName) => (
                          <span
                            className="rounded-md bg-white/10 px-2 py-1 font-mono text-[10px] text-blue-50"
                            key={skillName}
                          >
                            {skillName}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </article>
              ))}
              {isSending && (
                <div className="flex items-center gap-3.5 text-sm text-slate-500">
                  <div className="grid size-8 place-items-center rounded-lg bg-slate-900 text-white">
                    <Bot className="size-4" />
                  </div>
                  <LoaderCircle className="size-4 animate-spin text-blue-600" />
                  {interactionMode === 'task'
                    ? '正在逐层定位能力并读取相关 Skill…'
                    : '正在组织回复…'}
                </div>
              )}
              <div ref={messageEndRef} />
            </div>
          </div>
        </ScrollArea>

        <div className="shrink-0 border-t border-slate-200/70 bg-white/88 px-4 py-4 backdrop-blur-xl sm:px-6 sm:py-5">
          <div className="mx-auto max-w-4xl">
            <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
              <fieldset
                aria-label="交互模式"
                className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1"
              >
                <Button
                  aria-pressed={interactionMode === 'chat'}
                  className={cn(
                    'h-7 gap-1.5 rounded-md px-2.5 text-xs shadow-none',
                    interactionMode === 'chat'
                      ? 'bg-white text-slate-900 hover:bg-white'
                      : 'text-slate-500 hover:bg-slate-200 hover:text-slate-800',
                  )}
                  disabled={isSending}
                  onClick={() => setInteractionMode('chat')}
                  size="sm"
                  variant="ghost"
                >
                  <MessageCircle className="size-3.5" />
                  普通对话
                </Button>
                <Button
                  aria-pressed={interactionMode === 'task'}
                  className={cn(
                    'h-7 gap-1.5 rounded-md px-2.5 text-xs shadow-none',
                    interactionMode === 'task'
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : 'text-slate-500 hover:bg-slate-200 hover:text-slate-800',
                  )}
                  disabled={isSending}
                  onClick={() => setInteractionMode('task')}
                  size="sm"
                  variant="ghost"
                >
                  <ListChecks className="size-3.5" />
                  任务模式
                </Button>
              </fieldset>
              <p className="text-[11px] text-slate-400">
                {interactionMode === 'task'
                  ? '逐层展开能力树 → 读取相关 Skill → 推荐方法或组合'
                  : '只进行问答，不生成流程'}
              </p>
            </div>
            {datasetNotice && <p role="status" className="mb-2 wrap-anywhere text-xs text-slate-500">{datasetNotice}</p>}
            {selectedDataset && (
              <div className="mb-2.5 flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
                <Database className="size-3.5 text-blue-600" />
                <span className="font-medium text-slate-700">{selectedDataset.display_name}</span>
                <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-slate-400">
                  {selectedDataset.relative_path || selectedDataset.absolute_path}
                </span>
                {selectedDataset.inspection.is_bids && <Badge variant="outline">BIDS</Badge>}
                {selectedDataset.inspection.has_dwi && <Badge variant="outline">DWI</Badge>}
              </div>
            )}
            {selectedDetails.length > 0 && (
              <div className="mb-2.5 flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-[11px] font-medium text-slate-400">本次启用</span>
                {selectedDetails.map((skill) => (
                  <button
                    className="inline-flex h-7 items-center gap-1.5 rounded-md border border-blue-100 bg-blue-50 px-2 text-[11px] font-medium text-blue-700 transition-colors hover:bg-blue-100"
                    key={skill.name}
                    onClick={() => toggleSkill(skill.name)}
                    type="button"
                  >
                    {skill.display_name}
                    <X className="size-3" />
                  </button>
                ))}
              </div>
            )}
            <div className="rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_10px_38px_rgba(15,23,42,0.08)] focus-within:border-blue-300 focus-within:ring-4 focus-within:ring-blue-50">
              <Textarea
                aria-label="对话输入"
                className="min-h-[68px] resize-none border-0 bg-transparent px-3 py-2 text-sm leading-6 shadow-none focus-visible:ring-0"
                disabled={isSending}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void sendMessage();
                  }
                }}
                placeholder={
                  interactionMode === 'chat'
                    ? '输入你想了解或讨论的问题……'
                    : selectedDataset
                      ? `描述希望如何处理 ${selectedDataset.display_name}……`
                      : '描述处理需求，模型会判断是否需要推荐流程……'
                }
                value={input}
              />
              <div className="flex items-center justify-between gap-3 px-1 pb-1">
                <div className="flex min-w-0 items-center gap-2 text-[11px] text-slate-400">
                  <PanelLeftClose className="size-3.5" />
                  <span className="truncate">Enter 发送 · Shift + Enter 换行</span>
                </div>
                <Button
                  aria-label="发送消息"
                  className="size-9 rounded-xl bg-[#1158e6] shadow-[0_6px_18px_rgba(17,88,230,0.22)] hover:bg-blue-700"
                  disabled={!input.trim() || isSending || isConversationOpening || isDatasetUpdating || busyWorkflows.length > 0}
                  onClick={() => void sendMessage()}
                  size="icon"
                >
                  {isSending ? (
                    <LoaderCircle className="animate-spin" />
                  ) : (
                    <SendHorizontal />
                  )}
                </Button>
              </div>
            </div>
            <p className="mt-2 text-center text-[10px] text-slate-400">
              {interactionMode === 'task'
                ? '流程需经过方法选择、参数确认和 Dry-run；仅已接入可信 Runner 的方法可显式启动。'
                : '普通对话不会创建 Workflow，也不会执行文件或软件操作。'}
            </p>
          </div>
        </div>
      </section>

      <Dialog
        onOpenChange={(open) => {
          if (!open && !isConversationUpdating) {
            setEditingConversation(null);
            setRenameTitle('');
          }
        }}
        open={editingConversation !== null}
      >
        <DialogContent>
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void submitRename();
            }}
          >
            <DialogHeader>
              <DialogTitle>重命名对话</DialogTitle>
              <DialogDescription>
                修改后的标题只用于整理历史记录，不会改变对话内容。
              </DialogDescription>
            </DialogHeader>
            <Input
              aria-label="对话标题"
              maxLength={120}
              onChange={(event) => setRenameTitle(event.target.value)}
              placeholder="输入对话标题"
              value={renameTitle}
            />
            <DialogFooter>
              <Button
                disabled={isConversationUpdating}
                onClick={() => {
                  setEditingConversation(null);
                  setRenameTitle('');
                }}
                type="button"
                variant="outline"
              >
                取消
              </Button>
              <Button
                disabled={!renameTitle.trim() || isConversationUpdating}
                type="submit"
              >
                {isConversationUpdating && <LoaderCircle className="animate-spin" />}
                保存标题
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog
        onOpenChange={(open) => {
          if (!open && !isConversationUpdating) setArchiveTarget(null);
        }}
        open={archiveTarget !== null}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {archiveTarget?.archived ? '恢复这条对话？' : '归档这条对话？'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {archiveTarget?.archived
                ? '恢复后，它会重新出现在最近对话中，原有消息和流程记录保持不变。'
                : '归档后，它会移到“已归档”列表；你可以随时恢复，消息不会被删除。'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isConversationUpdating}>取消</AlertDialogCancel>
            <AlertDialogAction
              disabled={isConversationUpdating}
              onClick={() => void confirmArchiveChange()}
            >
              {isConversationUpdating && <LoaderCircle className="animate-spin" />}
              {archiveTarget?.archived ? '恢复对话' : '确认归档'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open && !isConversationUpdating) {
            setDeleteTarget(null);
            setDeleteError(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>永久删除这条对话？</AlertDialogTitle>
            <AlertDialogDescription>
              “{deleteTarget?.title}”的全部消息和历史摘要将被永久删除，无法恢复。
              已创建的任务、运行记录、数据集和输出文件会保留。
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && <p role="alert" className="text-sm text-red-600">{deleteError}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isConversationUpdating}>取消</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={isConversationUpdating} onClick={() => void confirmDelete()}>
              {isConversationUpdating && <LoaderCircle className="animate-spin" />}
              永久删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </main>
  );
}
