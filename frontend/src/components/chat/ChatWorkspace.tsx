import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  DislikeOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  LikeOutlined,
  LoadingOutlined,
  MessageOutlined,
  PaperClipOutlined,
  PlusOutlined,
  ReloadOutlined,
  UserOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Button, Empty, Input, message, Modal, Select, Space, Spin, Tag, Tooltip, Typography } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  createConversation,
  deleteConversation,
  deleteTempFile,
  fetchConversation,
  fetchConversations,
  sendFeedback,
  sendMessage,
  updateConversationTitle,
  type ChatMessage,
  type Conversation,
  type TempFile,
} from '../../api/chat';
import { fetchKnowledgeBases, type KnowledgeBase } from '../../api/kb';
import ChatInput from '../ChatInput';
import FileUploadPanel from '../FileUploadPanel';
import ModelStatusBadge from '../ModelStatusBadge';

export default function ChatWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedConversationId = searchParams.get('conversationId') || undefined;
  const requestedQuery = searchParams.get('query');
  const requestedKbId = searchParams.get('kbId') || undefined;
  const requestedKbIdsParam = searchParams.get('kbIds');
  const requestedKbIds = useMemo(
    () => parseKbIds(requestedKbIdsParam, requestedKbId),
    [requestedKbId, requestedKbIdsParam],
  );
  const requestedDocumentIds = useMemo(() => parseIds(searchParams.get('documentIds')), [searchParams]);
  const requestedScope = searchParams.get('scope') || '';
  const requestedScopeLabel = searchParams.get('scopeLabel') || '';
  const shouldOpenUpload = searchParams.get('upload') === '1';

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [tempFiles, setTempFiles] = useState<TempFile[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>(requestedKbIds);
  const [loading, setLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [editingConversationId, setEditingConversationId] = useState<string>();
  const [editingTitle, setEditingTitle] = useState('');
  const initialQuerySent = useRef(false);
  const initialUploadOpened = useRef(false);
  const messageEndRef = useRef<HTMLDivElement | null>(null);

  const activeScope = active?.scope;
  const selectedKbNames = useMemo(() => {
    const byId = new Map(knowledgeBases.map((kb) => [kb.id, kb.name]));
    return selectedKbIds.map((id) => byId.get(id)).filter(Boolean) as string[];
  }, [knowledgeBases, selectedKbIds]);

  const loadConversation = useCallback(async (id: string) => {
    const conversation = await fetchConversation(id);
    setActive(conversation);
    setMessages(conversation.messages || []);
    setTempFiles(conversation.temp_files || []);
    if (conversation.scope?.kb_ids?.length) {
      setSelectedKbIds(conversation.scope.kb_ids);
    }
  }, []);

  const bootstrap = useCallback(async () => {
    try {
      const list = await fetchConversations();
      setConversations(list);
      if (requestedConversationId) {
        await loadConversation(requestedConversationId);
        return;
      }
      const shouldCreateScopedConversation =
        Boolean(requestedQuery) || Boolean(requestedScope) || requestedKbIds.length > 0 || requestedDocumentIds.length > 0;
      if (shouldCreateScopedConversation) {
        const title = requestedScopeLabel || requestedQuery?.slice(0, 24) || '新会话';
        const created = await createConversation({
          title,
          kb_ids: requestedKbIds,
          document_ids: requestedDocumentIds,
          scope_label: requestedScopeLabel,
        });
        setConversations((items) => [created, ...items.filter((item) => item.id !== created.id)]);
        setActive(created);
        setMessages([]);
        setTempFiles([]);
        if (requestedKbIds.length) {
          setSelectedKbIds(requestedKbIds);
        }
        const nextParams = new URLSearchParams(searchParams);
        nextParams.set('conversationId', created.id);
        setSearchParams(nextParams, { replace: true });
        return;
      }
      if (list.length) {
        await loadConversation(list[0].id);
      } else {
        const created = await createConversation('审计问答');
        setConversations([created]);
        setActive(created);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '会话加载失败');
    }
  }, [
    loadConversation,
    requestedConversationId,
    requestedDocumentIds,
    requestedKbIds,
    requestedQuery,
    requestedScope,
    requestedScopeLabel,
    searchParams,
    setSearchParams,
  ]);

  const handleSubmit = useCallback(
    async (text: string, kbIds: string[] = selectedKbIds) => {
      let conversation = active;
      if (!conversation) {
        conversation = await createConversation(text.slice(0, 24));
        setActive(conversation);
        setConversations((items) => [conversation as Conversation, ...items]);
      }
      const documentIds = conversation.scope?.document_ids || [];
      const effectiveKbIds = documentIds.length ? conversation.scope?.kb_ids || [] : kbIds;
      const userMessage: ChatMessage = {
        id: `local-${Date.now()}`,
        role: 'user',
        content: text,
        citations: [],
        attachments: tempFiles,
        created_at: new Date().toISOString(),
      };
      setMessages((items) => [...items, userMessage]);
      setLoading(true);
      try {
        const result = await sendMessage(conversation.id, text, effectiveKbIds, documentIds);
        const returnedUserMessage = result.user_message;
        setMessages((items) => {
          const nextItems = returnedUserMessage
            ? items.map((item) => (item.id === userMessage.id ? returnedUserMessage : item))
            : items;
          return [...nextItems, result.message];
        });
        setConversations((items) =>
          items.map((item) =>
            item.id === conversation.id && isDefaultConversationTitle(item.title)
              ? { ...item, title: titleFromQuestion(text), updated_at: new Date().toISOString() }
              : item,
          ),
        );
        setActive((current) =>
          current && current.id === conversation.id && isDefaultConversationTitle(current.title)
            ? { ...current, title: titleFromQuestion(text), updated_at: new Date().toISOString() }
            : current,
        );
        setTempFiles([]);
      } catch (error) {
        message.error(error instanceof Error ? error.message : '发送失败');
        setMessages((items) => items.filter((item) => item.id !== userMessage.id));
      } finally {
        setLoading(false);
      }
    },
    [active, selectedKbIds, tempFiles],
  );

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    fetchKnowledgeBases()
      .then((items) => {
        setKnowledgeBases(items);
        setSelectedKbIds((current) => {
          if (current.length) {
            return current.filter((id) => items.some((kb) => kb.id === id));
          }
          return items[0]?.id ? [items[0].id] : [];
        });
      })
      .catch(() => setKnowledgeBases([]));
  }, []);

  useEffect(() => {
    if (requestedQuery && active && !initialQuerySent.current) {
      initialQuerySent.current = true;
      handleSubmit(requestedQuery, requestedKbIds);
    }
  }, [active, handleSubmit, requestedKbIds, requestedQuery]);

  useEffect(() => {
    if (shouldOpenUpload && active && !initialUploadOpened.current) {
      initialUploadOpened.current = true;
      setUploadOpen(true);
    }
  }, [active, shouldOpenUpload]);

  const hasProcessingTempFiles = tempFiles.some((file) => ['uploaded', 'parsing'].includes(file.status));
  useEffect(() => {
    if (!active || !hasProcessingTempFiles) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      loadConversation(active.id).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [active, hasProcessingTempFiles, loadConversation]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [messages.length, loading]);

  const createNewConversation = async () => {
    const item = await createConversation('新会话');
    setConversations((items) => [item, ...items]);
    setActive(item);
    setMessages([]);
    setTempFiles([]);
    setSearchParams({ conversationId: item.id });
  };

  const feedback = async (messageId: string, type: string) => {
    await sendFeedback(messageId, type);
    message.success('反馈已记录');
  };

  const saveConversationTitle = async (conversation: Conversation) => {
    const title = editingTitle.trim();
    if (!title) {
      message.warning('标题不能为空');
      return;
    }
    try {
      const updated = await updateConversationTitle(conversation.id, title);
      setConversations((items) => items.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)));
      setActive((current) => (current?.id === updated.id ? { ...current, ...updated } : current));
      setEditingConversationId(undefined);
      setEditingTitle('');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '改名失败');
    }
  };

  const confirmDeleteConversation = (conversation: Conversation) => {
    Modal.confirm({
      title: `删除会话：${conversation.title}`,
      content: '会话消息和未过期的临时附件都会一起删除。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteConversation(conversation.id);
          const remaining = conversations.filter((item) => item.id !== conversation.id);
          setConversations(remaining);
          if (active?.id === conversation.id) {
            const next = remaining[0];
            if (next) {
              setSearchParams({ conversationId: next.id });
              await loadConversation(next.id);
            } else {
              const created = await createConversation('新会话');
              setConversations([created]);
              setActive(created);
              setMessages([]);
              setTempFiles([]);
              setSearchParams({ conversationId: created.id });
            }
          }
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败');
        }
      },
    });
  };

  const removePendingTempFile = async (file: TempFile) => {
    if (!active) return;
    try {
      await deleteTempFile(active.id, file.id);
      setTempFiles((items) => items.filter((item) => item.id !== file.id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除附件失败');
    }
  };

  return (
    <div className="chat-workspace">
      <aside className="workspace-rail" aria-label="会话列表">
        <div className="workspace-rail-head">
          <div>
            <Typography.Text className="workspace-kicker">会话</Typography.Text>
            <Typography.Title level={5} className="workspace-panel-title">
              审计问答
            </Typography.Title>
          </div>
          <Tooltip title="新建对话">
            <Button type="primary" shape="circle" icon={<PlusOutlined />} onClick={createNewConversation} />
          </Tooltip>
        </div>
        <div className="conversation-stack" role="list">
          {conversations.length ? (
            conversations.map((item) => (
              <div
                key={item.id}
                role="listitem"
                className={active?.id === item.id ? 'conversation active' : 'conversation'}
                onClick={() => {
                  setSearchParams({ conversationId: item.id });
                  loadConversation(item.id);
                }}
              >
                {editingConversationId === item.id ? (
                  <Space.Compact className="full-width" onClick={(event) => event.stopPropagation()}>
                    <Input
                      size="small"
                      value={editingTitle}
                      onChange={(event) => setEditingTitle(event.target.value)}
                      onPressEnter={() => saveConversationTitle(item)}
                    />
                    <Button size="small" icon={<CheckCircleOutlined />} onClick={() => saveConversationTitle(item)} />
                    <Button
                      size="small"
                      icon={<CloseCircleOutlined />}
                      onClick={() => {
                        setEditingConversationId(undefined);
                        setEditingTitle('');
                      }}
                    />
                  </Space.Compact>
                ) : (
                  <div className="conversation-row">
                    <div className="conversation-copy">
                      <Typography.Text strong ellipsis={{ tooltip: item.title }} className="conversation-title">
                        {item.title}
                      </Typography.Text>
                      <Typography.Text type="secondary" className="conversation-time">
                        {formatShortTime(item.updated_at)}
                      </Typography.Text>
                    </div>
                    <Space size={0} className="conversation-actions" onClick={(event) => event.stopPropagation()}>
                      <Tooltip title="编辑标题">
                        <Button
                          size="small"
                          type="text"
                          icon={<EditOutlined />}
                          aria-label="编辑会话标题"
                          onClick={() => {
                            setEditingConversationId(item.id);
                            setEditingTitle(item.title);
                          }}
                        />
                      </Tooltip>
                      <Tooltip title="删除会话">
                        <Button
                          size="small"
                          danger
                          type="text"
                          icon={<DeleteOutlined />}
                          aria-label="删除会话"
                          onClick={() => confirmDeleteConversation(item)}
                        />
                      </Tooltip>
                    </Space>
                  </div>
                )}
              </div>
            ))
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无会话" />
          )}
        </div>
      </aside>

      <section className="workspace-chat" aria-label="审计 AI 工作台">
        <header className="workspace-chat-head">
          <div className="workspace-title-block">
            <Typography.Text className="workspace-kicker">工作台</Typography.Text>
            <Typography.Title level={3} className="workspace-title">
              {active?.title || '审计 AI 助手'}
            </Typography.Title>
            <Typography.Text type="secondary" className="workspace-subtitle">
              {selectedKbNames.length ? `当前检索：${selectedKbNames.join('、')}` : '选择知识库后开始问答'}
            </Typography.Text>
          </div>
          <div className="workspace-head-actions">
            <ModelStatusBadge />
          </div>
        </header>

        <div className="message-list workspace-message-list">
          {!messages.length && (
            <div className="workspace-empty">
              <FileSearchOutlined />
              <Typography.Title level={4}>开始一次审计问答</Typography.Title>
              <Typography.Text type="secondary">
                选择知识库或上传本轮附件后提问，回答会基于当前材料生成。
              </Typography.Text>
            </div>
          )}
          {messages.map((item) => (
            <article key={item.id} className={`message-bubble ${item.role}`}>
              <div className="message-meta">
                <span className="message-avatar">{item.role === 'user' ? <UserOutlined /> : <MessageOutlined />}</span>
                <Typography.Text strong>{item.role === 'user' ? '我' : '审计 AI 助手'}</Typography.Text>
              </div>
              <Typography.Paragraph className="markdown-text">{item.content}</Typography.Paragraph>
              {item.attachments && item.attachments.length > 0 && (
                <div className="message-attachment-list">
                  {item.attachments.map((file) => (
                    <ChatAttachment key={file.id} file={file} compact />
                  ))}
                </div>
              )}
              {item.role === 'assistant' && (
                <Space className="message-actions" size={4}>
                  <Tooltip title="有帮助">
                    <Button size="small" icon={<LikeOutlined />} onClick={() => feedback(item.id, 'like')} />
                  </Tooltip>
                  <Tooltip title="没帮助">
                    <Button size="small" icon={<DislikeOutlined />} onClick={() => feedback(item.id, 'dislike')} />
                  </Tooltip>
                  <Tooltip title="引用有误">
                    <Button size="small" icon={<WarningOutlined />} onClick={() => feedback(item.id, 'citation_error')} />
                  </Tooltip>
                  <Tooltip title="重新生成">
                    <Button size="small" icon={<ReloadOutlined />} onClick={() => feedback(item.id, 'regenerate')} />
                  </Tooltip>
                </Space>
              )}
            </article>
          ))}
          {loading && (
            <div className="workspace-loading">
              <Spin />
              <Typography.Text type="secondary">正在检索知识库并生成回答</Typography.Text>
            </div>
          )}
          <div ref={messageEndRef} />
        </div>

        <div className="workspace-composer">
          <div className="workspace-context-row">
            <div className="workspace-kb-select">
              <Typography.Text type="secondary">知识库</Typography.Text>
              <Select
                mode="multiple"
                value={selectedKbIds}
                onChange={setSelectedKbIds}
                placeholder="选择一个或多个知识库"
                maxTagCount="responsive"
                options={knowledgeBases.map((kb) => ({
                  value: kb.id,
                  label: `${kb.name}（${kb.visibility === 'shared' ? '共享' : '个人'}）`,
                }))}
              />
            </div>
            {activeScope?.label ? (
              <Tag className="workspace-scope-tag" color={activeScope.type === 'documents' ? 'purple' : 'blue'}>
                {activeScope.type === 'documents' ? '围绕文件' : '围绕知识库'}：{activeScope.label}
              </Tag>
            ) : null}
          </div>
          {tempFiles.length > 0 && (
            <div className="chat-attachment-strip">
              {tempFiles.map((file) => (
                <ChatAttachment key={file.id} file={file} onDelete={() => removePendingTempFile(file)} />
              ))}
            </div>
          )}
          <ChatInput
            disabled={loading || hasProcessingTempFiles}
            onSubmit={(text) => handleSubmit(text, selectedKbIds)}
            onUploadClick={() => setUploadOpen(true)}
          />
        </div>
      </section>

      <FileUploadPanel
        open={uploadOpen}
        conversationId={active?.id}
        onClose={() => setUploadOpen(false)}
        onUploaded={(file) => setTempFiles((items) => [...items, file])}
      />
    </div>
  );
}

function parseKbIds(rawKbIds: string | null, fallbackKbId?: string): string[] {
  const parsed = parseIds(rawKbIds);
  if (parsed.length) {
    return parsed;
  }
  return fallbackKbId ? [fallbackKbId] : [];
}

function parseIds(raw: string | null): string[] {
  return (raw || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function isDefaultConversationTitle(title: string) {
  return ['', '新会话', '审计问答'].includes(title.trim());
}

function titleFromQuestion(text: string) {
  return text.trim().replace(/\s+/g, ' ').slice(0, 24) || '新会话';
}

function formatShortTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function ChatAttachment({
  file,
  compact = false,
  onDelete,
}: {
  file: TempFile;
  compact?: boolean;
  onDelete?: () => void;
}) {
  const status = tempFileStatusMeta(file.status);
  return (
    <div className={`chat-attachment ${status.className} ${compact ? 'compact' : ''}`}>
      <PaperClipOutlined className="chat-attachment-icon" />
      <Typography.Text ellipsis={{ tooltip: file.file_name }} className="chat-attachment-name">
        {file.file_name}
      </Typography.Text>
      <Tag icon={status.icon} color={status.color}>
        {status.label}
      </Tag>
      {onDelete ? (
        <Tooltip title="删除附件">
          <Button
            size="small"
            danger
            type="text"
            icon={<DeleteOutlined />}
            aria-label="删除附件"
            onClick={onDelete}
          />
        </Tooltip>
      ) : null}
    </div>
  );
}

function tempFileStatusMeta(status: string) {
  if (status === 'ready') {
    return {
      label: '已上传',
      color: 'green',
      className: 'ready',
      icon: <CheckCircleOutlined />,
    };
  }
  if (status === 'need_review') {
    return {
      label: '待复核',
      color: 'gold',
      className: 'need-review',
      icon: <ExclamationCircleOutlined />,
    };
  }
  if (status === 'failed') {
    return {
      label: '失败',
      color: 'red',
      className: 'failed',
      icon: <CloseCircleOutlined />,
    };
  }
  return {
    label: '解析中',
    color: 'blue',
    className: 'processing',
    icon: <LoadingOutlined />,
  };
}
