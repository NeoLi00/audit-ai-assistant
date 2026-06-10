import {
  AuditOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DislikeOutlined,
  DownloadOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  HistoryOutlined,
  HomeOutlined,
  LikeOutlined,
  LoadingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PaperClipOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Button, Empty, Input, message, Modal, Select, Space, Spin, Tag, Tooltip, Typography } from 'antd';
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { fetchMe, type UserInfo } from '../../api/auth';
import {
  createConversation,
  deleteConversation,
  deleteTempFile,
  editMessageAndRegenerate,
  fetchConversation,
  fetchConversations,
  regenerateAssistantMessage,
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
  const navigate = useNavigate();
  const location = useLocation();
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
  const [user, setUser] = useState<UserInfo | null>(null);
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>(requestedKbIds);
  const [loading, setLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [conversationSearch, setConversationSearch] = useState('');
  const [editingConversationId, setEditingConversationId] = useState<string>();
  const [editingTitle, setEditingTitle] = useState('');
  const [editingMessageId, setEditingMessageId] = useState<string>();
  const [editingMessageContent, setEditingMessageContent] = useState('');
  const [actionMessageId, setActionMessageId] = useState<string>();
  const initialQuerySent = useRef(false);
  const initialUploadOpened = useRef(false);
  const messageEndRef = useRef<HTMLDivElement | null>(null);

  const activeScope = active?.scope;
  const selectedKbNames = useMemo(() => {
    const byId = new Map(knowledgeBases.map((kb) => [kb.id, kb.name]));
    return selectedKbIds.map((id) => byId.get(id)).filter(Boolean) as string[];
  }, [knowledgeBases, selectedKbIds]);
  const navItems = useMemo(
    () =>
      [
        { key: '/', label: '工作台', icon: <HomeOutlined /> },
        { key: '/kb', label: '知识库', icon: <DatabaseOutlined /> },
        { key: '/history', label: '历史记录', icon: <HistoryOutlined /> },
        { key: '/settings', label: '设置', icon: <SettingOutlined /> },
        user?.role === 'system_admin' || user?.role === 'audit_manager'
          ? { key: '/admin', label: '管理后台', icon: <ToolOutlined /> }
          : null,
      ].filter(Boolean) as Array<{ key: string; label: string; icon: ReactNode }>,
    [user?.role],
  );

  const applyConversation = useCallback((conversation: Conversation) => {
    setActive(conversation);
    setMessages(conversation.messages || []);
    setTempFiles(conversation.temp_files || []);
    setConversations((items) =>
      items.map((item) =>
        item.id === conversation.id
          ? {
              ...item,
              title: conversation.title,
              updated_at: conversation.updated_at,
              scope: conversation.scope,
            }
          : item,
      ),
    );
  }, []);

  const syncConversationSummary = useCallback((conversation: Conversation) => {
    setConversations((items) => {
      const exists = items.some((item) => item.id === conversation.id);
      const updated = items.map((item) =>
        item.id === conversation.id
          ? {
              ...item,
              title: conversation.title,
              updated_at: conversation.updated_at,
              scope: conversation.scope,
            }
          : item,
      );
      return exists ? updated : [conversation, ...updated];
    });
    setActive((current) =>
      current?.id === conversation.id
        ? {
            ...current,
            title: conversation.title,
            updated_at: conversation.updated_at,
            scope: conversation.scope,
          }
        : current,
    );
  }, []);

  const loadConversation = useCallback(async (id: string) => {
    const conversation = await fetchConversation(id);
    applyConversation(conversation);
    if (conversation.scope?.kb_ids?.length) {
      setSelectedKbIds(conversation.scope.kb_ids);
    }
  }, [applyConversation]);

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
        if (result.conversation) {
          syncConversationSummary(result.conversation);
        } else if (isDefaultConversationTitle(conversation.title)) {
          syncConversationSummary({ ...conversation, title: titleFromQuestion(text), updated_at: new Date().toISOString() });
        }
        setTempFiles([]);
      } catch (error) {
        message.error(error instanceof Error ? error.message : '发送失败');
        setMessages((items) => items.filter((item) => item.id !== userMessage.id));
      } finally {
        setLoading(false);
      }
    },
    [active, selectedKbIds, syncConversationSummary, tempFiles],
  );

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    if (window.matchMedia('(max-width: 760px)').matches) {
      setSidebarCollapsed(true);
    }
  }, []);

  useEffect(() => {
    fetchMe().then(setUser).catch(() => setUser(null));
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
    const timer = window.setTimeout(() => {
      fetchConversations(conversationSearch)
        .then(setConversations)
        .catch(() => undefined);
    }, 220);
    return () => window.clearTimeout(timer);
  }, [conversationSearch]);

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

  const copyAssistantOutput = async (item: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(item.content);
      message.success('已复制');
    } catch {
      message.error('复制失败，请手动选择文本');
    }
  };

  const exportAssistantOutput = (item: ChatMessage) => {
    const fileTitle = sanitizeFileName(active?.title || 'assistant-output');
    const content = `${active?.title || '审计 AI 助手'}\n\n${item.content}\n`;
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${fileTitle}-${formatExportTime(new Date(item.created_at))}.md`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  const regenerateAnswer = async (item: ChatMessage) => {
    if (!active) return;
    setActionMessageId(item.id);
    setLoading(true);
    try {
      const documentIds = active.scope?.document_ids || [];
      const effectiveKbIds = documentIds.length ? active.scope?.kb_ids || [] : selectedKbIds;
      const conversation = await regenerateAssistantMessage(active.id, item.id, effectiveKbIds, documentIds);
      applyConversation(conversation);
      message.success('已重新生成');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '重新生成失败');
    } finally {
      setActionMessageId(undefined);
      setLoading(false);
    }
  };

  const startEditingUserMessage = (item: ChatMessage) => {
    setEditingMessageId(item.id);
    setEditingMessageContent(item.content);
  };

  const cancelEditingUserMessage = () => {
    setEditingMessageId(undefined);
    setEditingMessageContent('');
  };

  const saveUserMessageAndRegenerate = async (item: ChatMessage) => {
    if (!active) return;
    const content = editingMessageContent.trim();
    if (!content) {
      message.warning('问题不能为空');
      return;
    }
    setActionMessageId(item.id);
    setLoading(true);
    try {
      const documentIds = active.scope?.document_ids || [];
      const effectiveKbIds = documentIds.length ? active.scope?.kb_ids || [] : selectedKbIds;
      const conversation = await editMessageAndRegenerate(active.id, item.id, content, effectiveKbIds, documentIds);
      applyConversation(conversation);
      cancelEditingUserMessage();
      message.success('已根据新问题重新生成');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '编辑重问失败');
    } finally {
      setActionMessageId(undefined);
      setLoading(false);
    }
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

  const hasMessages = messages.length > 0;
  const selectedRoute = location.pathname === '/' ? '/' : `/${location.pathname.split('/')[1]}`;

  return (
    <div className={`chat-workspace ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className="workspace-rail" aria-label="会话列表">
        <div className="workspace-rail-head">
          <div className="workspace-brand">
            <span className="workspace-brand-icon">
              <AuditOutlined />
            </span>
            <Typography.Title level={5} className="workspace-panel-title">
              审计 AI 助手
            </Typography.Title>
          </div>
          <Tooltip title="收起侧边栏">
            <Button
              type="text"
              icon={<MenuFoldOutlined />}
              aria-label="收起侧边栏"
              onClick={() => setSidebarCollapsed(true)}
            />
          </Tooltip>
        </div>
        <div className="workspace-quick-actions">
          <Button className="workspace-action-row" type="text" icon={<PlusOutlined />} onClick={createNewConversation}>
            新对话
          </Button>
          <Input
            className="workspace-search"
            prefix={<SearchOutlined />}
            value={conversationSearch}
            onChange={(event) => setConversationSearch(event.target.value)}
            placeholder="搜索会话标题或内容"
            allowClear
          />
        </div>
        <nav className="workspace-nav" aria-label="主导航">
          {navItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={selectedRoute === item.key ? 'workspace-nav-item active' : 'workspace-nav-item'}
              onClick={() => navigate(item.key)}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="workspace-recents-label">{conversationSearch.trim() ? '搜索结果' : '最近'}</div>
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

      <section className={`workspace-chat ${hasMessages ? 'has-messages' : 'empty'}`} aria-label="审计 AI 工作台">
        {sidebarCollapsed && (
          <Tooltip title="展开侧边栏">
            <Button
              className="workspace-sidebar-toggle"
              type="text"
              icon={<MenuUnfoldOutlined />}
              aria-label="展开侧边栏"
              onClick={() => setSidebarCollapsed(false)}
            />
          </Tooltip>
        )}
        <header className="workspace-chat-head">
          <div className="workspace-title-block">
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
          {!hasMessages && (
            <div className="workspace-empty">
              <Typography.Title level={2}>今天要审计什么？</Typography.Title>
              <Typography.Text type="secondary">
                选择知识库、上传材料，或直接输入问题。
              </Typography.Text>
            </div>
          )}
          {messages.map((item) => (
            <article key={item.id} className={`message-bubble ${item.role}`}>
              {item.role === 'user' && editingMessageId === item.id ? (
                <div className="message-edit-panel">
                  <Input.TextArea
                    value={editingMessageContent}
                    onChange={(event) => setEditingMessageContent(event.target.value)}
                    autoSize={{ minRows: 2, maxRows: 8 }}
                    autoFocus
                  />
                  <Space size={6} className="message-edit-actions">
                    <Button
                      size="small"
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      loading={actionMessageId === item.id}
                      onClick={() => saveUserMessageAndRegenerate(item)}
                    >
                      保存并重新回答
                    </Button>
                    <Button size="small" icon={<CloseCircleOutlined />} onClick={cancelEditingUserMessage}>
                      取消
                    </Button>
                  </Space>
                </div>
              ) : (
                <MessageText content={item.content} />
              )}
              {item.attachments && item.attachments.length > 0 && (
                <div className="message-attachment-list">
                  {item.attachments.map((file) => (
                    <ChatAttachment key={file.id} file={file} compact />
                  ))}
                </div>
              )}
              {item.role === 'user' && editingMessageId !== item.id && (
                <Space className="message-actions user-actions" size={4}>
                  <Tooltip title="编辑问题并重新回答">
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      aria-label="编辑问题并重新回答"
                      disabled={loading}
                      onClick={() => startEditingUserMessage(item)}
                    />
                  </Tooltip>
                </Space>
              )}
              {item.role === 'assistant' && (
                <Space className="message-actions" size={4}>
                  <Tooltip title="复制">
                    <Button
                      size="small"
                      icon={<CopyOutlined />}
                      aria-label="复制回答"
                      onClick={() => copyAssistantOutput(item)}
                    />
                  </Tooltip>
                  <Tooltip title="导出当前回答">
                    <Button
                      size="small"
                      icon={<DownloadOutlined />}
                      aria-label="导出当前回答"
                      onClick={() => exportAssistantOutput(item)}
                    />
                  </Tooltip>
                  <Tooltip title="有帮助">
                    <Button
                      size="small"
                      icon={<LikeOutlined />}
                      aria-label="回答有帮助"
                      onClick={() => feedback(item.id, 'like')}
                    />
                  </Tooltip>
                  <Tooltip title="没帮助">
                    <Button
                      size="small"
                      icon={<DislikeOutlined />}
                      aria-label="回答没帮助"
                      onClick={() => feedback(item.id, 'dislike')}
                    />
                  </Tooltip>
                  <Tooltip title="重新生成">
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      aria-label="重新生成回答"
                      loading={actionMessageId === item.id}
                      disabled={loading && actionMessageId !== item.id}
                      onClick={() => regenerateAnswer(item)}
                    />
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

function MessageText({ content }: { content: string }) {
  const blocks = content.split(/\n{2,}/).filter((block) => block.length > 0);
  return (
    <div className="markdown-text">
      {blocks.map((block, blockIndex) => (
        <p key={`${blockIndex}-${block.slice(0, 12)}`}>
          {block.split('\n').map((line, lineIndex) => (
            <Fragment key={`${lineIndex}-${line.slice(0, 12)}`}>
              {lineIndex > 0 ? <br /> : null}
              {renderInlineMarkdown(line)}
            </Fragment>
          ))}
        </p>
      ))}
    </div>
  );
}

function renderInlineMarkdown(line: string) {
  return line.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${index}-${part}`}>{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={`${index}-${part}`}>{part}</Fragment>;
  });
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

function sanitizeFileName(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, '-').slice(0, 60) || 'assistant-output';
}

function formatExportTime(date: Date) {
  if (Number.isNaN(date.getTime())) {
    return 'unknown-time';
  }
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(
    date.getMinutes(),
  )}`;
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
