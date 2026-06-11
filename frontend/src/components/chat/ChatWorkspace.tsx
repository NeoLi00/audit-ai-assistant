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
  HomeOutlined,
  LikeOutlined,
  LoadingOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PaperClipOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Button, Dropdown, Empty, Input, message, Modal, Progress, Select, Space, Spin, Tag, Tooltip, Typography } from 'antd';
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { fetchMe, logout, type UserInfo } from '../../api/auth';
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

const scopedConversationRequests = new Map<string, Promise<Conversation>>();

export default function ChatWorkspace() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedConversationId = searchParams.get('conversationId') || undefined;
  const requestedQuery = searchParams.get('query');
  const requestedKbId = searchParams.get('kbId') || undefined;
  const requestedKbIdsParam = searchParams.get('kbIds');
  const requestedLaunchId = searchParams.get('launchId') || '';
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
  const [conversationSearchResults, setConversationSearchResults] = useState<Conversation[]>([]);
  const [conversationSearchOpen, setConversationSearchOpen] = useState(false);
  const [editingConversationId, setEditingConversationId] = useState<string>();
  const [editingTitle, setEditingTitle] = useState('');
  const [editingMessageId, setEditingMessageId] = useState<string>();
  const [editingMessageContent, setEditingMessageContent] = useState('');
  const [actionMessageId, setActionMessageId] = useState<string>();
  const [exportingTarget, setExportingTarget] = useState<{ messageId: string; format: 'md' | 'word' | 'pdf' }>();
  const initialQuerySent = useRef<string | undefined>(undefined);
  const bootstrappedScopedLaunch = useRef<string | undefined>(undefined);
  const initialUploadOpened = useRef(false);
  const messageEndRef = useRef<HTMLDivElement | null>(null);
  const shouldCreateScopedConversation =
    Boolean(requestedQuery) || Boolean(requestedScope) || requestedKbIds.length > 0 || requestedDocumentIds.length > 0;
  const scopedLaunchKey = useMemo(() => {
    if (!shouldCreateScopedConversation) {
      return '';
    }
    return [
      requestedLaunchId || location.key,
      requestedQuery || '',
      requestedScope,
      requestedScopeLabel,
      requestedKbIds.join(','),
      requestedDocumentIds.join(','),
    ].join('|');
  }, [
    location.key,
    requestedDocumentIds,
    requestedKbIds,
    requestedLaunchId,
    requestedQuery,
    requestedScope,
    requestedScopeLabel,
    shouldCreateScopedConversation,
  ]);

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
      if (shouldCreateScopedConversation) {
        if (bootstrappedScopedLaunch.current === scopedLaunchKey) {
          return;
        }
        bootstrappedScopedLaunch.current = scopedLaunchKey;
        const title = requestedScopeLabel || requestedQuery?.slice(0, 24) || '新会话';
        const created = await createScopedConversationOnce(scopedLaunchKey, {
          title,
          kb_ids: requestedKbIds,
          document_ids: requestedDocumentIds,
          scope_label: requestedScopeLabel,
          client_request_id: scopedLaunchKey,
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
    requestedScopeLabel,
    scopedLaunchKey,
    searchParams,
    setSearchParams,
    shouldCreateScopedConversation,
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
      const search = conversationSearch.trim();
      if (!search) {
        setConversationSearchResults([]);
        setConversationSearchOpen(false);
        fetchConversations()
          .then(setConversations)
          .catch(() => undefined);
        return;
      }
      fetchConversations(search)
        .then((items) => {
          setConversationSearchResults(items);
          setConversationSearchOpen(true);
        })
        .catch(() => {
          setConversationSearchResults([]);
          setConversationSearchOpen(true);
        });
    }, 220);
    return () => window.clearTimeout(timer);
  }, [conversationSearch]);

  useEffect(() => {
    if (!requestedQuery || !active || messages.length > 0) {
      return;
    }
    const queryLaunchKey = `${active.id}|${scopedLaunchKey}|${requestedQuery}`;
    if (initialQuerySent.current !== queryLaunchKey) {
      initialQuerySent.current = queryLaunchKey;
      handleSubmit(requestedQuery, requestedKbIds);
    }
  }, [active, handleSubmit, messages.length, requestedKbIds, requestedQuery, scopedLaunchKey]);

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

  const openConversation = async (conversationId: string) => {
    setSearchParams({ conversationId });
    setConversationSearch('');
    setConversationSearchResults([]);
    setConversationSearchOpen(false);
    await loadConversation(conversationId);
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

  const exportAssistantOutput = async (item: ChatMessage, format: 'md' | 'word' | 'pdf') => {
    const answer = item.content.trim();
    if (!answer) {
      message.warning('当前回答为空，无法导出');
      return;
    }
    setExportingTarget({ messageId: item.id, format });
    try {
      const fileTitle = sanitizeFileName(`${active?.title || 'assistant-answer'}-回答`);
      const timestamp = formatExportTime(new Date(item.created_at || Date.now()));
      if (format === 'md') {
        downloadBlob(`${fileTitle}-${timestamp}.md`, new Blob([`${answer}\n`], { type: 'text/markdown;charset=utf-8' }));
        return;
      }
      if (format === 'word') {
        const html = buildWordDocument(answer);
        downloadBlob(`${fileTitle}-${timestamp}.doc`, new Blob([html], { type: 'application/msword;charset=utf-8' }));
        return;
      }
      await downloadAnswerPdf(`${fileTitle}-${timestamp}.pdf`, answer);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导出失败');
    } finally {
      setExportingTarget(undefined);
    }
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

  const handleWorkspaceLogout = useCallback(async () => {
    try {
      await logout();
    } catch {
      // Token may already be expired; local cleanup still matters.
    }
    localStorage.removeItem('audit_ai_token');
    localStorage.removeItem('audit_ai_user');
    window.location.reload();
  }, []);

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
          <div className="workspace-search-box">
            <Input
              className="workspace-search"
              prefix={<SearchOutlined />}
              value={conversationSearch}
              onChange={(event) => setConversationSearch(event.target.value)}
              onFocus={() => setConversationSearchOpen(Boolean(conversationSearch.trim()))}
              placeholder="搜索会话标题或内容"
              allowClear
            />
            {conversationSearch.trim() && conversationSearchOpen && (
              <div className="conversation-search-popover" onMouseDown={(event) => event.preventDefault()}>
                <div className="conversation-search-head">
                  <span>匹配会话</span>
                  <span>{conversationSearchResults.length} 个结果</span>
                </div>
                <div className="conversation-search-results">
                  {conversationSearchResults.length ? (
                    conversationSearchResults.slice(0, 8).map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className="conversation-search-result"
                        onClick={() => openConversation(item.id)}
                      >
                        <ConversationSearchResult
                          conversation={item}
                          query={conversationSearch}
                        />
                      </button>
                    ))
                  ) : (
                    <div className="conversation-search-empty">没有匹配的会话</div>
                  )}
                </div>
              </div>
            )}
          </div>
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
        <div className="workspace-recents-label">最近</div>
        <div className="conversation-stack" role="list">
          {conversations.length ? (
            conversations.map((item) => (
              <div
                key={item.id}
                role="listitem"
                className={active?.id === item.id ? 'conversation active' : 'conversation'}
                onClick={() => openConversation(item.id)}
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
        {user && (
          <div className="workspace-user-footer">
            <div className="workspace-user-chip">
              <span className="workspace-user-avatar">{user.display_name.slice(0, 1).toUpperCase()}</span>
              <span className="workspace-user-copy">
                <span className="workspace-user-name">{user.display_name}</span>
                <span className="workspace-user-role">{userSubtitle(user)}</span>
              </span>
              <Tooltip title="退出">
                <Button
                  type="text"
                  size="small"
                  icon={<LogoutOutlined />}
                  aria-label="退出"
                  onClick={handleWorkspaceLogout}
                />
              </Tooltip>
            </div>
          </div>
        )}
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
                  <Dropdown
                    trigger={['click']}
                    menu={{
                      items: [
                        { key: 'md', label: '导出为 Markdown (.md)' },
                        { key: 'word', label: '导出为 Word 文档 (.doc)' },
                        { key: 'pdf', label: '导出为 PDF' },
                      ],
                      onClick: ({ key }) => {
                        void exportAssistantOutput(item, key as 'md' | 'word' | 'pdf');
                      },
                    }}
                  >
                    <Tooltip title="导出当前回答">
                      <Button
                        size="small"
                        icon={<DownloadOutlined />}
                        aria-label="导出当前回答"
                        loading={exportingTarget?.messageId === item.id}
                      />
                    </Tooltip>
                  </Dropdown>
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

function ConversationSearchResult({ conversation, query }: { conversation: Conversation; query: string }) {
  const match = conversation.search_match || {};
  const isTitleMatch = match.source === 'title';
  const snippet = isTitleMatch
    ? conversation.title
    : compactSnippetAroundQuery(match.snippet || conversation.title, query, match.matched_text);
  return (
    <>
      <span className={isTitleMatch ? 'conversation-search-title title-only' : 'conversation-search-title'}>
        {highlightQuery(conversation.title, query)}
      </span>
      {!isTitleMatch && <span className="conversation-search-snippet">{highlightQuery(snippet, query)}</span>}
      <span className="conversation-search-meta">
        {formatShortTime(conversation.updated_at)} · {isTitleMatch ? '标题匹配' : '对话内容匹配'}
      </span>
    </>
  );
}

function highlightQuery(text: string, query: string) {
  const terms = searchHighlightTerms(query);
  if (!terms.length) {
    return text;
  }
  const lowerText = text.toLocaleLowerCase();
  const parts: ReactNode[] = [];
  let cursor = 0;
  while (cursor < text.length) {
    const match = nextHighlightMatch(lowerText, terms, cursor);
    if (!match) {
      break;
    }
    if (match.index > cursor) {
      parts.push(text.slice(cursor, match.index));
    }
    parts.push(
      <mark key={`${match.index}-${match.term}`} className="search-highlight">
        {text.slice(match.index, match.index + match.term.length)}
      </mark>,
    );
    cursor = match.index + match.term.length;
  }
  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }
  return parts.length ? parts : text;
}

function searchHighlightTerms(query: string) {
  const cleanQuery = query.trim().replace(/\s+/g, ' ');
  if (!cleanQuery) {
    return [];
  }
  const terms = [cleanQuery, ...cleanQuery.split(' ')]
    .map((term) => term.trim())
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);
  return Array.from(new Set(terms));
}

function nextHighlightMatch(lowerText: string, terms: string[], cursor: number) {
  let best: { index: number; term: string } | undefined;
  for (const term of terms) {
    const index = lowerText.indexOf(term.toLocaleLowerCase(), cursor);
    if (index < 0) {
      continue;
    }
    if (!best || index < best.index || (index === best.index && term.length > best.term.length)) {
      best = { index, term };
    }
  }
  return best;
}

function compactSnippetAroundQuery(snippet: string, query: string, matchedText?: string) {
  const normalized = snippet.trim().replace(/\s+/g, ' ');
  if (normalized.length <= 86) {
    return normalized;
  }
  const terms = searchHighlightTerms(matchedText || query);
  const lowerText = normalized.toLocaleLowerCase();
  const match = nextHighlightMatch(lowerText, terms, 0);
  if (!match) {
    return `${normalized.slice(0, 82)}…`;
  }
  const context = 28;
  const left = Math.max(0, match.index - context);
  const right = Math.min(normalized.length, match.index + match.term.length + context);
  return `${left > 0 ? '…' : ''}${normalized.slice(left, right)}${right < normalized.length ? '…' : ''}`;
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

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    system_admin: '系统管理员',
    audit_manager: '审计管理员',
    auditor: '审计人员',
  };
  return labels[role] || role;
}

function userSubtitle(user: UserInfo) {
  const role = roleLabel(user.role);
  if (user.display_name === role) {
    return user.department || role;
  }
  return role;
}

function createScopedConversationOnce(key: string, payload: Parameters<typeof createConversation>[0]) {
  const requestKey = key || JSON.stringify(payload);
  const existing = scopedConversationRequests.get(requestKey);
  if (existing) {
    return existing;
  }
  const request = createConversation(payload);
  scopedConversationRequests.set(requestKey, request);
  return request;
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

function downloadBlob(fileName: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function buildWordDocument(content: string) {
  const bodyHtml = plainTextToHtml(markdownToPlainText(content));
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>AI 回答</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif; line-height: 1.72; color: #1f1f1f; }
    h2 { font-size: 15px; margin: 22px 0 8px; color: #333; }
    p { margin: 0 0 12px; }
    table { border-collapse: collapse; width: 100%; }
    td, th { border: 1px solid #deded8; padding: 6px 8px; }
  </style>
</head>
<body>
  ${bodyHtml}
</body>
</html>`;
}

async function downloadAnswerPdf(fileName: string, content: string) {
  const plainText = markdownToPlainText(content);
  const pages = renderTextPages(plainText);
  downloadBlob(fileName, buildImagePdf(pages));
}

function plainTextToHtml(content: string) {
  return content
    .trim()
    .split(/\n{2,}/)
    .map((paragraph) => {
      return `<p>${escapeHtml(paragraph).replace(/\n/g, '<br />')}</p>`;
    })
    .join('\n');
}

function markdownToPlainText(content: string) {
  return content
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .trim();
}

type PdfImagePage = {
  width: number;
  height: number;
  bytes: Uint8Array;
};

function renderTextPages(content: string): PdfImagePage[] {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error('浏览器不支持 PDF 导出所需的 Canvas');
  }

  const width = 1240;
  const height = 1754;
  const marginX = 118;
  const marginY = 126;
  const fontSize = 30;
  const lineHeight = 50;
  const paragraphGap = 22;
  const maxTextWidth = width - marginX * 2;
  const fontFamily = '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", Arial, sans-serif';
  const pages: PdfImagePage[] = [];
  let y = marginY;

  const resetPage = () => {
    canvas.width = width;
    canvas.height = height;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = '#1f1f1f';
    ctx.font = `${fontSize}px ${fontFamily}`;
    ctx.textBaseline = 'top';
  };
  const commitPage = () => {
    const dataUrl = canvas.toDataURL('image/jpeg', 0.92);
    pages.push({ width, height, bytes: dataUrlToBytes(dataUrl) });
  };

  resetPage();
  const paragraphs = content.trim() ? content.split(/\n{2,}/) : [''];
  for (const paragraph of paragraphs) {
    const sourceLines = paragraph.split('\n');
    for (const sourceLine of sourceLines) {
      const lines = wrapCanvasText(ctx, sourceLine || ' ', maxTextWidth);
      for (const line of lines) {
        if (y + lineHeight > height - marginY) {
          commitPage();
          resetPage();
          y = marginY;
        }
        ctx.fillText(line, marginX, y);
        y += lineHeight;
      }
    }
    y += paragraphGap;
  }
  commitPage();
  return pages;
}

function wrapCanvasText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number) {
  const chars = Array.from(text);
  const lines: string[] = [];
  let current = '';
  for (const char of chars) {
    const next = current + char;
    if (current && ctx.measureText(next).width > maxWidth) {
      lines.push(current);
      current = char;
    } else {
      current = next;
    }
  }
  lines.push(current || ' ');
  return lines;
}

function dataUrlToBytes(dataUrl: string) {
  const base64 = dataUrl.split(',')[1] || '';
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function buildImagePdf(pages: PdfImagePage[]) {
  const encoder = new TextEncoder();
  const parts: BlobPart[] = [];
  const offsets: number[] = [];
  let length = 0;
  const pdfWidth = 595.28;
  const pdfHeight = 841.89;
  const objectCount = 2 + pages.length * 3;

  const pushText = (value: string) => {
    const bytes = encoder.encode(value);
    const buffer = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(buffer).set(bytes);
    parts.push(buffer);
    length += bytes.length;
  };
  const pushBytes = (bytes: Uint8Array) => {
    const buffer = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(buffer).set(bytes);
    parts.push(buffer);
    length += bytes.length;
  };
  const startObject = (objectId: number) => {
    offsets[objectId] = length;
    pushText(`${objectId} 0 obj\n`);
  };
  const pageObjectId = (index: number) => 3 + index * 3;
  const imageObjectId = (index: number) => pageObjectId(index) + 1;
  const contentObjectId = (index: number) => pageObjectId(index) + 2;

  pushText('%PDF-1.4\n%\xE2\xE3\xCF\xD3\n');
  startObject(1);
  pushText('<< /Type /Catalog /Pages 2 0 R >>\nendobj\n');
  startObject(2);
  pushText(
    `<< /Type /Pages /Count ${pages.length} /Kids [${pages.map((_, index) => `${pageObjectId(index)} 0 R`).join(' ')}] >>\nendobj\n`,
  );

  pages.forEach((page, index) => {
    const pageId = pageObjectId(index);
    const imageId = imageObjectId(index);
    const contentId = contentObjectId(index);
    const stream = `q\n${pdfWidth} 0 0 ${pdfHeight} 0 0 cm\n/Im${index + 1} Do\nQ\n`;

    startObject(pageId);
    pushText(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pdfWidth} ${pdfHeight}] /Resources << /XObject << /Im${index + 1} ${imageId} 0 R >> >> /Contents ${contentId} 0 R >>\nendobj\n`,
    );
    startObject(imageId);
    pushText(
      `<< /Type /XObject /Subtype /Image /Width ${page.width} /Height ${page.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.bytes.length} >>\nstream\n`,
    );
    pushBytes(page.bytes);
    pushText('\nendstream\nendobj\n');
    startObject(contentId);
    pushText(`<< /Length ${encoder.encode(stream).length} >>\nstream\n${stream}endstream\nendobj\n`);
  });

  const xrefOffset = length;
  pushText(`xref\n0 ${objectCount + 1}\n0000000000 65535 f \n`);
  for (let objectId = 1; objectId <= objectCount; objectId += 1) {
    pushText(`${String(offsets[objectId]).padStart(10, '0')} 00000 n \n`);
  }
  pushText(`trailer\n<< /Size ${objectCount + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`);
  return new Blob(parts, { type: 'application/pdf' });
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
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
  const detail = file.error_message || file.status_message || file.parser_detail || '';
  const showDetail = Boolean(detail && !compact && file.status !== 'ready');
  const progressPercent = tempFileProgressPercent(file);
  const showProgress = !compact && file.status !== 'ready';
  return (
    <div
      className={`chat-attachment ${status.className} ${compact ? 'compact' : ''} ${
        showDetail || showProgress ? 'with-detail' : ''
      }`}
    >
      <PaperClipOutlined className="chat-attachment-icon" />
      <Typography.Text ellipsis={{ tooltip: file.file_name }} className="chat-attachment-name">
        {file.file_name}
      </Typography.Text>
      <Tooltip title={detail || undefined}>
        <Tag icon={status.icon} color={status.color}>
          {status.label}
        </Tag>
      </Tooltip>
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
      {showDetail ? (
        <Typography.Text type="secondary" className="chat-attachment-detail" ellipsis={{ tooltip: detail }}>
          {detail}
        </Typography.Text>
      ) : null}
      {showProgress ? (
        <div className="chat-attachment-progress">
          <div className="chat-attachment-progress-label">
            <Typography.Text type="secondary">{file.progress_stage || status.label}</Typography.Text>
            <Typography.Text type="secondary">{progressPercent}%</Typography.Text>
          </div>
          <Progress
            percent={progressPercent}
            showInfo={false}
            size="small"
            status={tempFileProgressStatus(file.status)}
            strokeColor={file.status === 'need_review' ? '#d97706' : undefined}
          />
        </div>
      ) : null}
    </div>
  );
}

function tempFileProgressPercent(file: TempFile) {
  const value = file.progress_percent ?? fallbackTempFileProgress(file.status);
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value)));
}

function fallbackTempFileProgress(status: string) {
  if (status === 'parsing') return 40;
  if (status === 'need_review' || status === 'failed' || status === 'ready') return 100;
  return 0;
}

function tempFileProgressStatus(status: string): 'normal' | 'active' | 'exception' | 'success' {
  if (status === 'failed') return 'exception';
  if (status === 'ready') return 'success';
  if (status === 'parsing') return 'active';
  return 'normal';
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
