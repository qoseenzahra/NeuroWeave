'use client';

import { Fragment, useCallback, useMemo, useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  File,
  Folder,
  FolderOpen,
  LoaderCircle,
  Maximize2,
  Minimize2,
  MoveDiagonal2,
  RefreshCw,
  Search,
  TriangleAlert,
} from 'lucide-react';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { DataRoot, DirectoryListing } from '@/lib/dataset';
import type { Dataset, DatasetPathPreview } from '@/lib/dataset';
import type { InputSlotSpec } from '@/lib/workflow';
import { cn } from '@/lib/utils';
import { responseError } from '@/lib/api-error';

type ArtifactPathPickerProps = {
  apiBase: string;
  disabled: boolean;
  dataset: Dataset | null;
  workspaceRoot?: string | null;
  workflowId: string;
  stepId: string;
  slot: InputSlotSpec;
  onSelected: (rootId: string, relativePath: string) => void;
};

export function ArtifactPathPicker({
  apiBase,
  dataset,
  workspaceRoot,
  disabled,
  onSelected,
  stepId,
  slot,
  workflowId,
}: ArtifactPathPickerProps) {
  const [open, setOpen] = useState(false);
  const [roots, setRoots] = useState<DataRoot[]>([]);
  const [rootId, setRootId] = useState('');
  const [listing, setListing] = useState<DirectoryListing | null>(null);
  const [pathDraft, setPathDraft] = useState('');
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<DatasetPathPreview | null>(null);
  const [expanded, setExpanded] = useState(false);

  const loadDirectory = useCallback(
    async (nextRootId: string, relativePath = '') => {
      setBusy(true);
      setError(null);
      setPreview(null);
      try {
        const query = new URLSearchParams({ root_id: nextRootId });
        if (relativePath) query.set('relative_path', relativePath);
        const response = await fetch(
          `${apiBase}/api/datasets/directories?${query}`,
        );
        if (!response.ok) throw new Error(await responseError(response));
        const nextListing = (await response.json()) as DirectoryListing;
        setListing(nextListing);
        setPathDraft(nextListing.relative_path);
        setFilter('');
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : '无法读取输入目录',
        );
      } finally {
        setBusy(false);
      }
    },
    [apiBase],
  );

  const loadRoots = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/api/datasets/roots`);
      if (!response.ok) throw new Error(await responseError(response));
      const payload = (await response.json()) as { roots: DataRoot[] };
      setRoots(payload.roots);
      const normalize = (path: string) => path.replaceAll('\\', '/').replace(/\/+$/, '');
      const workspacePath = workspaceRoot ? normalize(workspaceRoot) : '';
      const workspaceDataRoot = workspaceRoot ? payload.roots.find(item => {
        const base = normalize(item.path);
        return workspacePath === base || workspacePath.startsWith(`${base}/`);
      }) : undefined;
      const initialRoot =
        dataset?.root_id || workspaceDataRoot?.root_id || rootId || payload.roots.at(0)?.root_id || '';
      setRootId(initialRoot);
      if (initialRoot) {
        const initialPath =
          dataset?.root_id === initialRoot ? dataset.relative_path : workspaceDataRoot?.root_id === initialRoot
            ? workspacePath.slice(normalize(workspaceDataRoot.path).length).replace(/^\//, '') : '';
        await loadDirectory(initialRoot, initialPath);
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '无法读取数据根目录',
      );
      setBusy(false);
    }
  }, [apiBase, dataset, workspaceRoot, loadDirectory, rootId]);

  const choose = async (relativePath: string) => {
    if (!dataset) {
      onSelected(rootId, relativePath);
      setOpen(false);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiBase}/api/workflows/${workflowId}/steps/${stepId}/inputs/${slot.id}/preview`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            root_id: rootId,
            relative_path: relativePath,
          }),
        },
      );
      if (!response.ok) throw new Error(await responseError(response));
      setPreview((await response.json()) as DatasetPathPreview);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : '无法生成样本路径预览',
      );
    } finally {
      setBusy(false);
    }
  };
  const canChooseFolder =
    slot.binding === 'folder' || slot.binding === 'file_bundle';
  const canChooseFile =
    slot.binding === 'file' || slot.binding === 'file_bundle';
  const acceptsFile = (name: string) =>
    slot.formats.length === 0 ||
    slot.formats.some((format) => name.toLowerCase().endsWith(format));
  const normalizedFilter = filter.trim().toLowerCase();
  const visibleDirectories = useMemo(
    () =>
      (listing?.directories ?? []).filter((directory) =>
        directory.name.toLowerCase().includes(normalizedFilter),
      ),
    [listing?.directories, normalizedFilter],
  );
  const visibleFiles = (listing?.files ?? []).filter(
    (file) =>
      acceptsFile(file.name) &&
      file.name.toLowerCase().includes(normalizedFilter),
  );

  return (
    <Dialog
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) setExpanded(false);
        if (nextOpen) {
          setPreview(null);
          void loadRoots();
        }
      }}
      open={open}
    >
      <DialogTrigger
        disabled={disabled}
        render={<Button size="sm" variant="outline" className="gap-1.5" />}
      >
        <FolderOpen className="size-3.5" />
        选择已有路径
      </DialogTrigger>
      <DialogContent
        className={cn(
          'flex min-h-0 min-w-0 max-h-[calc(100dvh-2rem)] max-w-[calc(100vw-2rem)] resize-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none md:resize',
          expanded
            ? 'h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)]'
            : 'h-[86dvh] w-[calc(100vw-2rem)] md:w-[82vw] lg:w-[76vw] lg:max-w-[90rem]',
        )}
      >
        <DialogHeader className="shrink-0 border-b border-slate-200 px-5 py-4 pr-24">
          <DialogTitle>选择：{slot.label}</DialogTitle>
          <DialogDescription>
            {slot.description}{' '}
            {slot.formats.length > 0 ? `支持 ${slot.formats.join('、')}` : ''}
            {dataset ? ` 当前从数据集“${dataset.display_name}”开始浏览。` : ''}
            <span className="mt-1 hidden text-[11px] text-slate-400 md:block">
              可拖动右下角调整窗口大小，或使用右上角按钮最大化。
            </span>
          </DialogDescription>
        </DialogHeader>
        <Button
          aria-label={expanded ? '还原选择窗口' : '最大化选择窗口'}
          className="absolute right-11 top-2"
          onClick={() => setExpanded((value) => !value)}
          size="icon-sm"
          title={expanded ? '还原窗口' : '最大化窗口'}
          variant="ghost"
        >
          {expanded ? (
            <Minimize2 className="size-4" />
          ) : (
            <Maximize2 className="size-4" />
          )}
        </Button>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto p-4">
          <div className="flex items-center gap-2">
            <NativeSelect
              className="min-w-0 flex-1"
              onChange={(event) => {
                setRootId(event.target.value);
                void loadDirectory(event.target.value);
              }}
              value={rootId}
            >
              {roots.map((root) => (
                <NativeSelectOption
                  disabled={!root.readable}
                  key={root.root_id}
                  value={root.root_id}
                >
                  {root.label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <Button
              aria-label="刷新目录"
              disabled={busy || !rootId}
              onClick={() => void loadDirectory(rootId, listing?.relative_path)}
              size="icon-sm"
              variant="outline"
            >
              <RefreshCw className={cn('size-4', busy && 'animate-spin')} />
            </Button>
          </div>
          <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            {listing ? (
              <Breadcrumb>
                <BreadcrumbList className="flex-nowrap overflow-x-auto whitespace-nowrap text-[11px]">
                  {listing.breadcrumbs.map((item, index) => {
                    const current = index === listing.breadcrumbs.length - 1;
                    return (
                      <Fragment key={`${item.relative_path}:${item.label}`}>
                        {index > 0 && <BreadcrumbSeparator />}
                        <BreadcrumbItem>
                          {current ? (
                            <BreadcrumbPage className="font-mono text-[11px]">
                              {item.label}
                            </BreadcrumbPage>
                          ) : (
                            <BreadcrumbLink
                              className="font-mono text-[11px]"
                              render={
                                <button
                                  aria-label={`转到 ${item.label}`}
                                  onClick={() =>
                                    void loadDirectory(
                                      rootId,
                                      item.relative_path,
                                    )
                                  }
                                  type="button"
                                />
                              }
                            >
                              {item.label}
                            </BreadcrumbLink>
                          )}
                        </BreadcrumbItem>
                      </Fragment>
                    );
                  })}
                </BreadcrumbList>
              </Breadcrumb>
            ) : (
              <p className="text-[11px] text-slate-500">
                正在读取允许的服务器目录…
              </p>
            )}
          </div>

          <form
            className="mt-2 flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (rootId) void loadDirectory(rootId, pathDraft);
            }}
          >
            <Input
              aria-label="服务器根目录内的相对路径"
              className="h-8 font-mono text-xs"
              onChange={(event) => setPathDraft(event.target.value)}
              placeholder="输入相对路径后跳转"
              value={pathDraft}
            />
            <Button
              disabled={busy || !rootId}
              size="sm"
              type="submit"
              variant="outline"
            >
              转到
            </Button>
          </form>

          <div className="relative mt-2">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
            <Input
              aria-label="筛选当前目录"
              className="h-8 pl-8 text-xs"
              onChange={(event) => setFilter(event.target.value)}
              placeholder="筛选当前目录"
              value={filter}
            />
          </div>

          <ScrollArea
            className={cn(
              'mt-3 h-48 min-h-32 shrink-0 flex-1 rounded-lg border border-slate-200',
              preview && 'max-h-56',
            )}
            horizontal
          >
            <div className="min-w-full w-max p-2">
              {listing?.parent_relative_path !== null && listing && (
                <button
                  className="flex min-w-full w-max items-center gap-2 whitespace-nowrap rounded-md px-2.5 py-2 text-left text-sm text-slate-600 hover:bg-slate-100"
                  onClick={() =>
                    void loadDirectory(
                      rootId,
                      listing.parent_relative_path ?? '',
                    )
                  }
                  type="button"
                >
                  <ArrowLeft className="size-4" />
                  返回上级目录
                </button>
              )}
              {canChooseFolder && listing && (
                <button
                  className="mb-1 flex min-w-full w-max items-center gap-2 whitespace-nowrap rounded-md border border-blue-100 bg-blue-50 px-2.5 py-2 text-left text-sm text-blue-700 hover:bg-blue-100"
                  onClick={() => void choose(listing.relative_path)}
                  type="button"
                >
                  <FolderOpen className="size-4" />
                  选择当前文件夹
                </button>
              )}
              {visibleDirectories.map((directory) => (
                <button
                  className="flex min-w-full w-max items-center gap-2 whitespace-nowrap rounded-md px-2.5 py-2 text-left text-sm text-slate-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-45"
                  disabled={!directory.readable}
                  key={directory.relative_path}
                  onClick={() =>
                    void loadDirectory(rootId, directory.relative_path)
                  }
                  type="button"
                >
                  <Folder className="size-4 text-blue-500" />
                  <span>{directory.name}</span>
                </button>
              ))}
              {canChooseFile &&
                visibleFiles.map((file) => (
                  <button
                    className="flex min-w-full w-max items-center gap-2 whitespace-nowrap rounded-md px-2.5 py-2 text-left text-sm text-slate-700 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-45"
                    disabled={!file.readable}
                    key={file.relative_path}
                    onClick={() => void choose(file.relative_path)}
                    type="button"
                  >
                    <File className="size-4 text-emerald-600" />
                    <span>{file.name}</span>
                  </button>
                ))}
              {busy && (
                <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-400">
                  <LoaderCircle className="size-4 animate-spin" />
                  正在读取…
                </div>
              )}
              {!busy &&
                visibleDirectories.length === 0 &&
                (!canChooseFile || visibleFiles.length === 0) && (
                  <p className="py-12 text-center text-sm text-slate-400">
                    {normalizedFilter
                      ? '没有匹配的路径'
                      : '当前目录没有可选择的内容'}
                  </p>
                )}
            </div>
          </ScrollArea>
          {listing && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
              <span>{listing.directory_count} 个文件夹</span>
              <span>·</span>
              <span>{listing.file_count} 个文件</span>
              {slot.formats.length > 0 && (
                <span>· 当前仅显示支持的文件格式</span>
              )}
              {(listing.directories_truncated || listing.files_truncated) && (
                <span className="text-amber-700">
                  列表已截断，请筛选或输入相对路径
                </span>
              )}
            </div>
          )}
          {preview && (
            <div className="mt-3 min-w-0 shrink-0 rounded-xl border border-blue-200 bg-blue-50/70 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-blue-950">
                    {preview.binding_mode === 'per_sample'
                      ? '全样本路径规则'
                      : '输入路径预览'}
                  </p>
                  <ScrollArea className="mt-1 max-w-full pb-2" horizontal>
                    <p className="w-max whitespace-nowrap font-mono text-[10px] leading-4 text-blue-700">
                      {preview.path_template || preview.selected_relative_path}
                    </p>
                  </ScrollArea>
                </div>
                <Badge className="bg-white text-blue-700 shadow-none">
                  {preview.coverage.matched}/{preview.coverage.total} 已匹配
                </Badge>
              </div>
              <ScrollArea
                className="mt-2 h-24 rounded-lg border border-blue-100 bg-white/80"
                horizontal
              >
                <div className="min-w-full w-max space-y-1 p-2">
                  {preview.matches.slice(0, 50).map((match) => (
                    <div
                      className="flex min-w-full w-max items-start gap-2 whitespace-nowrap text-[10px]"
                      key={match.sample_id}
                    >
                      {match.status === 'matched' ? (
                        <CheckCircle2 className="mt-0.5 size-3 shrink-0 text-emerald-600" />
                      ) : (
                        <TriangleAlert className="mt-0.5 size-3 shrink-0 text-amber-600" />
                      )}
                      <span className="w-32 shrink-0 overflow-hidden text-ellipsis font-medium text-slate-700">
                        {match.label}
                      </span>
                      <span className="font-mono text-slate-500">
                        {match.relative_path || match.message}
                      </span>
                    </div>
                  ))}
                  {preview.matches.length > 50 && (
                    <p className="pt-1 text-center text-[10px] text-slate-400">
                      其余 {preview.matches.length - 50} 个样本已完成后端验证
                    </p>
                  )}
                </div>
              </ScrollArea>
              {!preview.can_apply && (
                <p className="mt-2 text-[10px] text-amber-700">
                  当前规则存在缺失或格式不匹配，暂不能应用。
                </p>
              )}
              <div className="mt-3 flex flex-wrap justify-end gap-2">
                <Button
                  onClick={() => setPreview(null)}
                  size="sm"
                  variant="ghost"
                >
                  重新选择
                </Button>
                <Button
                  disabled={!preview.can_apply}
                  onClick={() => {
                    onSelected(rootId, preview.selected_relative_path);
                    setOpen(false);
                    setPreview(null);
                  }}
                  size="sm"
                >
                  {preview.binding_mode === 'per_sample'
                    ? `应用到 ${preview.coverage.matched} 个样本`
                    : '确认此输入'}
                </Button>
              </div>
            </div>
          )}
        </div>
        {error && (
          <Alert className="m-4 mt-0 shrink-0" variant="destructive">
            <TriangleAlert />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute bottom-1.5 right-1.5 hidden text-slate-400 md:block"
          title="拖动调整窗口大小"
        >
          <MoveDiagonal2 className="size-4" />
        </div>
      </DialogContent>
    </Dialog>
  );
}
