import {
  AppstoreOutlined,
  BarsOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
  MessageOutlined,
  PlusOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { Button, Form, Input, message, Modal, Progress, Radio, Segmented, Space, Table, Tag, Tooltip, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchMe, type UserInfo } from '../api/auth';
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  fetchKbDocuments,
  fetchKnowledgeBases,
  type DocumentItem,
  type KnowledgeBase,
} from '../api/kb';
import { deleteDocument } from '../api/documents';
import ChatInput from '../components/ChatInput';
import DocumentCard from '../components/DocumentCard';
import {
  documentProgressColor,
  documentProgressPercent,
  documentProgressStage,
  documentProgressStatus,
  documentStatusColor,
  documentStatusDetail,
  documentStatusLabel,
} from '../components/documentStatus';
import UploadModal from '../components/UploadModal';

export default function KnowledgeBasePage() {
  const navigate = useNavigate();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<string>();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [keyword, setKeyword] = useState('');
  const [view, setView] = useState<'card' | 'list'>('card');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [form] = Form.useForm();

  const loadKnowledgeBases = () => {
    return fetchKnowledgeBases().then((items) => {
      setKnowledgeBases(items);
      setSelectedKbId((current) => {
        if (current && items.some((item) => item.id === current)) {
          return current;
        }
        return items[0]?.id;
      });
    });
  };

  useEffect(() => {
    fetchMe().then(setUser).catch(() => setUser(null));
    loadKnowledgeBases();
  }, []);

  useEffect(() => {
    if (selectedKbId) {
      fetchKbDocuments(selectedKbId).then(setDocuments).catch(() => setDocuments([]));
    }
  }, [selectedKbId]);

  const hasProcessingDocuments = documents.some((document) =>
    ['uploaded', 'parsing', 'chunking', 'embedding'].includes(document.status),
  );
  useEffect(() => {
    if (!selectedKbId || !hasProcessingDocuments) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      fetchKbDocuments(selectedKbId).then(setDocuments).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [hasProcessingDocuments, selectedKbId]);

  const filtered = useMemo(
    () => documents.filter((doc) => doc.file_name.includes(keyword) || doc.tags.join(',').includes(keyword)),
    [documents, keyword],
  );
  const selectedKb = useMemo(
    () => knowledgeBases.find((kb) => kb.id === selectedKbId),
    [knowledgeBases, selectedKbId],
  );
  const canDeleteDocument = (document: DocumentItem) =>
    user?.role === 'system_admin' ||
    (document.visibility === 'private' && (document.uploaded_by === user?.id || selectedKb?.created_by === user?.id));

  const refreshDocuments = () => {
    if (!selectedKbId) return Promise.resolve();
    return fetchKbDocuments(selectedKbId).then(setDocuments).catch(() => setDocuments([]));
  };

  const confirmDeleteDocument = (document: DocumentItem) => {
    Modal.confirm({
      title: `删除文件：${document.file_name}`,
      content: '文件、解析块、chunk、关键词索引和向量索引都会一起删除。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDocument(document.id);
          message.success('文件已删除');
          await refreshDocuments();
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败');
        }
      },
    });
  };

  const openKnowledgeBaseChat = () => {
    if (!selectedKb) return;
    const params = new URLSearchParams({
      scope: 'kb',
      kbIds: selectedKb.id,
      scopeLabel: selectedKb.name,
      launchId: newLaunchId('kb'),
    });
    navigate(`/?${params.toString()}`);
  };

  const openDocumentChat = (document: DocumentItem) => {
    const params = new URLSearchParams({
      scope: 'document',
      scopeLabel: document.file_name,
      documentIds: document.id,
      launchId: newLaunchId('doc'),
    });
    if (document.kb_id) params.set('kbIds', document.kb_id);
    navigate(`/?${params.toString()}`);
  };

  return (
    <div className="kb-page">
      <aside className="kb-tree">
        <div className="kb-sidebar-head">
          <div>
            <Typography.Title level={5}>知识库</Typography.Title>
            <Typography.Text type="secondary">{knowledgeBases.length} 个资料库</Typography.Text>
          </div>
          {user?.role === 'system_admin' && (
            <Tooltip title="新建知识库">
              <Button type="text" icon={<PlusOutlined />} aria-label="新建知识库" onClick={() => setCreateOpen(true)} />
            </Tooltip>
          )}
        </div>
        <div className="kb-list" role="list">
          {knowledgeBases.map((kb) => (
            <button
              key={kb.id}
              type="button"
              className={selectedKbId === kb.id ? 'kb-list-item active' : 'kb-list-item'}
              onClick={() => setSelectedKbId(kb.id)}
            >
              <span className="kb-list-icon">
                <FolderOpenOutlined />
              </span>
              <span className="kb-list-copy">
                <span className="kb-list-name">{kb.name}</span>
                <span className="kb-list-meta">{kb.visibility === 'shared' ? '共享知识库' : '个人知识库'}</span>
              </span>
            </button>
          ))}
        </div>
      </aside>
      <section className="kb-main">
        <div className="kb-hero">
          <div className="kb-hero-copy">
            <Space size={8} wrap>
              <Tag color={selectedKb?.visibility === 'shared' ? 'blue' : 'green'}>
                {selectedKb?.visibility === 'shared' ? '共享知识库' : '个人知识库'}
              </Tag>
              <Typography.Text type="secondary">{filtered.length} / {documents.length} 个文件</Typography.Text>
            </Space>
            <Typography.Title level={3}>{selectedKb?.name || '请选择知识库'}</Typography.Title>
            <Typography.Paragraph type="secondary">
              {selectedKb?.description || '上传审计底稿、制度、合同和报表后，可在对话中作为可检索材料使用。'}
            </Typography.Paragraph>
          </div>
          <Space wrap className="kb-hero-actions">
            {selectedKb && (
              <Button icon={<MessageOutlined />} onClick={openKnowledgeBaseChat}>
                围绕知识库对话
              </Button>
            )}
            <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
              上传文件
            </Button>
          </Space>
        </div>
        <div className="kb-toolbar">
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索文件名或标签"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <Segmented
            value={view}
            options={[
              { value: 'card', icon: <AppstoreOutlined /> },
              { value: 'list', icon: <BarsOutlined /> },
            ]}
            onChange={(value) => setView(value as 'card' | 'list')}
          />
          {user?.role === 'system_admin' && selectedKb && (
            <Button
              danger
              icon={<DeleteOutlined />}
              onClick={() => {
                Modal.confirm({
                  title: `删除知识库：${selectedKb.name}`,
                  content: '库内文档、解析块和向量切片会一起删除。',
                  okText: '删除',
                  okButtonProps: { danger: true },
                  cancelText: '取消',
                  onOk: async () => {
                    try {
                      await deleteKnowledgeBase(selectedKb.id);
                      message.success('知识库已删除');
                      setDocuments([]);
                      await loadKnowledgeBases();
                    } catch (error) {
                      message.error(error instanceof Error ? error.message : '删除失败');
                    }
                  },
                });
              }}
            >
              删除知识库
            </Button>
          )}
        </div>
        {view === 'card' ? (
          <div className="document-grid">
            {filtered.map((document) => (
              <DocumentCard
                key={document.id}
                document={document}
                onChat={openDocumentChat}
                onDelete={canDeleteDocument(document) ? confirmDeleteDocument : undefined}
              />
            ))}
          </div>
        ) : (
          <Table
            rowKey="id"
            dataSource={filtered}
            pagination={{ pageSize: 8 }}
            scroll={{ x: 920 }}
            columns={[
              { title: '文件名', dataIndex: 'file_name', ellipsis: true },
              { title: '类型', dataIndex: 'file_ext', width: 90 },
              { title: '分类', dataIndex: 'department_category', ellipsis: true },
              { title: '业务类型', dataIndex: 'business_type', ellipsis: true },
              {
                title: '状态',
                dataIndex: 'status',
                width: 220,
                render: (_, document: DocumentItem) => {
                  const detail = documentStatusDetail(document);
                  const showDetail = detail && !['indexed', 'ready'].includes(document.status);
                  const showProgress = !['indexed', 'ready'].includes(document.status);
                  return (
                    <Space direction="vertical" size={2} className="document-status-cell">
                      <Tooltip title={detail || undefined}>
                        <Tag color={documentStatusColor(document.status)}>{documentStatusLabel(document.status)}</Tag>
                      </Tooltip>
                      {showDetail ? (
                        <Typography.Text type="secondary" ellipsis={{ tooltip: detail }}>
                          {detail}
                        </Typography.Text>
                      ) : null}
                      {showProgress ? (
                        <div className="document-progress table-progress">
                          <div className="document-progress-label">
                            <Typography.Text type="secondary">{documentProgressStage(document)}</Typography.Text>
                            <Typography.Text type="secondary">{documentProgressPercent(document)}%</Typography.Text>
                          </div>
                          <Progress
                            percent={documentProgressPercent(document)}
                            showInfo={false}
                            size="small"
                            status={documentProgressStatus(document.status)}
                            strokeColor={documentProgressColor(document.status)}
                          />
                        </div>
                      ) : null}
                    </Space>
                  );
                },
              },
              { title: '上传时间', dataIndex: 'created_at', width: 190 },
              {
                title: '操作',
                width: 180,
                render: (_, document: DocumentItem) =>
                  (
                    <Space size={4}>
                      <Button type="link" icon={<MessageOutlined />} onClick={() => openDocumentChat(document)}>
                        对话
                      </Button>
                      {canDeleteDocument(document) ? (
                        <Button danger type="link" icon={<DeleteOutlined />} onClick={() => confirmDeleteDocument(document)}>
                          删除
                        </Button>
                      ) : null}
                    </Space>
                  ),
              },
            ]}
          />
        )}
        <div className="kb-bottom-input">
          <Typography.Text type="secondary">基于当前知识库提问</Typography.Text>
          <ChatInput
            onSubmit={(text) => {
              const params = new URLSearchParams({ query: text, launchId: newLaunchId('kb-question') });
              if (selectedKbId) params.set('kbIds', selectedKbId);
              if (selectedKb) {
                params.set('scope', 'kb');
                params.set('scopeLabel', selectedKb.name);
              }
              navigate(`/?${params.toString()}`);
            }}
          />
        </div>
      </section>
      <UploadModal
        open={uploadOpen}
        knowledgeBases={
          user?.role === 'system_admin'
            ? knowledgeBases
            : knowledgeBases.filter((kb) => kb.visibility === 'private' && kb.created_by === user?.id)
        }
        selectedKbId={selectedKbId}
        onClose={() => setUploadOpen(false)}
        onUploaded={refreshDocuments}
      />
      <Modal
        title="新建知识库"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={async () => {
          const values = await form.validateFields();
          try {
            await createKnowledgeBase({ ...values, visibility: values.visibility || 'private' });
            message.success('知识库已创建');
            setCreateOpen(false);
            form.resetFields();
            await loadKnowledgeBases();
          } catch (error) {
            message.error(error instanceof Error ? error.message : '创建失败');
          }
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="知识库名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：2026 年招采专项审计资料" />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} />
          </Form.Item>
          <Form.Item name="visibility" label="类型" initialValue="private">
            <Radio.Group
              options={[
                { label: '个人知识库', value: 'private' },
                { label: '共享知识库', value: 'shared' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function newLaunchId(prefix: string) {
  if (globalThis.crypto?.randomUUID) {
    return `${prefix}-${globalThis.crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
