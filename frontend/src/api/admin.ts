import { apiClient, unwrap } from './client';

export type DatabaseTableInfo = {
  table: string;
  rows: number;
};

export type DatabaseOverview = {
  dialect: string;
  tables: DatabaseTableInfo[];
  stats: Record<string, number>;
};

export type RuntimeModelConfig = {
  llm?: {
    provider?: string;
    base_url?: string;
    model?: string;
    api_key_set?: boolean;
    validation?: {
      status?: string;
      message?: string;
      checked_at?: string;
      sample?: string;
    };
  };
  embedding?: {
    provider?: string;
    base_url?: string;
    model?: string;
    dim?: number;
    api_key_set?: boolean;
    validation?: {
      status?: string;
      message?: string;
      checked_at?: string;
    };
  };
  local_e5?: {
    status?: string;
    message?: string;
    pid?: number | string;
    health_url?: string;
    log_path?: string;
    started_at?: string;
    checked_at?: string;
  };
};

export type LocalE5Status = NonNullable<RuntimeModelConfig['local_e5']>;

export type RetrievalTraceItem = {
  chunk_id?: string;
  document_id?: string;
  score?: number;
  rrf_score?: number;
  source?: string;
};

export type RetrievalEvidenceItem = RetrievalTraceItem & {
  kb_id?: string;
  file_name?: string;
  text?: string;
  context_text?: string;
  page_number?: number;
  sheet_name?: string;
  heading_path?: string;
  chunk_type?: string;
  parent_chunk_id?: string;
};

export type RetrievalTestResult = {
  query: string;
  evidence: RetrievalEvidenceItem[];
  trace: {
    filters?: Record<string, unknown>;
    vector: RetrievalTraceItem[];
    keyword: RetrievalTraceItem[];
    fused: RetrievalTraceItem[];
    errors?: Record<string, string>;
  };
  vector_index?: Record<string, unknown>;
};

export function fetchUsers() {
  return unwrap<Record<string, unknown>[]>(apiClient.get('/admin/users'));
}

export function createUser(payload: {
  username: string;
  password: string;
  display_name: string;
  role: string;
  department: string;
}) {
  return unwrap<Record<string, unknown>>(apiClient.post('/admin/users', payload));
}

export function fetchAuditLogs() {
  return unwrap<Record<string, unknown>[]>(apiClient.get('/admin/audit-logs'));
}

export function fetchTasks() {
  return unwrap<Record<string, unknown>[]>(apiClient.get('/admin/tasks'));
}

export function fetchModelCallLogs() {
  return unwrap<Record<string, unknown>>(apiClient.get('/admin/model-call-logs'));
}

export function fetchModelHealth() {
  return unwrap<Record<string, unknown>>(apiClient.get('/health/models'));
}

export function fetchDatabaseOverview() {
  return unwrap<DatabaseOverview>(apiClient.get('/admin/database/overview'));
}

export function vacuumDatabase() {
  return unwrap<{ status: string; message: string }>(apiClient.post('/admin/database/vacuum'));
}

export function fetchModelSetup() {
  return unwrap<RuntimeModelConfig>(apiClient.get('/admin/model-setup'));
}

export function configureDeepSeek(payload: { api_key: string; model: string }) {
  return unwrap<RuntimeModelConfig>(apiClient.post('/admin/model-setup/deepseek', payload));
}

export function configureLocalLLM(payload: { base_url: string; model?: string }) {
  return unwrap<RuntimeModelConfig>(apiClient.post('/admin/model-setup/llm', payload));
}

export function configureLocalEmbedding(payload: { base_url: string; api_key?: string; model?: string }) {
  return unwrap<RuntimeModelConfig>(apiClient.post('/admin/model-setup/embedding', payload));
}

export function startLocalE5() {
  return unwrap<LocalE5Status>(apiClient.post('/admin/model-setup/local-e5/start'));
}

export function fetchLocalE5Status() {
  return unwrap<LocalE5Status>(apiClient.get('/admin/model-setup/local-e5/status'));
}

export function testRetrieval(payload: { query: string; kb_id?: string | null; top_k: number }) {
  return unwrap<RetrievalTestResult>(apiClient.post('/admin/retrieval/test', payload));
}
