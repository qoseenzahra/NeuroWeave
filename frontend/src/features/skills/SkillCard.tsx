import { BarChart3, FileSearch, Image as ImageIcon, Scan } from 'lucide-react';
import type { Skill } from './skillsApi';
import { useLanguageStore } from '../../stores/languageStore';
import { getTranslations } from '../../lib/i18n';
import { cx } from '../../ui/cx';

type SkillCardProps = {
  skill: Skill;
  selected: boolean;
  onSelect: () => void;
};

function kindForSkill(skill: Skill): 'image' | 'report' | 'data' | 'default' {
  const kind = skill.skill_type.toLowerCase();
  if (kind.includes('image')) return 'image';
  if (kind.includes('report')) return 'report';
  if (kind.includes('data') || kind.includes('table') || kind.includes('clean')) return 'data';
  return 'default';
}

export function SkillCard({ skill, selected, onSelect }: SkillCardProps) {
  const language = useLanguageStore((state) => state.language);
  const t = getTranslations(language);

  const title =
    language === 'zh'
      ? (skill.summary_zh ?? skill.display_name)
      : (skill.summary_en ?? skill.display_name);
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
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`${selected ? t.deselect : t.select} ${skill.display_name}`}
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
            <p className="min-w-0 flex-1 truncate text-body font-medium">
              {title || skill.display_name || skill.name}
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
  );
}
