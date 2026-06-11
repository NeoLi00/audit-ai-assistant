import { apiClient, unwrap } from './client';

export type Citation = {
  chunk_id: string;
  document_id: string;
  file_name: string;
  page_number?: number;
  sheet_name?: string;
  heading_path?: string;
  quote: string;
  score: number;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  attachments?: TempFile[];
  created_at: string;
};

export type TempFile = {
  id: string;
  file_name: string;
  status: string;
  error_message?: string;
  expires_at?: string;
};

export type Conversation = {
  id: string;
  title: string;
  mode: string;
  search_match?: {
    source?: 'title' | 'message' | 'none';
    title?: string;
    snippet?: string;
    matched_text?: string;
    role?: string;
  };
  scope?: {
    type?: string;
    label?: string;
    kb_ids?: string[];
    document_ids?: string[];
  };
  created_at: string;
  updated_at: string;
  messages?: ChatMessage[];
  temp_files?: TempFile[];
};

export type ConversationCreatePayload = {
  title?: string;
  kb_ids?: string[];
  document_ids?: string[];
  scope_label?: string;
};

export function createConversation(payload?: string | ConversationCreatePayload) {
  const body = typeof payload === 'string' ? { title: payload } : payload || {};
  return unwrap<Conversation>(apiClient.post('/chat/conversations', body));
}

export function fetchConversations(query?: string) {
  const q = query?.trim();
  return unwrap<Conversation[]>(apiClient.get('/chat/conversations', q ? { params: { q } } : undefined));
}

export function fetchConversation(conversationId: string) {
  return unwrap<Conversation>(apiClient.get(`/chat/conversations/${conversationId}`));
}

export function updateConversationTitle(conversationId: string, title: string) {
  return unwrap<Conversation>(apiClient.patch(`/chat/conversations/${conversationId}`, { title }));
}

export function deleteConversation(conversationId: string) {
  return unwrap<{ deleted: string }>(apiClient.delete(`/chat/conversations/${conversationId}`));
}

export function sendMessage(conversationId: string, content: string, kbIds: string[] = [], documentIds: string[] = []) {
  return unwrap<{ user_message?: ChatMessage; message: ChatMessage; conversation?: Conversation }>(
    apiClient.post(`/chat/conversations/${conversationId}/messages`, {
      content,
      kb_id: kbIds[0],
      kb_ids: kbIds,
      document_ids: documentIds,
    }),
  );
}

export function editMessageAndRegenerate(
  conversationId: string,
  messageId: string,
  content: string,
  kbIds: string[] = [],
  documentIds: string[] = [],
) {
  return unwrap<Conversation>(
    apiClient.patch(`/chat/conversations/${conversationId}/messages/${messageId}`, {
      content,
      kb_id: kbIds[0],
      kb_ids: kbIds,
      document_ids: documentIds,
    }),
  );
}

export function regenerateAssistantMessage(
  conversationId: string,
  messageId: string,
  kbIds: string[] = [],
  documentIds: string[] = [],
) {
  return unwrap<Conversation>(
    apiClient.post(`/chat/conversations/${conversationId}/messages/${messageId}/regenerate`, {
      kb_id: kbIds[0],
      kb_ids: kbIds,
      document_ids: documentIds,
    }),
  );
}

export function uploadTempFile(conversationId: string, formData: FormData) {
  return unwrap<TempFile>(
    apiClient.post(`/chat/conversations/${conversationId}/temp-files`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  );
}

export function deleteTempFile(conversationId: string, fileId: string) {
  return unwrap<{ deleted: string }>(apiClient.delete(`/chat/conversations/${conversationId}/temp-files/${fileId}`));
}

export function sendFeedback(messageId: string, feedbackType: string, detail?: string) {
  return unwrap<Record<string, unknown>>(
    apiClient.post('/chat/feedback', { message_id: messageId, feedback_type: feedbackType, detail }),
  );
}
