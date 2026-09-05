export type DataRoot = {
  root_id: string;
  label: string;
  path: string;
  readable: boolean;
  writable: boolean;
};

export type PathBreadcrumb = {
  label: string;
  relative_path: string;
};

export type DirectoryEntry = {
  name: string;
  relative_path: string;
  readable: boolean;
  is_symlink: boolean;
};

export type FileEntry = {
  name: string;
  relative_path: string;
  suffix: string;
  size_bytes: number;
  readable: boolean;
  is_symlink: boolean;
};

export type DirectoryListing = {
  root: DataRoot;
  relative_path: string;
  parent_relative_path: string | null;
  breadcrumbs: PathBreadcrumb[];
  directories: DirectoryEntry[];
  files: FileEntry[];
  directory_count: number;
  file_count: number;
  directories_truncated: boolean;
  files_truncated: boolean;
};

export type DatasetSample = {
  sample_id: string;
  label: string;
  relative_root: string;
  entities: Record<string, string>;
};

export type SamplePathMatch = {
  sample_id: string;
  label: string;
  relative_path: string;
  absolute_path: string;
  status: 'matched' | 'missing' | 'invalid';
  message: string;
};

export type SamplePathCoverage = {
  total: number;
  matched: number;
  missing: number;
  invalid: number;
};

export type DatasetPathPreview = {
  dataset_id: string;
  binding_mode: 'single' | 'per_sample' | 'dataset';
  selected_sample_id: string | null;
  selected_relative_path: string;
  path_template: string;
  variables: string[];
  coverage: SamplePathCoverage;
  matches: SamplePathMatch[];
  can_apply: boolean;
  messages: string[];
};

export type DatasetInspection = {
  file_count: number;
  total_bytes: number;
  truncated: boolean;
  is_bids: boolean;
  has_dwi: boolean;
  has_bval: boolean;
  has_bvec: boolean;
  has_t1w: boolean;
  has_preprocessed_dwi: boolean;
  has_fod: boolean;
  has_five_tt: boolean;
  has_reverse_phase: boolean;
  shell_count: number | null;
  input_types: string[];
  features: Record<string, boolean>;
  sample_layout: 'bids' | 'directory' | 'single';
  sample_count: number;
  samples: DatasetSample[];
  warnings: string[];
  scanned_at: string;
};

export type Dataset = {
  dataset_id: string;
  root_id: string;
  relative_path: string;
  display_name: string;
  absolute_path: string;
  inspection: DatasetInspection;
  created_at: string;
  updated_at: string;
};
