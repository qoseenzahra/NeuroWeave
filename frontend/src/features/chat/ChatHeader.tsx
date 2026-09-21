import { Database, FolderOpen, Menu } from 'lucide-react';
import { BackendStatusDot } from '../../components/BackendStatusDot';
import { LanguageSelector } from '../../components/LanguageSelector';
import { ThemeSwitch } from '../../components/ThemeSwitch';
import { Badge } from '../../ui/Badge';
import { Button } from '../../ui/Button';
import { IconButton } from '../../ui/IconButton';
import type { TranslationKeys } from '../../types/i18n';

type ChatHeaderProps = {
  t: TranslationKeys;
  title: string;
  /** Domain label shown above the title, e.g. "Conversations". */
  domainLabel: string;
  sidebarOpen: boolean;
  darkMode: boolean;
  datasetLabel: string | null;
  datasetCount: number;
  datasetDisabled?: boolean;
  datasetNotice?: string | null;
  onBrowseDataset?: () => void;
  skillLabel: string | null;
  skillCount: number;
  onOpenSidebar: () => void;
  workspaceId: string | null;
  onOpenWorkspace: () => void;
  onOpenDatasets: () => void;
  onToggleTheme: () => void;
};

export function ChatHeader({
  t,
  title,
  domainLabel,
  sidebarOpen,
  darkMode,
  datasetLabel,
  datasetCount,
  datasetDisabled,
  datasetNotice,
  onBrowseDataset,
  skillLabel,
  skillCount,
  onOpenSidebar,
  workspaceId,
  onOpenWorkspace,
  onOpenDatasets,
  onToggleTheme
}: ChatHeaderProps) {
  return (
    <header className="flex min-h-16 shrink-0 flex-wrap items-center justify-between gap-3 border-b border-line bg-canvas px-4 sm:px-5">
      <div className="flex min-w-0 items-center gap-2">
        {!sidebarOpen && (
          <IconButton label={t.openSidebar} icon={<Menu />} size="lg" onClick={onOpenSidebar} />
        )}

        <div className="flex min-w-0 flex-col justify-center gap-0.5">
          <div className="flex min-w-0 items-center gap-1.5">
            <BackendStatusDot t={t} />
            <p className="truncate text-micro font-medium text-subtle">{domainLabel}</p>
          </div>
          {/*
 Deliberately no trailing chevron: the previous one implied a
 dropdown that did not exist (false affordance in the title area).
 */}
          <h1 className="truncate text-title">{title}</h1>
        </div>
      </div>

      <div className="flex min-w-0 shrink items-center gap-2">
        <div className="hidden min-w-0 items-center gap-2 sm:flex">
          {datasetCount > 0 && datasetLabel ? (
            <Button
              disabled={datasetDisabled} onClick={onOpenDatasets}
              title={datasetNotice ?? datasetLabel}
              size="sm"
              className="max-w-64 lg:max-w-80"
            >
              <Database className="shrink-0" />
              <span className="min-w-0 truncate">{datasetLabel}</span>
            </Button>
          ) : skillCount === 0 ? (
            <span className="truncate rounded-control border border-dashed border-line px-2 py-1 text-meta text-subtle">
              {t.noSkillSelected}
            </span>
          ) : (
            <Badge
              tone="neutral"
              size="md"
              title={skillLabel ?? undefined}
              className="max-w-64 lg:max-w-80"
            >
              <span className="min-w-0 truncate">{skillLabel}</span>
            </Badge>
          )}
        </div>

        <span className="relative shrink-0">
          <IconButton
            label={datasetLabel ?? t.datasetSelectLocal}
            title={datasetNotice ?? datasetLabel ?? t.datasetSelectLocal}
            icon={<Database />}
            size="lg"
            variant="outline"
            disabled={datasetDisabled} onClick={onOpenDatasets}
          />
          {datasetCount > 0 && (
            /* Redundant for assistive tech - mirrors the visible chip above. */
            <span
              aria-hidden="true"
              className="pointer-events-none absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-pill bg-accent-solid px-1 text-micro font-semibold text-on-accent"
            >
              {datasetCount}
            </span>
          )}
        </span>

        <Button
          onClick={onOpenWorkspace}
          aria-label={workspaceId ? t.workspaceTitle : t.workspaceSelect}
          title={workspaceId ? t.workspaceTitle : t.workspaceSelect}
          size="lg"
        >
          <FolderOpen className="shrink-0" />
          <span className="hidden lg:inline">
            {workspaceId ? t.workspaceTitle : t.workspaceSelect}
          </span>
        </Button>

        {onBrowseDataset && <IconButton label={t.datasetBrowseFiles} icon={<FolderOpen />}
          variant="outline" size="lg" onClick={onBrowseDataset} />}
        <LanguageSelector />

        <ThemeSwitch t={t} darkMode={darkMode} onToggle={onToggleTheme} />
      </div>
    </header>
  );
}
