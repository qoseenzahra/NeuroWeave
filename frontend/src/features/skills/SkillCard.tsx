import { BarChart3, FileSearch, Image as ImageIcon, Scan } from 'lucide-react';
import type { Skill } from './skillsApi';
import { useLanguageStore } from '../../stores/languageStore';
import { getTranslations } from '../../lib/i18n';
import { cx } from '../../ui/cx';
import { Button } from '../../ui/Button';

type SkillCardProps = {
  skill: Skill;
  selected: boolean;
  onDetails: () => void;
  onAdd: () => void;
  onRemove: () => void;
  disabled?: boolean;
};

function kindForSkill(skill: Skill): 'image' | 'report' | 'data' | 'default' {
  const kind = skill.skill_type.toLowerCase();
  if (kind.includes('image')) return 'image';
  if (kind.includes('report')) return 'report';
  if (kind.includes('data') || kind.includes('table') || kind.includes('clean')) return 'data';
  return 'default';
}

export function SkillCard({ skill, selected, onDetails, onAdd, onRemove, disabled }: SkillCardProps) {
  const language = useLanguageStore((state) => state.language);
  const t = getTranslations(language);

  // Summaries describe a Skill; its stable name is the list heading.
  const title = skill.display_name.trim() || skill.name;
  const kind = kindForSkill(skill);
  // Catalog status describes the imported definition, not server readiness.
  // Older backends without runtime evidence must never imply executability.
  const state = skill.execution_state;
  const runtimeLabel = state === 'ready'
    ? (skill.ready_runner_count == null ? t.skillRuntimeReady
      : t.skillRuntimeReadyCount.replace('{{count}}', String(skill.ready_runner_count)))
    : state === 'needs_environment' ? t.skillRuntimeMissing
      : state === 'planning' ? t.skillRuntimePlanning : t.skillRuntimeUnknown;
  const runtimeReasons = skill.runtime_reasons?.filter(Boolean).join('\n');

  return (
    <article>
    <button
      type="button"
      onClick={onDetails}
      aria-label={`${t.skillViewDetails}: ${title}`}
      title={runtimeReasons || runtimeLabel}
      className={cx(
        'w-full rounded-card border p-3 text-left transition-control focus-ring-inset',
        selected ? 'border-line-strong bg-raised' : 'border-transparent hover:bg-hover'
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cx(
            'flex size-8 shrink-0 items-center justify-center rounded-control [&_svg]:size-4',
            selected ? 'bg-accent-solid text-on-accent' : 'bg-well text-muted'
          )}
        >
          {kind === 'image' ? (
            <ImageIcon />
          ) : kind === 'report' ? (
            <FileSearch />
          ) : kind === 'data' ? (
            <BarChart3 />
          ) : (
            <Scan />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p title={title} className="min-w-0 flex-1 truncate text-body font-medium">
              {title}
            </p>

            <span
              role="img"
              aria-label={runtimeLabel}
              title={runtimeLabel}
              className={cx(
                'size-1.5 shrink-0 rounded-full',
                state === 'ready' ? 'bg-success' : state === 'needs_environment'
                  ? 'bg-warning' : state === 'planning' ? 'bg-accent-solid' : 'bg-line-strong'
              )}
            />
          </div>

          <p className="mt-1 line-clamp-2 text-meta leading-5 text-muted">{skill.description}</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-micro">
            <span className={cx('rounded-chip px-1.5 py-0.5', state === 'ready'
              ? 'bg-success-quiet text-success' : state === 'needs_environment'
                ? 'bg-warning-quiet text-warning' : 'bg-well text-muted')}>{runtimeLabel}</span>
            {state && <span className="rounded-chip border border-line px-1.5 py-0.5 text-muted">
              {state === 'ready' ? 'Runner' : state === 'needs_environment' ? t.skillMissingDependencies
                : skill.structure_mode === 'planning' ? t.skillPlanningStructure : t.skillAdvisory}
            </span>}
          </div>
          {runtimeReasons && <p className="mt-1 line-clamp-2 break-words text-meta text-warning" title={runtimeReasons}>
            {runtimeReasons}
          </p>}
        </div>
      </div>
    </button>
    <div className="flex flex-wrap items-center justify-between gap-2 px-3 pb-3">
      <span className="text-micro text-subtle">{selected ? t.skillAdded : t.skillViewDetails}</span>
      <Button size="sm" disabled={disabled} onClick={selected ? onRemove : onAdd}
        aria-label={`${selected ? t.skillRemove : t.skillAdd}: ${title}`}>
        {selected ? t.skillRemove : t.skillAdd}
      </Button>
    </div>
    </article>
  );
}
