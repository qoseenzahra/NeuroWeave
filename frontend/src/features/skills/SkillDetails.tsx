import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileText, Plus, Minus } from 'lucide-react';
import { fetchSkill } from './skillsApi';
import type { Skill } from './skillsApi';
import { useLanguageStore } from '../../stores/languageStore';
import { getTranslations } from '../../lib/i18n';
import { Dialog } from '../../ui/Dialog';
import { Button } from '../../ui/Button';
import { Tabs } from '../../ui/Tabs';

export function SkillDetails({ skill, selected, disabled, onAdd, onRemove, onClose }: {
  skill: Skill; selected: boolean; disabled: boolean;
  onAdd: () => void; onRemove: () => void; onClose: () => void;
}) {
  const t = getTranslations(useLanguageStore(s => s.language));
  const [tab, setTab] = useState<'instructions' | 'files'>('instructions');
  // Fetch the full document only when its dialog is opened, never with the catalog.
  const query = useQuery({ queryKey: ['skill-detail', skill.name],
    queryFn: ({ signal }) => fetchSkill(skill.name, signal), staleTime: 60_000, retry: 1 });
  const details = query.data;
  return <Dialog title={skill.display_name || skill.name} description={t.skillDetailsTitle}
    closeLabel={t.workspaceClose} onClose={onClose} size="xl"
    footer={<>
      <span className="mr-auto text-meta text-muted">{selected ? t.skillAdded : t.skillSelectionHint}</span>
      <Button disabled={disabled} onClick={selected ? onRemove : onAdd}>
        {selected ? <Minus aria-hidden="true" /> : <Plus aria-hidden="true" />}
        {selected ? t.skillRemove : t.skillAdd}
      </Button>
    </>}>
    <p className="whitespace-pre-wrap break-words leading-6">{skill.description}</p>
    <dl className="my-4 grid grid-cols-1 gap-3 text-meta sm:grid-cols-2">
      {[[t.skillIdentifier, skill.name], [t.skillSource, skill.source], [t.skillType, skill.skill_type],
        [t.skillRuntime, skill.runtime], [t.skillDependencies, skill.dependencies?.join(', ') || t.skillNone],
        [t.skillComplementary, details?.complementary_skills?.join(', ') || t.skillNone]].map(([label, value]) =>
        <div key={label} className="min-w-0"><dt className="text-subtle">{label}</dt><dd className="mt-1 break-words">{value || '—'}</dd></div>)}
    </dl>
    {!!(details ?? skill).runtime_reasons?.length && <ul className="mb-4 space-y-1 rounded-control bg-warning-quiet p-3 text-meta text-warning">
      {(details ?? skill).runtime_reasons!.map(reason => <li key={reason}>{reason}</li>)}
    </ul>}
    <Tabs label={t.skillDetailsTitle} value={tab} onChange={setTab} items={[
      {value:'instructions',label:t.skillInstructions}, {value:'files',label:t.skillFiles,badge:details?.files.length}
    ]} />
    {query.isPending && <p role="status" className="py-4 text-muted">{t.loadingSkills}</p>}
    {query.isError && <div role="alert" className="py-4 text-danger">
      <p>{query.error.message}</p><Button onClick={() => void query.refetch()} loading={query.isFetching}>{t.retry}</Button>
    </div>}
    {details && (tab === 'instructions'
      // Render source as text: Skill documents may contain HTML or executable examples.
      ? <pre className="mt-3 whitespace-pre-wrap break-words rounded-control border border-line bg-well p-4 font-mono text-meta leading-6">{details.instructions || t.skillNoInstructions}</pre>
      : <ul className="mt-3 space-y-2">{details.files.map(file => <li key={file} className="flex min-w-0 items-start gap-2 text-meta">
        <FileText className="mt-0.5 size-4 shrink-0" aria-hidden="true"/><code className="break-all">{file}</code>
      </li>)}</ul>)}
  </Dialog>;
}
