import { apiClient, unwrap } from './client';

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  category: string;
  visibility: string;
  created_by?: string;
};

export type DocumentItem = {
  id: string;
  kb_id?: string;
  file_name: string;
  file_ext: string;
  file_size: number;
  department_category: string;
  business_type: string;
  tags: string[];
  visibility: string;
  version: number;
  is_current_version: boolean;
  status: string;
  error_message: string;
  status_message?: string;
  parser_provider?: string;
  parser_detail?: string;
  progress_percent?: number;
  progress_stage?: string;
  progress_estimated?: boolean;
  uploaded_by?: string;
  created_at: string;
};

export function fetchKnowledgeBases() {
  return unwrap<KnowledgeBase[]>(apiClient.get('/kb'));
}

export function createKnowledgeBase(payload: {
  name: string;
  description?: string;
  category?: string;
  visibility: 'shared' | 'private';
}) {
  return unwrap<KnowledgeBase>(apiClient.post('/kb', payload));
}

export function fetchKbDocuments(kbId: string) {
  return unwrap<DocumentItem[]>(apiClient.get(`/kb/${kbId}/documents`));
}

export function deleteKnowledgeBase(kbId: string) {
  return unwrap<{ deleted: string }>(apiClient.delete(`/kb/${kbId}`));
}
