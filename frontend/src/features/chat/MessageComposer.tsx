import { Send } from 'lucide-react';
import { Badge } from '../../ui/Badge';
import { Button } from '../../ui/Button';
import { IconButton } from '../../ui/IconButton';
import { Tabs } from '../../ui/Tabs';
import type { TabItem } from '../../ui/Tabs';
import type { InteractionMode } from '../conversations/conversationTypes';
import type { TranslationKeys } from '../../types/i18n';

type MessageComposerProps = {
  t: TranslationKeys;
  value: string;
  sending: boolean;
  mode: InteractionMode;
  selectedLabel: string | null;
  selectedCount: number;
  onChange: (value: string) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
  onModeChange: (mode: InteractionMode) => void;
  onClearSkills: () => void;
};

export function MessageComposer({
  t,
  value,
  sending,
  mode,
  selectedLabel,
  selectedCount,
  onChange,
  onKeyDown,
  onSend,
  onModeChange,
  onClearSkills
}: MessageComposerProps) {
  const modes: TabItem<InteractionMode>[] = [
    { value: 'chat', label: t.chatMode },
    { value: 'task', label: t.taskMode }
  ];

  return (
    <div className="shrink-0 border-t border-line bg-canvas px-4 pb-4 pt-3 sm:px-5">
      <div className="mx-auto w-full max-w-3xl">
        <Tabs
          items={modes}
          value={mode}
          onChange={onModeChange}
          label={t.interactionMode}
          variant="chip"
          disabled={sending}
          className="mb-2"
        />
        {selectedCount > 0 && selectedLabel && (
          <div className="mb-2 flex items-center gap-2 text-meta text-muted">
            <span className="shrink-0">
              {selectedCount > 1
                ? t.usingSkills.replace('{{count}}', String(selectedCount))
                : t.usingSkill}
            </span>

            <Badge tone="neutral" className="min-w-0 flex-1">
              <span className="min-w-0 truncate">{selectedLabel}</span>
            </Badge>

            <Button variant="ghost" size="sm" onClick={onClearSkills}>
              {t.clearSelectedSkills}
            </Button>
          </div>
        )}

        <div className="focus-ring flex items-end gap-2 rounded-card border border-line bg-well p-2 transition-control">
          <textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t.messagePlaceholder}
            aria-label={t.messagePlaceholder}
            rows={1}
            disabled={sending}
            className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-body text-ink outline-none placeholder:text-subtle disabled:cursor-not-allowed"
          />

          <IconButton
            label={t.sendMessage}
            icon={<Send />}
            variant="solid"
            size="lg"
            onClick={onSend}
            disabled={!value.trim() || sending}
          />
        </div>

        <p className="mt-2 text-center text-meta text-subtle">{t.backendNotice}</p>
      </div>
    </div>
  );
}
