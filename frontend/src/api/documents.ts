import { apiClient, unwrap } from './client';
import type { DocumentItem } from './kb';

export type DocumentBlock = {
  id: string;
  block_type: string;
  page_number?: number;
  sheet_name?: string;
  heading_path?: string;
  text: string;
  confidence?: number;
};

export type DocumentChunk = {
  id: string;
  chunk_index: number;
  parent_chunk_id?: string;
  prev_chunk_id?: string;
  next_chunk_id?: string;
  chunk_type?: string;
  token_count?: number;
  content_hash?: string;
  chunker_version?: string;
  text: string;
  metadata: Record<string, unknown>;
};

export function fetchDocuments() {
  return unwrap<DocumentItem[]>(apiClient.get('/documents'));
}

export function fetchDocument(documentId: string) {
  return unwrap<DocumentItem>(apiClient.get(`/documents/${documentId}`));
}

export function fetchDocumentBlocks(documentId: string) {
  return unwrap<DocumentBlock[]>(apiClient.get(`/documents/${documentId}/blocks`));
}

export function fetchDocumentChunks(documentId: string) {
  return unwrap<DocumentChunk[]>(apiClient.get(`/documents/${documentId}/chunks`));
}

export function uploadDocument(formData: FormData) {
  return unwrap<DocumentItem>(
    apiClient.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  );
}

export function submitOcrCorrection(documentId: string, text: string) {
  return unwrap<Record<string, unknown>>(apiClient.post(`/documents/${documentId}/ocr-correction`, { text }));
}
