export type Workspace = {
  id: string;
  name: string;
  root_path: string;
  status: string;
  description: string;
  manageable: boolean;
  permission_reason: string;
};

export type WorkspaceOperation = {
  id: string;
  action: string;
  source: string;
  target: string | null;
  conversation_id: string | null;
  status: string;
  error?: string;
  result?: Record<string, unknown>;
  staging_path?: string;
  request: { permanent?: boolean; overwrite?: boolean; root_path?: string };
};

export type WorkspaceEvent = {
  tool: string;
  status: string;
  count?: number;
  error?: string;
  operation?: WorkspaceOperation;
  arguments?: Record<string, unknown>;
  time?: string;
};

export type FsEntry = {
  name: string;
  path: string;
  relative_path: string;
  type: string;
  size: number;
  modified_at: string;
  permissions: string;
  readable: boolean;
  writable: boolean;
};

export type FsListing = {
  root_path: string;
  path: string;
  relative_path: string;
  items: FsEntry[];
  has_more: boolean;
  next_cursor: string | null;
};

export type FsRoots = {
  roots: string[];
  default_root: string;
};

export type TextPreview = {
  text: string;
  truncated: boolean;
  next_offset: number;
};

export type TrashItem = {
  id: string;
  original_path: string;
  deleted_at: string;
  status: string;
};
