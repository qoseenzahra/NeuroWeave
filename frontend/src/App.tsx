import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useIsMutating, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { patchConversation } from './features/conversations/conversationsApi';
import type { ConversationDetailState } from './features/conversations/useConversations';
import { currentConversationRead, mergeConversationMessages } from './features/conversations/conversationContext';
import { adoptConflict, useWorkflowDataset, useWorkflowQuery, workflowQueryKey } from './features/workflows/useWorkflows';
import { saveWorkflowOutput } from './features/workspace/workspaceApi';
import type { Dataset } from './features/datasets/datasetsApi';
import type { Workspace } from './features/workspace/workspaceTypes';
import NeuroSplash from './components/SplashScreen/NeuroSplash';
import { AppRail } from './components/AppRail';
import type { RailDomain } from './components/AppRail';
import { ContextPanelHeader } from './components/ContextPanelHeader';
import { useThemeStore } from './stores/themeStore';
import { setMouseWaveEnabled } from './lib/mouseWave';
import { ChatHeader } from './features/chat/ChatHeader';
import { MessageArea } from './features/chat/MessageArea';
import { MessageComposer } from './features/chat/MessageComposer';
import type { ChatMessage } from './features/chat/chatMessages';
import { useSendChat } from './features/chat/useChat';
import { DatasetPicker } from './features/datasets/DatasetPicker';
import { StoragePanel } from './features/storage/StoragePanel';
import { WorkspacePanel } from './features/workspace/WorkspacePanel';
import { getTranslations } from './lib/i18n';
import { useLanguageStore } from './stores/languageStore';
import { ConversationRow } from './features/conversations/ConversationRow';
import { ConversationSearch } from './features/conversations/ConversationSearch';
import type { ConversationListItem } from './features/conversations/conversationTypes';
import type { InteractionMode } from './features/conversations/conversationTypes';
import {
  useArchiveConversation,
  useConversationDetail,
  useConversationList,
  useDeleteConversation,
  useLoadOlderMessages,
  useRenameConversation
} from './features/conversations/useConversations';
import { SkillList } from './features/skills/SkillList';
import { SkillDetails } from './features/skills/SkillDetails';
import type { Skill } from './features/skills/skillsApi';
import { DatasetFilesDrawer } from './features/datasets/DatasetFilesDrawer';
import { useSkillStore } from './stores/skillStore';
import { useSkills } from './features/skills/useSkills';
import { useDatasetStore } from './stores/datasetStore';
import { useSelectedDataset } from './features/datasets/useDatasets';
import { useConversationUiStore } from './stores/conversationUiStore';
import { useWorkspaceToolEvents } from './features/workspace/useWorkspaceToolEvents';
import { DatasetContextPanel } from './features/datasets/DatasetContextPanel';
import { StorageContextPanel } from './features/storage/StorageContextPanel';
import { WorkspaceContextPanel } from './features/workspace/WorkspaceContextPanel';
import { ApiError } from './api/http';
import { Button } from './ui/Button';
import { Tabs } from './ui/Tabs';
import type { TabItem } from './ui/Tabs';

function App() {
  const ui = useConversationUiStore();
  const { activeConversationId } = ui;
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('chat');
  const { selectedSkillIds, setSelectedSkills } = useSkillStore();
  const [viewedSkill, setViewedSkill] = useState<Skill | null>(null);
  // Keep unsent skill choices scoped to their conversation when browsing history.
  const skillDrafts = useRef<Record<string, string[]>>({});
  const skills = useSkills().data?.skills ?? [];
  const skillsStats = useSkills().data?.stats;
  const selectedDatasetId = useDatasetStore((s) => s.selectedDatasetId);
  const { data: chosenDataset } = useSelectedDataset(selectedDatasetId);
  const [datasetFilesOpen, setDatasetFilesOpen] = useState(false);
  const [restoredConversation, setRestoredConversation] = useState<string | null>(null);
  const [datasetPickerOpen, setDatasetPickerOpen] = useState(false);
  const language = useLanguageStore((s) => s.language);
  const t = getTranslations(language);
  const selectedSkills = selectedSkillIds.map(name => skills.find(skill => skill.name === name) ?? { name, display_name: name });
  const selectedSkillNames = selectedSkills.map((s) => s.display_name || s.name).join(' + ');
  const [input, setInput] = useState('');
  const [conversationSearch, setConversationSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [chatSection, setChatSection] = useState<'history' | 'archived'>('history');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarView, setSidebarView] = useState<RailDomain>('conversations');
  const theme = useThemeStore((s) => s.theme);
  const wave = useThemeStore((s) => s.wave);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);
  const darkMode = theme === 'dark';
  const [sendError, setSendError] = useState<string | null>(null);
  const [olderError, setOlderError] = useState<string | null>(null);
  const [localMessagesByConversation, setLocalMessagesByConversation] = useState<
    Record<string, ChatMessage[]>
  >({});
  const [localNewMessages, setLocalNewMessages] = useState<ChatMessage[]>([]);
  const localMessages = activeConversationId
    ? (localMessagesByConversation[activeConversationId] ?? [])
    : localNewMessages;
  const scope = chatSection === 'archived' ? 'archived' : 'active';
  const listQuery = useConversationList(scope, debouncedSearch, sidebarOpen && sidebarView === 'conversations');
  const listItems: ConversationListItem[] = (listQuery.data?.pages ?? []).flatMap(
    (p) => p.conversations
  );
  const detailQuery = useConversationDetail(activeConversationId);
  const renameMutation = useRenameConversation();
  const archiveMutation = useArchiveConversation();
  const deleteMutation = useDeleteConversation();
  const sendMutation = useSendChat();
  const [draftWorkspaceId, setDraftWorkspaceId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const workspaceMutation = useMutation({
    mutationKey: ['workflow-change', 'output-root'],
    mutationFn: async ({ id, workspaceId }: { id: string | null; workspaceId: string | null }) => {
      if (activeWorkflow) {
        const updated = await saveWorkflowOutput(activeWorkflow.workflow_id, '.', activeWorkflow.revision,
          { workspaceId, conversationId: id });
        queryClient.setQueryData(workflowQueryKey(updated.workflow_id), updated);
      } else if (id) await patchConversation(id, { workspace_id: workspaceId });
    },
    onError: error => { adoptConflict(queryClient, error); },
    onSuccess: (_data, { id, workspaceId }) => {
      setDraftWorkspaceId(workspaceId);
      if (id) queryClient.setQueryData<ConversationDetailState>(['conversation', id], (previous) =>
        previous ? { ...previous, workspaceId } : previous
      );
      void queryClient.invalidateQueries({ queryKey: ['conversations'] });
    }
  });
  const [activeTurn, setActiveTurn] = useState<string | null>(null);
  const { events: liveWorkspaceEvents } = useWorkspaceToolEvents(activeTurn);
  const [storageOpen, setStorageOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const mutating =
    renameMutation.isPending || archiveMutation.isPending || deleteMutation.isPending;
  const detail = detailQuery.data ?? null;
  const serverMessages = detail?.messages ?? [];
  const mergedMessages = mergeConversationMessages(serverMessages, localMessages, detail?.readGeneration ?? 0);
  const latestWorkflowMessage = [...mergedMessages].reverse().find(message => message.workflow || message.workflowId);
  const embeddedWorkflow = latestWorkflowMessage?.workflow ?? null;
  const activeWorkflowId = embeddedWorkflow?.workflow_id ?? latestWorkflowMessage?.workflowId
    ?? (typeof detail?.context.workflow_id === 'string' ? detail.context.workflow_id : null);
  const workflowQuery = useWorkflowQuery(activeWorkflowId, embeddedWorkflow);
  const activeWorkflow = workflowQuery.data ?? null;
  // The persisted workflow owns its inputs, even after opening history.
  const selectedDataset = activeWorkflow ? activeWorkflow.dataset : chosenDataset;
  const workspaceId = activeWorkflow ? (activeWorkflow.workspace_id ?? null)
    : activeConversationId ? (detail?.workspaceId ?? null) : draftWorkspaceId;
  const datasetPatch = useWorkflowDataset();
  const workflowMutations = useIsMutating({ mutationKey: ['workflow-change'] });
  const contextLoading = Boolean(activeConversationId && (restoredConversation !== activeConversationId || detailQuery.isPending || detailQuery.isError))
    || Boolean(activeWorkflowId && (workflowQuery.isPending || workflowQuery.isError));
  const navigationBusy = sendMutation.isPending || workspaceMutation.isPending || datasetPatch.isPending || workflowMutations > 0 || mutating;
  const contextBusy = sendMutation.isPending || workspaceMutation.isPending || datasetPatch.isPending
    || workflowMutations > 0 || contextLoading || mutating;
  const datasetLocked = Boolean(activeWorkflow?.locked_at || activeWorkflow?.status === 'confirmed');
  const datasetDisabled = datasetLocked || contextBusy;
  const datasetNotice = datasetLocked ? t.workflowDatasetLocked
    : activeWorkflow ? t.datasetChangeNotice : null;
  const setDatasetId = useDatasetStore(s => s.setDatasetId);

  // Apply a fetched snapshot once when opening a conversation. Background
  // refresh must not overwrite choices made after it was opened.
  useLayoutEffect(() => {
    if (!activeConversationId || !detail || restoredConversation === activeConversationId) return;
    const context = detail.context;
    setSelectedSkills(skillDrafts.current[activeConversationId] ?? (Array.isArray(context.selected_skills)
      ? context.selected_skills.filter((id): id is string => typeof id === 'string') : []));
    setDatasetId(typeof context.dataset_id === 'string' ? context.dataset_id : null);
    // Deliberately synchronize controls with the asynchronous server snapshot.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setInteractionMode(context.interaction_mode === 'task' ? 'task' : 'chat');
    setRestoredConversation(activeConversationId);
  }, [activeConversationId, detail, restoredConversation, setDatasetId, setSelectedSkills]);
  useEffect(() => {
    if (activeWorkflow) {
      setDatasetId(activeWorkflow.dataset_id);
      if (activeWorkflow.dataset)
        queryClient.setQueryData(['datasets', 'detail', activeWorkflow.dataset_id], activeWorkflow.dataset);
    }
  }, [activeWorkflow, queryClient, setDatasetId]);

  const handleWorkspaceSelect = async (workspace: Workspace | null) => {
    if (datasetDisabled) throw new Error(t.workspaceLockedHint);
    await workspaceMutation.mutateAsync({ id: activeConversationId, workspaceId: workspace?.id ?? null });
  };
  const handleDatasetSelect = async (dataset: Dataset) => {
    if (datasetDisabled) throw new Error(t.workflowDatasetLocked);
    if (activeWorkflow) {
      const updated = await datasetPatch.mutateAsync({
        workflowId: activeWorkflow.workflow_id, datasetId: dataset.dataset_id,
        expectedRevision: activeWorkflow.revision,
      });
      setDatasetId(updated.dataset_id);
    } else setDatasetId(dataset.dataset_id);
    queryClient.setQueryData(['datasets', 'detail', dataset.dataset_id], dataset);
  };
  const openDatasetPicker = () => { if (!datasetDisabled) setDatasetPickerOpen(true); };
  const changeSkills = (ids: string[]) => {
    if (contextBusy || olderMutation.isPending) return;
    const next = [...new Set(ids)];
    if (activeConversationId) skillDrafts.current[activeConversationId] = next;
    setSelectedSkills(next);
  };
  const addSkill = (id: string) => changeSkills([...selectedSkillIds, id]);
  const removeSkill = (id: string) => changeSkills(selectedSkillIds.filter(value => value !== id));
  const clearSkills = () => changeSkills([]);
  const viewSkill = (id: string) => setViewedSkill(skills.find(skill => skill.name === id) ?? {
    name:id, display_name:id, description:'', layer:'', skill_type:'', runtime:'', status:''
  });
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(conversationSearch), 250);
    return () => window.clearTimeout(timer);
  }, [conversationSearch]);
  useEffect(() => {
    setMouseWaveEnabled(wave);
    return () => setMouseWaveEnabled(false);
  }, [wave]);
  const handleSelect = (id: string) => {
    if (navigationBusy || olderMutation.isPending) return;
    setWorkspaceOpen(false);
    setDatasetPickerOpen(false);
    setDatasetFilesOpen(false);
    setInput('');
    setRestoredConversation(null);
    setSendError(null);
    setOlderError(null);
    ui.setActionError(null);
    ui.selectConversation(id);
    ui.setOpenMenuId(null);
  };
  const handleNew = () => {
    if (
      navigationBusy ||
      olderMutation.isPending
    )
      return;
    setDraftWorkspaceId(workspaceId);
    setRestoredConversation(null);
    setDatasetPickerOpen(false);
    setDatasetFilesOpen(false);
    setWorkspaceOpen(false);
    setLocalNewMessages([]);
    setSelectedSkills([]);
    setActiveTurn(null);
    ui.setActionError(null);
    setSendError(null);
    setOlderError(null);
    setInput('');
    ui.selectConversation(null);
  };
  const handleCommitRename = (id: string) => {
    const title = ui.renameValue.replace(/\s+/g, ' ').trim();
    if (!title) {
      ui.cancelRename();
      return;
    }
    ui.setActionError(null);
    renameMutation.mutate(
      { id, title },
      {
        onSuccess: () => ui.cancelRename(),
        onError: (e) => ui.setActionError(e instanceof Error ? e.message : t.errorMessage)
      }
    );
  };
  const handleArchive = (id: string, archived: boolean) => {
    if (contextBusy || olderMutation.isPending) return;
    ui.setActionError(null);
    archiveMutation.mutate(
      { id, archived },
      {
        onSuccess: () => {
          ui.setOpenMenuId(null);
          if (archived && id === activeConversationId) ui.selectConversation(null);
        },
        onError: (e) => ui.setActionError(e instanceof Error ? e.message : t.errorMessage)
      }
    );
  };
  const handleConfirmDelete = (id: string) => {
    if (contextBusy || olderMutation.isPending) return;
    ui.setActionError(null);
    deleteMutation.mutate(id, {
      onSuccess: () => {
        setLocalMessagesByConversation((previous) => {
          const next = { ...previous };
          delete next[id];
          return next;
        });
        ui.cancelDelete();
        ui.setOpenMenuId(null);
        if (useConversationUiStore.getState().activeConversationId === id) {
          setLocalNewMessages([]);
          setInput('');
          setSendError(null);
          setOlderError(null);
          setActiveTurn(null);
          setWorkspaceOpen(false);
          ui.selectConversation(null);
        }
      },
      onError: (e) => ui.setActionError(e instanceof Error ? e.message : t.errorMessage)
    });
  };
  const mainRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const animation = mainRef.current?.animate(
      [
        { opacity: 0.85, translate: '0 5px' },
        { opacity: 1, translate: '0 0' }
      ],
      { duration: 160, easing: 'ease-out' }
    );
    return () => animation?.cancel();
  }, [activeConversationId, sidebarOpen]);
  const followTail = useRef(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const messageEndRef = useRef<HTMLDivElement | null>(null);
  const listSentinelRef = useRef<HTMLDivElement | null>(null);
  const olderMutation = useLoadOlderMessages(activeConversationId, {
    onSettledScroll: (anchor: { top: number; height: number } | null) => {
      const viewport = scrollRef.current;
      if (viewport && anchor) {
        viewport.scrollTop = anchor.top + viewport.scrollHeight - anchor.height;
      }
    }
  });
  const handleLoadOlder = () => {
    if (!activeConversationId || !detail?.hasMoreOlder || detail.beforeSequence == null) return;
    if (sendMutation.isPending || olderMutation.isPending || contextLoading) return;
    const viewport = scrollRef.current;
    const anchor = viewport ? { top: viewport.scrollTop, height: viewport.scrollHeight } : null;
    setOlderError(null);
    olderMutation.mutate(
      { beforeSequence: detail.beforeSequence, anchor },
      {
        onError: (e: Error) => setOlderError(e instanceof Error ? e.message : t.olderLoadError)
      }
    );
  };

  const appendLocal = (message: ChatMessage) => {
    if (activeConversationId) {
      setLocalMessagesByConversation((prev) => ({
        ...prev,
        [activeConversationId]: [...(prev[activeConversationId] ?? []), message]
      }));
    } else {
      setLocalNewMessages((prev) => [...prev, message]);
    }
    requestAnimationFrame(() => messageEndRef.current?.scrollIntoView({ behavior: 'smooth' }));
  };

  const handleSend = () => {
    if (contextBusy || olderMutation.isPending) return;
    const text = input.trim();
    if (!text || sendMutation.isPending) return;
    const userMessage: ChatMessage = {
      id: `local-user-${Date.now()}`,
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
      skills: [...selectedSkillIds],
      interactionMode
    };
    appendLocal(userMessage);
    setInput('');
    setSendError(null);
    const turnId =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `turn-${Date.now()}`;
    setActiveTurn(turnId);
    sendMutation.mutate(
      {
        message: text,
        conversation_id: activeConversationId,
        workspace_id: workspaceId,
        client_turn_id: turnId,
        interaction_mode: interactionMode,
        selected_skills: [...selectedSkillIds],
        dataset_id: selectedDataset?.dataset_id ?? null,
        language: language === 'zh' ? 'zh-CN' : 'en-US'
      },
      {
        onSuccess: (response) => {
          const persistedAfterRead = currentConversationRead();
          const persistedUser = { ...userMessage, persistedAfterRead };
          if (response.workflow) queryClient.setQueryData(workflowQueryKey(response.workflow.workflow_id), response.workflow);
          if (response.workspace_id !== undefined) {
            const nextWorkspaceId = response.workspace_id ?? null;
            setDraftWorkspaceId(nextWorkspaceId);
            if (response.conversation_id)
              queryClient.setQueryData<ConversationDetailState>(
                ['conversation', response.conversation_id],
                (previous) => (previous ? { ...previous, workspaceId: nextWorkspaceId } : previous)
              );
          }
          if (!response.content) {
            setSendError(t.chatSendError);
            return;
          }
          const assistant: ChatMessage = {
            id: `local-assistant-${Date.now()}`,
            persistedAfterRead,
            role: 'assistant',
            content: response.content,
            createdAt: new Date().toISOString(),
            interactionMode: response.interaction_mode ?? interactionMode,
            workflowRecommended: response.workflow_recommended,
            clarificationRequired: response.clarification_required,
            workflowId: response.workflow?.workflow_id,
            workflow: response.workflow ?? null,
            capabilityRouting: response.capability_routing,
            capabilityRecommendation: response.capability_recommendation,
            workspaceEvents: Array.isArray(response.workspace_tool_events)
              ? response.workspace_tool_events
              : undefined
          };
          if (response.conversation_id && response.conversation_id !== activeConversationId) {
            const pending = [persistedUser, assistant];
            setLocalMessagesByConversation((prev) => ({
              ...prev,
              [response.conversation_id as string]: [
                ...(prev[response.conversation_id as string] ?? []),
                ...pending
              ]
            }));
            setLocalNewMessages([]);
            ui.selectConversation(response.conversation_id);
          } else if (activeConversationId) {
            setLocalMessagesByConversation(previous => ({
              ...previous,
              [activeConversationId]: [
                ...(previous[activeConversationId] ?? []).map(message =>
                  message.id === userMessage.id ? persistedUser : message),
                assistant,
              ],
            }));
          } else {
            setLocalNewMessages([persistedUser, assistant]);
          }
          if (response.conversation_id)
            void queryClient.invalidateQueries({ queryKey: ['conversation', response.conversation_id] });
        },
        onError: (e) =>
          setSendError(
            e instanceof ApiError
              ? e.message || t.chatSendError
              : e instanceof Error
                ? e.message || t.chatSendError
                : t.chatSendError
          ),
        onSettled: () => {
          setActiveTurn(null);
        }
      }
    );
  };
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      handleSend();
    }
  };
  useEffect(() => {
    const sentinel = listSentinelRef.current;
    if (!sentinel || typeof IntersectionObserver === 'undefined') return;
    if (!listQuery.hasNextPage || listQuery.isFetchingNextPage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) void listQuery.fetchNextPage();
      },
      { rootMargin: '0px 0px 80px 0px' }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listQuery.hasNextPage, listQuery.isFetchingNextPage, listItems.length]);
  const latestMessageId = mergedMessages.at(-1)?.id;
  const scrollScope = activeConversationId ?? 'new-conversation';
  const initializedScrollScope = useRef<string | null>(null);
  useLayoutEffect(() => {
    if (contextLoading) return;
    const viewport = scrollRef.current;
    if (initializedScrollScope.current !== scrollScope) {
      initializedScrollScope.current = scrollScope;
      followTail.current = true;
    }
    // Opening history must jump directly to the latest page: smooth scrolling
    // from the top can otherwise trigger eager loading of every older page.
    // Prepending history and editing parameters leave latestMessageId unchanged.
    if (followTail.current && viewport) viewport.scrollTop = viewport.scrollHeight;
  }, [scrollScope, contextLoading, latestMessageId]);
  const todayCount = listItems.length;
  const activeTitle = detail?.title ?? t.newConversation;
  const contextPanelMeta: Record<RailDomain, { title: string; subtitle?: string }> = {
    conversations: {
      title: t.chatHistory,
      subtitle: t.chatsToday.replace('{{count}}', String(todayCount))
    },
    skills: { title: t.skills, subtitle: String(skills.length) },
    datasets: { title: t.datasetPickerTitle, subtitle: t.datasetPickerSubtitle },
    workspace: { title: t.workspaceTitle, subtitle: t.workspaceHint },
    storage: { title: t.storageTitle, subtitle: t.storageDescription }
  };
  // A rail click both selects the domain and reveals its context panel beside
  // the rail, so the icon -> panel relationship is always demonstrated. The
  // navbar's existing open control and resource buttons share the same state.
  const handleRailDomain = (domain: RailDomain) => {
    setSidebarView(domain);
    setSidebarOpen(true);
  };
  const sectionTabs: TabItem<'history' | 'archived'>[] = [
    { value: 'history', label: t.chatHistory },
    { value: 'archived', label: t.archivedChats }
  ];
  return (
    <>
      <NeuroSplash />
      <div className="flex h-dvh overflow-hidden bg-canvas text-ink">
        <AppRail
          t={t}
          domain={sidebarView}
          datasetCount={selectedDataset ? 1 : 0}
          onDomainChange={handleRailDomain}
          onOpenDatasets={openDatasetPicker}
          onOpenWorkspace={() => setWorkspaceOpen(true)}
          onOpenStorage={() => setStorageOpen(true)}
        />
        {sidebarOpen && <button aria-label={t.closeSidebar} className="fixed inset-0 z-20 bg-black/20 lg:hidden" onClick={() => setSidebarOpen(false)} />}
        {sidebarOpen && (
          <aside className="max-lg:fixed max-lg:inset-y-0 max-lg:left-14 max-lg:z-30 flex w-72 max-w-[80vw] shrink-0 flex-col overflow-hidden border-r border-line bg-panel">
            <ContextPanelHeader
              title={contextPanelMeta[sidebarView].title}
              subtitle={contextPanelMeta[sidebarView].subtitle}
              t={t}
              onClose={() => setSidebarOpen(false)}
            />
            {sidebarView === 'conversations' ? (
              <>
                <div className="shrink-0 space-y-2 px-3 pt-3">
                  <div className="flex items-center justify-end gap-2">
                    <Button variant="primary" size="sm" disabled={navigationBusy || olderMutation.isPending} onClick={handleNew}>
                      <Plus aria-hidden="true" />
                      {t.newChat}
                    </Button>
                  </div>
                  <ConversationSearch value={conversationSearch} onChange={setConversationSearch} />
                  <Tabs
                    items={sectionTabs}
                    value={chatSection}
                    onChange={setChatSection}
                    label={t.chatHistory}
                  />
                </div>
                <div
                  key={chatSection}
                  className="view-enter min-h-0 flex-1 overflow-y-auto px-3 pb-3"
                >
                  {ui.actionError && (
                    <p role="alert" className="px-2 pt-2 text-meta text-danger">
                      {ui.actionError}
                    </p>
                  )}
                  {listQuery.isPending ? (
                    <p className="px-2 py-6 text-center text-meta text-muted">
                      {t.loadingConversations}
                    </p>
                  ) : listQuery.isError ? (
                    <div className="px-2 py-6 text-center">
                      <p role="alert" className="text-meta text-danger">
                        {t.conversationsLoadError}
                      </p>
                      <Button
                        size="sm"
                        className="mt-2"
                        loading={listQuery.isFetching}
                        onClick={() => void listQuery.refetch()}
                      >
                        {t.retry}
                      </Button>
                    </div>
                  ) : listItems.length === 0 ? (
                    <p className="px-2 py-6 text-center text-meta text-muted">
                      {debouncedSearch.trim()
                        ? t.noMatchingConversations
                        : chatSection === 'archived'
                          ? t.noArchivedConversations
                          : t.noConversations}
                    </p>
                  ) : (
                    <div className="space-y-1 pt-3">
                      {listItems.map((item) => (
                        <ConversationRow
                          key={item.conversation_id}
                          conversation={item}
                          isActive={item.conversation_id === activeConversationId}
                          isMenuOpen={ui.openMenuId === item.conversation_id}
                          isRenaming={ui.renamingId === item.conversation_id}
                          renameValue={ui.renameValue}
                          isArchivedView={chatSection === 'archived'}
                          disabled={navigationBusy || olderMutation.isPending}
                          pendingDelete={ui.pendingDeleteId === item.conversation_id}
                          t={t}
                          onSelect={() => handleSelect(item.conversation_id)}
                          onToggleMenu={() =>
                            ui.setOpenMenuId(
                              ui.openMenuId === item.conversation_id ? null : item.conversation_id
                            )
                          }
                          onCloseMenu={() => ui.setOpenMenuId(null)}
                          onStartRename={() => ui.startRename(item.conversation_id, item.title)}
                          onRenameChange={ui.setRenameValue}
                          onCommitRename={() => handleCommitRename(item.conversation_id)}
                          onCancelRename={() => ui.cancelRename()}
                          onArchive={() => handleArchive(item.conversation_id, true)}
                          onUnarchive={() => handleArchive(item.conversation_id, false)}
                          onDelete={() => ui.requestDelete(item.conversation_id)}
                          onCancelDelete={() => ui.cancelDelete()}
                          onConfirmDelete={() => handleConfirmDelete(item.conversation_id)}
                        />
                      ))}
                      <div ref={listSentinelRef} />
                      {listQuery.isFetchingNextPage && (
                        <p className="px-2 py-3 text-center text-meta text-muted">
                          {t.loadingConversations}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </>
            ) : sidebarView === 'skills' ? (
              <div className="view-enter min-h-0 flex-1 overflow-y-auto px-3 py-3">
                <SkillList selectedSkillIds={selectedSkillIds} disabled={contextBusy || olderMutation.isPending}
                  onAdd={addSkill} onRemove={removeSkill} onDetails={setViewedSkill} onClear={clearSkills}/>
                {skillsStats && (
                  <div className="mt-3 border-t border-line pt-2">
                    <p className="px-1 text-meta text-subtle">
                      {t.skillCatalogStats.replace('{{total}}', String(skillsStats.total))}
                      {skillsStats.capability_catalog
                        ? ` · ${t.skillCatalogMethods.replace('{{count}}', String(skillsStats.capability_catalog.methods))}`
                        : ''}
                    </p>
                  </div>
                )}
              </div>
            ) : sidebarView === 'datasets' ? (
              <DatasetContextPanel onOpenFull={openDatasetPicker} onChoose={handleDatasetSelect}
                disabled={datasetDisabled} notice={datasetNotice}
                onBrowse={selectedDataset ? () => setDatasetFilesOpen(true) : undefined} />
            ) : sidebarView === 'workspace' ? (
              <WorkspaceContextPanel workspaceId={workspaceId} onOpenFull={() => setWorkspaceOpen(true)} />
            ) : (
              <StorageContextPanel onOpenFull={() => setStorageOpen(true)} />
            )}
          </aside>
        )}
        <main ref={mainRef} className="flex min-w-0 flex-1 flex-col">
          <ChatHeader
            workspaceId={workspaceId}
            onOpenWorkspace={() => setWorkspaceOpen(true)}
            t={t}
            title={activeTitle}
            domainLabel={sidebarView === 'skills' ? t.skills : sidebarView === 'datasets' ? t.datasetPickerTitle : sidebarView === 'workspace' ? t.workspaceTitle : sidebarView === 'storage' ? t.storageTitle : t.conversations}
            sidebarOpen={sidebarOpen}
            darkMode={darkMode}
            datasetLabel={selectedDataset ? selectedDataset.display_name : null}
            datasetCount={selectedDataset ? 1 : 0}
            datasetDisabled={datasetDisabled}
            datasetNotice={datasetNotice}
            onBrowseDataset={selectedDataset ? () => setDatasetFilesOpen(true) : undefined}
            skillLabel={selectedSkills.length > 0 ? selectedSkillNames : null}
            skillCount={selectedSkills.length}
            onOpenSidebar={() => setSidebarOpen(true)}
            onOpenDatasets={openDatasetPicker}
            onToggleTheme={toggleTheme}
          />
          {contextLoading && (detailQuery.isError || workflowQuery.isError) &&
            <div role="alert" className="px-4 py-2 text-meta text-danger">{t.conversationsLoadError}
              <Button size="sm" onClick={() => { void detailQuery.refetch(); if (activeWorkflowId) void workflowQuery.refetch(); }}>{t.retry}</Button>
            </div>}
          <MessageArea
            key={scrollScope}
            activeWorkflowId={activeWorkflowId}
            activeWorkflow={activeWorkflow}
            t={t}
            messages={mergedMessages}
            activeTask={null}
            sending={sendMutation.isPending}
            controlsDisabled={contextBusy}
            loadingOlder={olderMutation.isPending}
            hasOlder={Boolean(detail?.hasMoreOlder)}
            olderError={olderError}
            sendError={sendError ?? (detailQuery.isError ? t.conversationsLoadError : null)}
            selectedLabel={selectedSkills.length > 0 ? selectedSkillNames : null}
            selectedCount={selectedSkills.length}
            liveWorkspaceEvents={liveWorkspaceEvents}
            onLoadOlder={handleLoadOlder}
            onNearBottomChange={near => { followTail.current = near; }}
            scrollRef={scrollRef}
            bottomRef={messageEndRef}
          />
          <MessageComposer
            t={t}
            value={input}
            sending={contextBusy || olderMutation.isPending}
            mode={interactionMode}
            selectedSkills={selectedSkills.map(skill => ({id:skill.name,label:skill.display_name || skill.name}))}
            onRemoveSkill={removeSkill}
            onViewSkill={viewSkill}
            onChange={setInput}
            onKeyDown={handleKeyDown}
            onSend={handleSend}
            onModeChange={setInteractionMode}
            onClearSkills={clearSkills}
          />
        </main>
      </div>
      {datasetPickerOpen && <DatasetPicker onSelect={handleDatasetSelect} onClose={() => setDatasetPickerOpen(false)} />}
      {storageOpen && <StoragePanel onClose={() => setStorageOpen(false)} />}
      {viewedSkill && <SkillDetails key={viewedSkill.name} skill={viewedSkill}
        selected={selectedSkillIds.includes(viewedSkill.name)} disabled={contextBusy || olderMutation.isPending}
        onAdd={() => addSkill(viewedSkill.name)} onRemove={() => removeSkill(viewedSkill.name)} onClose={() => setViewedSkill(null)}/>}
      {datasetFilesOpen && selectedDataset && (
        <DatasetFilesDrawer key={selectedDataset.dataset_id} dataset={selectedDataset}
          onClose={() => setDatasetFilesOpen(false)} />
      )}
      {workspaceOpen && (
        <WorkspacePanel
          key={activeConversationId ?? 'new'}
          workspaceId={workspaceId}
          conversationId={activeConversationId}
          datasetId={selectedDatasetId}
          locked={datasetDisabled}
          onSelect={handleWorkspaceSelect}
          onClose={() => setWorkspaceOpen(false)}
        />
      )}
    </>
  );
}

export default App;
