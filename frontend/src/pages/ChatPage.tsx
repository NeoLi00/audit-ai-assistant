import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DislikeOutlined,
  ExclamationCircleOutlined,
  LikeOutlined,
  LoadingOutlined,
  PaperClipOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Button, Card, Empty, List, message, Select, Space, Spin, Tag, Typography } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  createConversation,
  fetchConversation,
  fetchConversations,
  sendFeedback,
  sendMessage,
  type ChatMessage,
  type Conversation,
  type TempFile,
} from '../api/chat';
import { fetchKnowledgeBases, type KnowledgeBase } from '../api/kb';
import ChatInput from '../components/ChatInput';
import FileUploadPanel from '../components/FileUploadPanel';

export default function ChatPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedConversationId = searchParams.get('conversationId') || undefined;
  const requestedQuery = searchParams.get('query');
  const requestedKbId = searchParams.get('kbId') || undefined;
  const requestedKbIdsParam = searchParams.get('kbIds');
  const requestedKbIds = useMemo(
    () => parseKbIds(requestedKbIdsParam, requestedKbId),
    [requestedKbId, requestedKbIdsParam],
  );
  const shouldOpenUpload = searchParams.get('upload') === '1';
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [tempFiles, setTempFiles] = useState<TempFile[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>(requestedKbIds);
  const [loading, setLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const initialQuerySent = useRef(false);
  const initialUploadOpened = useRef(false);

  const loadConversation = useCallback(async (id: string) => {
    const conversation = await fetchConversation(id);
    setActive(conversation);
    setMessages(conversation.messages || []);
    setTempFiles(conversation.temp_files || []);
  }, []);

  const bootstrap = useCallback(async (requestedConversationId?: string) => {
    try {
      const list = await fetchConversations();
      if (list.length) {
        setConversations(list);
        const targetId = requestedConversationId || list[0].id;
        await loadConversation(targetId);
      } else {
        const created = await createConversation('审计问答');
        setConversations([created]);
        setActive(created);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '会话加载失败');
    }
  }, [loadConversation]);

  const handleSubmit = useCallback(async (text: string, kbIds: string[] = selectedKbIds) => {
    let conversation = active;
    if (!conversation) {
      conversation = await createConversation(text.slice(0, 20));
      setActive(conversation);
      setConversations((items) => [conversation as Conversation, ...items]);
    }
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
      const result = await sendMessage(conversation.id, text, kbIds);
      const returnedUserMessage = result.user_message;
      setMessages((items) => {
        const nextItems = returnedUserMessage
          ? items.map((item) => (item.id === userMessage.id ? returnedUserMessage : item))
          : items;
        return [...nextItems, result.message];
      });
      setTempFiles([]);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '发送失败');
      setMessages((items) => items.filter((item) => item.id !== userMessage.id));
    } finally {
      setLoading(false);
    }
  }, [active, selectedKbIds, tempFiles]);

  useEffect(() => {
    bootstrap(requestedConversationId);
  }, [bootstrap, requestedConversationId]);

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

  const feedback = async (messageId: string, type: string) => {
    await sendFeedback(messageId, type);
    message.success('反馈已记录');
  };

  return (
    <div className="chat-page">
      <aside className="conversation-list">
        <Button
          type="primary"
          block
          onClick={async () => {
            const item = await createConversation('新会话');
            setConversations((items) => [item, ...items]);
            setActive(item);
            setMessages([]);
            setTempFiles([]);
            setSearchParams({ conversationId: item.id });
          }}
        >
          新建对话
        </Button>
        <List
          dataSource={conversations}
          renderItem={(item) => (
            <List.Item
              className={active?.id === item.id ? 'conversation active' : 'conversation'}
              onClick={() => {
                setSearchParams({ conversationId: item.id });
                loadConversation(item.id);
              }}
            >
              <Typography.Text ellipsis>{item.title}</Typography.Text>
            </List.Item>
          )}
        />
      </aside>
      <section className="chat-main">
        <div className="message-list">
          {!messages.length && <Empty description="输入问题开始审计问答" />}
          {messages.map((item) => (
            <Card key={item.id} className={`message-card ${item.role}`}>
              <Typography.Text strong>{item.role === 'user' ? '我' : '审计 AI 助手'}</Typography.Text>
              <Typography.Paragraph className="markdown-text">{item.content}</Typography.Paragraph>
              {item.attachments && item.attachments.length > 0 && (
                <div className="message-attachment-list">
                  {item.attachments.map((file) => (
                    <ChatAttachment key={file.id} file={file} compact />
                  ))}
                </div>
              )}
              {item.role === 'assistant' && (
                <Space className="message-actions">
                  <Button icon={<LikeOutlined />} onClick={() => feedback(item.id, 'like')} />
                  <Button icon={<DislikeOutlined />} onClick={() => feedback(item.id, 'dislike')} />
                  <Button icon={<WarningOutlined />} onClick={() => feedback(item.id, 'citation_error')} />
                  <Button icon={<ReloadOutlined />} onClick={() => feedback(item.id, 'regenerate')} />
                </Space>
              )}
            </Card>
          ))}
          {loading && <Spin tip="正在检索知识库并生成回答" />}
        </div>
        <div className="chat-composer">
          <div className="chat-kb-selector">
            <Typography.Text type="secondary">检索知识库</Typography.Text>
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
          {tempFiles.length > 0 && (
            <div className="chat-attachment-strip">
              {tempFiles.map((file) => (
                <ChatAttachment key={file.id} file={file} />
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
  const parsed = (rawKbIds || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (parsed.length) {
    return Array.from(new Set(parsed));
  }
  return fallbackKbId ? [fallbackKbId] : [];
}

function ChatAttachment({ file, compact = false }: { file: TempFile; compact?: boolean }) {
  const status = tempFileStatusMeta(file.status);
  return (
    <div className={`chat-attachment ${status.className} ${compact ? 'compact' : ''}`}>
      <PaperClipOutlined className="chat-attachment-icon" />
      <Typography.Text ellipsis className="chat-attachment-name">
        {file.file_name}
      </Typography.Text>
      <Tag icon={status.icon} color={status.color}>
        {status.label}
      </Tag>
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
