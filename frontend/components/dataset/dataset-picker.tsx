'use client';

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  Check,
  Database,
  File,
  Folder,
  FolderOpen,
  HardDrive,
  LoaderCircle,
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
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import type { DataRoot, Dataset, DirectoryListing } from '@/lib/dataset';

type DatasetPickerProps = {
  apiBase: string;
  selectedDataset: Dataset | null;
  onSelected: (dataset: Dataset) => void | Promise<void>;
  disabled?: boolean;
  disabledReason?: string;
};

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

async function responseError(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `请求失败（${response.status}）`;
  } catch {
    return `请求失败（${response.status}）`;
  }
}

export function DatasetPicker({ apiBase, selectedDataset, onSelected, disabled = false, disabledReason }: DatasetPickerProps) {
  const [open, setOpen] = useState(false);
  const [roots, setRoots] = useState<DataRoot[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [rootId, setRootId] = useState('');
  const [listing, setListing] = useState<DirectoryListing | null>(null);
  const [pathDraft, setPathDraft] = useState('');
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState<'load' | 'register' | 'inspect' | 'select' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selectionEpoch = useRef(0);
  const disabledRef = useRef(disabled);
  disabledRef.current = disabled;
  useEffect(() => {
    selectionEpoch.current += 1;
    if (disabled) setOpen(false);
    return () => { selectionEpoch.current += 1; };
  }, [disabled]);

  const applySelection = async (dataset: Dataset, epoch: number) => {
    if (disabledRef.current || epoch !== selectionEpoch.current) return;
    await onSelected(dataset);
    setOpen(false);
  };

  const selectRegistered = async (dataset: Dataset) => {
    if (disabledRef.current || busy) return;
    setBusy('select');
    setError(null);
    try {
      await applySelection(dataset, selectionEpoch.current);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '无法更换数据集');
    } finally {
      setBusy(null);
    }
  };

  const currentDataset = useMemo(
    () =>
      datasets.find(
        (dataset) =>
          dataset.root_id === rootId && dataset.relative_path === (listing?.relative_path ?? ''),
      ) ?? null,
    [datasets, listing?.relative_path, rootId],
  );
  const normalizedFilter = filter.trim().toLowerCase();
  const visibleDirectories = useMemo(
    () =>
      (listing?.directories ?? []).filter((directory) =>
        directory.name.toLowerCase().includes(normalizedFilter),
      ),
    [listing?.directories, normalizedFilter],
  );
  const visibleFiles = useMemo(
    () =>
      (listing?.files ?? []).filter((file) =>
        file.name.toLowerCase().includes(normalizedFilter),
      ),
    [listing?.files, normalizedFilter],
  );

  const loadDirectory = useCallback(
    async (nextRootId: string, relativePath = '') => {
      setBusy('load');
      setError(null);
      try {
        const query = new URLSearchParams({ root_id: nextRootId });
        if (relativePath) query.set('relative_path', relativePath);
        const response = await fetch(`${apiBase}/api/datasets/directories?${query}`);
        if (!response.ok) throw new Error(await responseError(response));
        const nextListing = (await response.json()) as DirectoryListing;
        setListing(nextListing);
        setPathDraft(nextListing.relative_path);
        setFilter('');
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : '无法浏览目录');
      } finally {
        setBusy(null);
      }
    },
    [apiBase],
  );

  const loadWorkspace = useCallback(async () => {
    setBusy('load');
    setError(null);
    try {
      const [rootsResponse, datasetsResponse] = await Promise.all([
        fetch(`${apiBase}/api/datasets/roots`),
        fetch(`${apiBase}/api/datasets`),
      ]);
      if (!rootsResponse.ok) throw new Error(await responseError(rootsResponse));
      if (!datasetsResponse.ok) throw new Error(await responseError(datasetsResponse));
      const rootsPayload = (await rootsResponse.json()) as { roots: DataRoot[] };
      const datasetsPayload = (await datasetsResponse.json()) as { datasets: Dataset[] };
      setRoots(rootsPayload.roots);
      setDatasets(datasetsPayload.datasets);
      const initialRoot =
        selectedDataset?.root_id || rootId || rootsPayload.roots.at(0)?.root_id || '';
      setRootId(initialRoot);
      if (initialRoot) {
        await loadDirectory(
          initialRoot,
          selectedDataset?.root_id === initialRoot ? selectedDataset.relative_path : '',
        );
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '无法读取数据目录');
      setBusy(null);
    }
  }, [apiBase, loadDirectory, rootId, selectedDataset]);

  const registerCurrent = async () => {
    if (!listing || disabledRef.current || busy) return;
    const epoch = selectionEpoch.current;
    setBusy('register');
    setError(null);
    try {
      const response = await fetch(`${apiBase}/api/datasets/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          root_id: rootId,
          relative_path: listing.relative_path,
          display_name:
            listing.relative_path.split(/[\\/]/).filter(Boolean).at(-1) ?? listing.root.label,
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const dataset = (await response.json()) as Dataset;
      setDatasets((current) => [
        dataset,
        ...current.filter((item) => item.dataset_id !== dataset.dataset_id),
      ]);
      await applySelection(dataset, epoch);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '数据集登记失败');
    } finally {
      setBusy(null);
    }
  };

  const inspectDataset = async (dataset: Dataset) => {
    if (disabledRef.current || busy) return;
    const epoch = selectionEpoch.current;
    setBusy('inspect');
    setError(null);
    try {
      const response = await fetch(`${apiBase}/api/datasets/${dataset.dataset_id}/inspect`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error(await responseError(response));
      const refreshed = (await response.json()) as Dataset;
      setDatasets((current) =>
        current.map((item) => (item.dataset_id === refreshed.dataset_id ? refreshed : item)),
      );
      await applySelection(refreshed, epoch);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '重新扫描失败');
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog
      onOpenChange={(nextOpen) => {
        if (nextOpen && disabledRef.current) return;
        setOpen(nextOpen);
        if (nextOpen) void loadWorkspace();
      }}
      open={open && !disabled}
    >
      <DialogTrigger disabled={disabled} render={<Button className="gap-2" size="sm" variant="outline" disabled={disabled} title={disabledReason} />}>
        <Database className="size-4" />
        <span className="max-w-40 truncate">
          {selectedDataset?.display_name ?? '选择数据集'}
        </span>
      </DialogTrigger>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-4xl">
        <DialogHeader className="border-b border-slate-200 px-5 py-4">
          <DialogTitle>选择本地数据集</DialogTitle>
          <DialogDescription>
            仅可浏览后端允许的数据根目录。选择后会先扫描元数据，不会修改文件。
          </DialogDescription>
        </DialogHeader>

        <div className="grid auto-rows-max min-h-0 min-w-0 overflow-y-auto md:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <section className="min-h-0 min-w-0 border-b border-slate-200 p-4 md:border-b-0 md:border-r">
            <div className="flex items-center gap-2">
              <NativeSelect
                aria-label="数据根目录"
                className="min-w-0 flex-1"
                onChange={(event) => {
                  const nextRoot = event.target.value;
                  setRootId(nextRoot);
                  void loadDirectory(nextRoot);
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
                disabled={busy !== null || !rootId}
                onClick={() => void loadDirectory(rootId, listing?.relative_path)}
                size="icon-sm"
                variant="outline"
              >
                <RefreshCw className={cn('size-4', busy === 'load' && 'animate-spin')} />
              </Button>
            </div>

            <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
              {listing ? (
                <Breadcrumb>
                  <BreadcrumbList className="flex-wrap wrap-anywhere text-xs">
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
                                    onClick={() => void loadDirectory(rootId, item.relative_path)}
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
                <p className="text-[11px] text-slate-500">正在读取允许的服务器目录…</p>
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
                placeholder="输入相对路径，例如 project/sub-01"
                value={pathDraft}
              />
              <Button disabled={busy !== null || !rootId} size="sm" type="submit" variant="outline">
                转到
              </Button>
            </form>

            <div className="relative mt-2">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
              <Input
                aria-label="筛选当前目录"
                className="h-8 pl-8 text-xs"
                onChange={(event) => setFilter(event.target.value)}
                placeholder="筛选当前目录中的文件夹或文件"
                value={filter}
              />
            </div>

            <ScrollArea className="mt-3 h-60 rounded-lg border border-slate-200 sm:h-[248px]">
              <div className="p-2">
                {listing?.parent_relative_path !== null && listing && (
                  <button
                    className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm text-slate-600 hover:bg-slate-100"
                    onClick={() => void loadDirectory(rootId, listing.parent_relative_path ?? '')}
                    type="button"
                  >
                    <ArrowLeft className="size-4" />
                    返回上级目录
                  </button>
                )}
                {visibleDirectories.map((directory) => (
                  <button
                    className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-800 disabled:cursor-not-allowed disabled:opacity-45"
                    disabled={!directory.readable}
                    key={directory.relative_path}
                    onClick={() => void loadDirectory(rootId, directory.relative_path)}
                    type="button"
                  >
                    <Folder className="size-4 shrink-0 text-blue-500" />
                    <span className="min-w-0 wrap-anywhere">{directory.name}</span>
                  </button>
                ))}
                {visibleFiles.map((file) => (
                  <div
                    className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-slate-500"
                    key={file.relative_path}
                    title="数据集选择器只选择文件夹；单个输入文件请在流程步骤中选择"
                  >
                    <File className="size-3.5 text-slate-400" />
                    <span className="min-w-0 flex-1 truncate">{file.name}</span>
                    <span className="shrink-0 text-[10px] text-slate-400">{formatBytes(file.size_bytes)}</span>
                  </div>
                ))}
                {busy === 'load' && (
                  <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-400">
                    <LoaderCircle className="size-4 animate-spin" />
                    正在读取目录…
                  </div>
                )}
                {busy !== 'load' && visibleDirectories.length === 0 && visibleFiles.length === 0 && (
                  <p className="py-12 text-center text-sm text-slate-400">
                    {normalizedFilter ? '没有匹配的文件夹或文件' : '当前目录为空'}
                  </p>
                )}
              </div>
            </ScrollArea>

            {listing && (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                <span>{listing.directory_count} 个文件夹</span>
                <span>·</span>
                <span>{listing.file_count} 个文件</span>
                {(listing.directories_truncated || listing.files_truncated) && (
                  <Badge className="bg-amber-50 text-amber-700 shadow-none">列表已截断，请筛选或输入路径</Badge>
                )}
              </div>
            )}

            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 text-xs text-slate-500">
                {currentDataset ? '这个目录已经登记，可以直接重新扫描。' : '登记时会执行只读扫描。'}
              </div>
              <Button
                className="shrink-0 gap-2 bg-blue-600 hover:bg-blue-700"
                disabled={!listing || busy !== null}
                onClick={() =>
                  currentDataset
                    ? void inspectDataset(currentDataset)
                    : void registerCurrent()
                }
                size="sm"
              >
                {busy === 'register' || busy === 'inspect' ? (
                  <LoaderCircle className="animate-spin" />
                ) : currentDataset ? (
                  <RefreshCw />
                ) : (
                  <FolderOpen />
                )}
                {currentDataset ? '重新扫描并选择' : '登记并选择此目录'}
              </Button>
            </div>
          </section>

          <section className="min-h-0 min-w-0 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold">已登记数据集</h3>
                <p className="mt-0.5 text-xs text-slate-500">SQLite 中保存的本地引用</p>
              </div>
              <Badge variant="secondary">{datasets.length}</Badge>
            </div>
            <ScrollArea className="h-[260px] sm:h-[375px]">
              <div className="space-y-2 pr-3">
                {datasets.map((dataset) => {
                  const active = selectedDataset?.dataset_id === dataset.dataset_id;
                  return (
                    <button
                      className={cn(
                        'w-full rounded-lg border p-3 text-left transition-colors',
                        active
                          ? 'border-blue-300 bg-blue-50'
                          : 'border-slate-200 bg-white hover:border-blue-200',
                      )}
                      key={dataset.dataset_id}
                      disabled={Boolean(busy)}
                      onClick={() => void selectRegistered(dataset)}
                      type="button"
                    >
                      <div className="flex items-start gap-2">
                        <HardDrive className="mt-0.5 size-4 shrink-0 text-slate-500" />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-2">
                            <span className="min-w-0 wrap-anywhere text-sm font-medium">{dataset.display_name}</span>
                            {active && <Check className="size-3.5 shrink-0 text-blue-700" />}
                          </span>
                          <span className="mt-1 block wrap-anywhere font-mono text-xs text-slate-500">
                            {dataset.relative_path || dataset.absolute_path}
                          </span>
                          <span className="mt-2 flex flex-wrap gap-1">
                            {dataset.inspection.is_bids && <Badge variant="outline">BIDS</Badge>}
                            {dataset.inspection.has_dwi && <Badge variant="outline">DWI</Badge>}
                            {dataset.inspection.has_t1w && <Badge variant="outline">T1w</Badge>}
                            {dataset.inspection.has_fod && <Badge variant="outline">FOD</Badge>}
                            {dataset.inspection.has_five_tt && <Badge variant="outline">5TT</Badge>}
                            <Badge variant="outline">
                              {dataset.inspection.sample_count} 样本
                            </Badge>
                            <Badge variant="outline">
                              {dataset.inspection.file_count} 文件 · {formatBytes(dataset.inspection.total_bytes)}
                            </Badge>
                          </span>
                          {dataset.inspection.warnings.length > 0 && (
                            <span className="mt-2 flex items-start gap-1 wrap-anywhere text-xs leading-4 text-amber-700">
                              <TriangleAlert className="mt-0.5 size-3 shrink-0" />
                              {dataset.inspection.warnings[0]}
                            </span>
                          )}
                        </span>
                      </div>
                    </button>
                  );
                })}
                {datasets.length === 0 && (
                  <div className="rounded-lg border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-400">
                    还没有登记数据集
                  </div>
                )}
              </div>
            </ScrollArea>
          </section>
        </div>

        {error && (
          <Alert className="m-4 mt-0" variant="destructive">
            <TriangleAlert />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </DialogContent>
    </Dialog>
  );
}
