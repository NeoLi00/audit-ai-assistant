import type { DocumentItem } from '../api/kb';

const STATUS_COLOR: Record<string, string> = {
  uploaded: 'default',
  parsing: 'processing',
  ocr_running: 'processing',
  chunking: 'processing',
  embedding: 'processing',
  indexed: 'success',
  ready: 'success',
  failed: 'error',
  need_review: 'warning',
};

const STATUS_LABEL: Record<string, string> = {
  uploaded: '已上传',
  parsing: '解析中',
  ocr_running: 'OCR 中',
  chunking: '切分中',
  embedding: '索引中',
  indexed: '已入库',
  ready: '已完成',
  failed: '失败',
  need_review: '待复核',
};

export function documentStatusColor(status: string) {
  return STATUS_COLOR[status] || 'default';
}

export function documentStatusLabel(status: string) {
  return STATUS_LABEL[status] || status;
}

export function documentStatusDetail(document: DocumentItem) {
  if (document.status === 'failed' || document.status === 'need_review') {
    return document.error_message || document.status_message || document.parser_detail || '';
  }
  return document.status_message || document.parser_detail || '';
}

export function documentProgressPercent(document: DocumentItem) {
  return clampProgress(document.progress_percent ?? fallbackProgress(document.status));
}

export function documentProgressStage(document: DocumentItem) {
  return document.progress_stage || documentStatusLabel(document.status);
}

export function documentProgressStatus(status: string): 'normal' | 'active' | 'exception' | 'success' {
  if (status === 'failed') return 'exception';
  if (status === 'indexed' || status === 'ready') return 'success';
  if (['uploaded', 'parsing', 'ocr_running', 'chunking', 'embedding'].includes(status)) return 'active';
  return 'normal';
}

export function documentProgressColor(status: string) {
  if (status === 'need_review') return '#d97706';
  return undefined;
}

function fallbackProgress(status: string) {
  if (status === 'uploaded') return 8;
  if (status === 'parsing') return 40;
  if (status === 'ocr_running') return 50;
  if (status === 'chunking') return 70;
  if (status === 'embedding') return 88;
  if (['indexed', 'ready', 'need_review', 'failed'].includes(status)) return 100;
  return 0;
}

function clampProgress(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}
