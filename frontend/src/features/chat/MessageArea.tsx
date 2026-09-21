import { useRef } from 'react';
import { MessageSquare, ListTree } from 'lucide-react';
import type { ChatMessage } from './chatMessages';
import type { AgentTask } from '../../types/agent';
import type { TranslationKeys } from '../../types/i18n';
import { Button } from '../../ui/Button';
import { cx } from '../../ui/cx';
import { TaskExecution } from '../tasks/TaskExecution';
import { WorkflowCard } from '../workflows/WorkflowCard';
import { CapabilityRecommendationCard } from '../workflows/CapabilityRecommendationCard';
import { WorkspaceTimeline } from '../workspace/WorkspaceTimeline';
import type { WorkspaceEvent } from '../workspace/workspaceTypes';

type MessageAreaProps = {
  t: TranslationKeys;
  messages: ChatMessage[];
  activeWorkflowId: string | null;
  activeWorkflow: ChatMessage['workflow'];
  activeTask: AgentTask | null;
  sending: boolean;
  controlsDisabled?: boolean;
  loadingOlder: boolean;
  hasOlder: boolean;
  olderError: string | null;
  sendError: string | null;
  selectedLabel: string | null;
  selectedCount: number;
  liveWorkspaceEvents?: WorkspaceEvent[];
  onLoadOlder: () => void;
  onNearBottomChange?: (near: boolean) => void;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  bottomRef: React.RefObject<HTMLDivElement | null>;
};

export function MessageArea({
  t,
  messages,
  activeWorkflowId,
  activeWorkflow,
  activeTask,
  sending,
  controlsDisabled,
  loadingOlder,
  hasOlder,
  olderError,
  sendError,
  selectedLabel,
  selectedCount,
  liveWorkspaceEvents,
  onLoadOlder,
  onNearBottomChange,
  scrollRef,
  bottomRef
}: MessageAreaProps) {
  const previousScrollTop = useRef(0);
  return (
    <div
      ref={scrollRef}
      onScroll={(event) => {
        const el = event.currentTarget;
        const scrollingUp = el.scrollTop < previousScrollTop.current;
        previousScrollTop.current = el.scrollTop;
        onNearBottomChange?.(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
        if (scrollingUp && el.scrollTop < 60 && hasOlder && !loadingOlder && !sending) {
          onLoadOlder();
        }
      }}
      className="min-h-0 flex-1 overflow-y-auto"
    >
      <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
        {sendError && <p role="alert" className="text-meta text-danger">{sendError}</p>}
        {activeTask && <TaskExecution task={activeTask} />}

        {messages.length === 0 && !activeWorkflowId ? (
          <div className="flex min-h-[50vh] flex-col items-center justify-center px-4 text-center">
            <div className="mx-auto mb-5 flex size-12 items-center justify-center rounded-panel bg-well text-muted [&_svg]:size-6">
              <MessageSquare />
            </div>

            <h2 className="max-w-md text-display">{t.startConversation}</h2>

            <p className="mt-2 max-w-md text-body text-muted">{t.askAgent}</p>

            {selectedCount > 0 && selectedLabel ? (
              <p className="mt-4 max-w-md truncate text-meta text-ink">
                {selectedCount > 1
                  ? t.usingSkills.replace('{{count}}', String(selectedCount))
                  : `${t.usingSkill} ${selectedLabel}`}
              </p>
            ) : (
              <p className="mt-4 max-w-md text-meta text-subtle">{t.noSkillSelected}</p>
            )}
          </div>
        ) : (
          <div className="space-y-5 sm:space-y-6">
            {hasOlder && (
              <div className="flex justify-center">
                <Button size="sm" loading={loadingOlder} disabled={controlsDisabled || sending} onClick={onLoadOlder}>
                  {loadingOlder ? t.loadingOlder : t.loadOlder}
                </Button>
              </div>
            )}
            {olderError && (
              <p role="alert" className="text-center text-meta text-danger">
                {olderError}
              </p>
            )}
            {messages.map((message) => {
              const workflowId = message.workflow?.workflow_id ?? message.workflowId;
              return (
                <div
                  key={message.id}
                  className={`flex flex-col ${
                    message.role === 'user' ? 'items-end' : 'items-start'
                  }`}
                >
                  <div
                    className={cx(
                      'min-w-0 max-w-full sm:max-w-[85%] break-words rounded-card px-4 py-3',
                      message.role === 'user'
                        ? 'bg-accent-solid text-on-accent'
                        : 'bg-well text-ink'
                    )}
                  >
                    <p className="whitespace-pre-wrap text-body leading-6">{message.content}</p>
                  </div>
                  {message.role === 'assistant' && workflowId && (
                    <div className="w-full">
                      <WorkflowCard
                        workflowId={workflowId}
                        initialWorkflow={message.workflow ?? null}
                        deferred={workflowId !== activeWorkflowId && !message.workflow}
                        disabled={controlsDisabled || sending}
                      />
                    </div>
                  )}

                  {/* Capability routing trace */}
                  {message.capabilityRouting && (
                    <div className="mt-3 inline-flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-chip border border-upstream-line bg-upstream-quiet px-2 py-1 text-micro text-upstream">
                      <ListTree className="size-3 shrink-0" aria-hidden="true" />
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

                  {message.role === 'assistant' && message.interactionMode === 'task' &&
                    message.workflowRecommended === false && !message.capabilityRecommendation && !workflowId && (
                      <p className="mt-3 inline-flex items-center gap-1.5 rounded-chip border border-line bg-well px-2 py-1 text-meta text-muted">
                        <MessageSquare className="size-3 shrink-0" aria-hidden="true" />
                        {message.clarificationRequired ? t.chatNeedsClarification : t.chatNoWorkflowNeeded}
                      </p>
                    )}

                  {/* Capability recommendation card */}
                  {message.capabilityRecommendation && (
                    <CapabilityRecommendationCard
                      recommendation={message.capabilityRecommendation}
                    />
                  )}

                  {/* Workspace tool events timeline */}
                  {Boolean(message.workspaceEvents?.length) && (
                    <WorkspaceTimeline events={message.workspaceEvents ?? []} />
                  )}
                </div>
              );
            })}

            {sending && (
              <div className="flex justify-start">
                <div role="status" className="rounded-card bg-well px-4 py-3">
                  <span className="sr-only">{t.running}</span>
                  <div className="flex items-center gap-1" aria-hidden="true">
                    <span className="size-2 animate-bounce rounded-full bg-subtle" />
                    <span
                      className="size-2 animate-bounce rounded-full bg-subtle"
                      style={{ animationDelay: '120ms' }}
                    />
                    <span
                      className="size-2 animate-bounce rounded-full bg-subtle"
                      style={{ animationDelay: '240ms' }}
                    />
                  </div>
                </div>
              </div>
            )}
            {sending && liveWorkspaceEvents && liveWorkspaceEvents.length > 0 && (
              <WorkspaceTimeline events={liveWorkspaceEvents} />
            )}
            {activeWorkflowId &&
              !messages.some(
                (message) =>
                  (message.workflow?.workflow_id ?? message.workflowId) === activeWorkflowId
              ) && (
                <div className="w-full">
                  <p className="mb-2 text-meta text-muted">{t.workflowCurrentRetained}</p>
                  <WorkflowCard
                    workflowId={activeWorkflowId}
                    initialWorkflow={activeWorkflow ?? null}
                    disabled={controlsDisabled || sending}
                  />
                </div>
              )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}
