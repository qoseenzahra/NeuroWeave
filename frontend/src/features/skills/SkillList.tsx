import { useState } from 'react';
import { SkillCard } from './SkillCard';
import { SkillSearch } from './SkillSearch';
import { useSkills } from './useSkills';
import type { Skill } from './skillsApi';
import { getTranslations } from '../../lib/i18n';
import { useLanguageStore } from '../../stores/languageStore';
import { Button } from '../../ui/Button';
import { Tabs } from '../../ui/Tabs';
import type { TabItem } from '../../ui/Tabs';

type SkillTab = 'all' | 'neuroclaw' | 'general';

function tabForSkill(skill: Skill): Exclude<SkillTab, 'all'> {
  if (skill.source === 'NeuroClaw') return 'neuroclaw';
  return 'general';
}

export function SkillList({ selectedSkillIds, disabled, onAdd, onRemove, onDetails, onClear }: {
  selectedSkillIds: string[]; disabled: boolean;
  onAdd: (id: string) => void; onRemove: (id: string) => void;
  onDetails: (skill: Skill) => void; onClear: () => void;
}) {
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<SkillTab>('all');

  const language = useLanguageStore((state) => state.language);

  const t = getTranslations(language);
  const skillsQuery = useSkills();
  const skills = skillsQuery.data?.skills ?? [];

  const tabItems: TabItem<SkillTab>[] = [
    { value: 'all', label: t.skillTabAll },
    { value: 'neuroclaw', label: t.skillTabNeuroClaw },
    { value: 'general', label: t.skillTabGeneral }
  ];

  if (skillsQuery.isPending) {
    return <p className="px-2 py-3 text-meta text-muted">{t.loadingSkills}</p>;
  }

  if (skillsQuery.isError) {
    return (
      <div className="px-2 py-3">
        <p role="alert" className="text-meta text-danger">
          {t.skillsLoadError}
        </p>
        <Button
          size="sm"
          className="mt-2"
          loading={skillsQuery.isFetching}
          onClick={() => void skillsQuery.refetch()}
        >
          {t.retry}
        </Button>
      </div>
    );
  }

  const filteredSkills = skills.filter((skill) => {
    if (activeTab !== 'all' && tabForSkill(skill) !== activeTab) {
      return false;
    }

    const query = search.trim().toLowerCase();

    if (!query) {
      return true;
    }

    return [
      skill.name,
      skill.display_name,
      skill.description,
      skill.summary_en,
      skill.summary_zh,
      skill.skill_type
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(query);
  });

  return (
    <div>
      <div className="mb-2">
        <SkillSearch value={search} onChange={setSearch} />
      </div>

      <div className="mb-2 flex min-w-0 flex-wrap items-center gap-2">
        <Tabs
          items={tabItems}
          value={activeTab}
          onChange={setActiveTab}
          label={t.skills}
          className="min-w-0 flex-1"
        />

        {selectedSkillIds.length > 0 && (
          <Button variant="ghost" size="sm" disabled={disabled} onClick={onClear}>
            {t.clearSelectedSkills}
          </Button>
        )}
      </div>

      {filteredSkills.length === 0 ? (
        <p className="px-2 py-3 text-meta text-muted">{t.noSkillsFound}</p>
      ) : (
        /*
         * No remount key on purpose: switching source tabs should filter the
         * list in place rather than replay the entrance animation each time.
         */
        <div className="view-enter space-y-1">
          {filteredSkills.map((skill) => (
            <SkillCard
              key={skill.name}
              skill={skill}
              selected={selectedSkillIds.includes(skill.name)}
              disabled={disabled}
              onDetails={() => onDetails(skill)}
              onAdd={() => onAdd(skill.name)}
              onRemove={() => onRemove(skill.name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
