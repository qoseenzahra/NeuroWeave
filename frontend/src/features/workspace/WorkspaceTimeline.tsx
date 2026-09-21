import { useLanguageStore } from '../../stores/languageStore';
import { getTranslations } from '../../lib/i18n';
import type { TranslationKeys } from '../../types/i18n';
import type { WorkspaceEvent } from './workspaceTypes';
import { WorkspaceConfirmation } from './WorkspaceConfirmation';

const TOOL_KEYS: Record<string, keyof TranslationKeys> = {
  list_workspace_directory: 'workspaceToolList',
  inspect_workspace_path: 'workspaceToolInspect',
  search_workspace_files: 'workspaceToolSearch',
  read_workspace_text: 'workspaceToolRead',
  create_workspace_directory: 'workspaceToolMkdir',
  copy_workspace_path: 'workspaceToolCopy',
  move_workspace_path: 'workspaceToolMove',
  rename_workspace_path: 'workspaceToolRename',
  delete_workspace_path: 'workspaceToolDelete'
};

for (const [tool, label] of Object.entries(TOOL_KEYS)) {
  TOOL_KEYS[tool.replace('_workspace_', '_output_')] = label;
  if (/^(list|inspect|search|read)_/.test(tool)) TOOL_KEYS[tool.replace('_workspace_', '_dataset_')] = label;
}

const STATUS_KEYS: Record<string, keyof TranslationKeys> = {
  running: 'workspaceStatusRunning',
  succeeded: 'workspaceStatusSucceeded',
  pending: 'workspaceStatusPending',
  failed: 'workspaceStatusFailed'
};

export function WorkspaceTimeline({
  events,
  conversationId = null
}: {
  events: WorkspaceEvent[];
  conversationId?: string | null;
}) {
  const language = useLanguageStore((s) => s.language);
  const t = getTranslations(language);
  return (
    <div className="min-w-0 space-y-1 text-xs text-muted" aria-live="polite">
      {events.map((event, index) => (
        <div
          key={`${event.time}-${index}`}
          className="min-w-0 rounded-chip border border-line bg-well px-2 py-1.5 "
        >
          <span>
            {event.tool.includes('_dataset_') ? t.datasetFilesTitle + ' · ' : event.tool.includes('_output_') ? t.workspaceTitle + ' · ' : ''}{t[TOOL_KEYS[event.tool]] ?? event.tool} ·{' '}
            {t[STATUS_KEYS[event.status]] ?? event.status}
          </span>
          {event.count != null && (
            <span>{t.workspaceFoundCount.replace('{{count}}', String(event.count))}</span>
          )}
          {typeof event.arguments?.path === 'string' && (
            <code className="ml-2 break-all">{event.arguments.path}</code>
          )}
          {event.error && <p className="break-words text-danger">{event.error}</p>}
          {event.operation && (
            <WorkspaceConfirmation key={event.operation.id} operation={event.operation} conversationId={conversationId} />
          )}
        </div>
      ))}
    </div>
  );
}
