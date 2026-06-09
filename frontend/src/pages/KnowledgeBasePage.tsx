import {
  AppstoreOutlined,
  BarsOutlined,
  DeleteOutlined,
  PlusOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { Button, Form, Input, message, Modal, Segmented, Space, Table, Tag, Tree, Typography } from 'antd';
import type { DataNode } from 'antd/es/tree';
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
import ChatInput from '../components/ChatInput';
import DocumentCard from '../components/DocumentCard';
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

  const treeData: DataNode[] = knowledgeBases.map((kb) => ({
    key: kb.id,
    title: (
      <Space size={6}>
        <span>{kb.name}</span>
        <Tag color={kb.visibility === 'shared' ? 'blue' : 'green'}>
          {kb.visibility === 'shared' ? '共享' : '个人'}
        </Tag>
      </Space>
    ),
  }));
  const filtered = useMemo(
    () => documents.filter((doc) => doc.file_name.includes(keyword) || doc.tags.join(',').includes(keyword)),
    [documents, keyword],
  );
  const selectedKb = useMemo(
    () => knowledgeBases.find((kb) => kb.id === selectedKbId),
    [knowledgeBases, selectedKbId],
  );

  return (
    <div className="kb-page">
      <aside className="kb-tree">
        <Tree
          treeData={treeData}
          selectedKeys={selectedKbId ? [selectedKbId] : []}
          onSelect={(keys) => {
            if (keys[0]) {
              setSelectedKbId(String(keys[0]));
            }
          }}
        />
      </aside>
      <section className="kb-main">
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
          {user?.role === 'system_admin' && (
            <Button icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建共享知识库
            </Button>
          )}
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
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
            上传
          </Button>
        </div>
        {view === 'card' ? (
          <div className="document-grid">
            {filtered.map((document) => (
              <DocumentCard key={document.id} document={document} />
            ))}
          </div>
        ) : (
          <Table
            rowKey="id"
            dataSource={filtered}
            pagination={{ pageSize: 8 }}
            columns={[
              { title: '文件名', dataIndex: 'file_name' },
              { title: '类型', dataIndex: 'file_ext', width: 90 },
              { title: '分类', dataIndex: 'department_category' },
              { title: '业务类型', dataIndex: 'business_type' },
              { title: '状态', dataIndex: 'status' },
              { title: '上传时间', dataIndex: 'created_at' },
            ]}
          />
        )}
        <div className="kb-bottom-input">
          <Typography.Text type="secondary">基于当前知识库提问</Typography.Text>
          <ChatInput
            onSubmit={(text) => {
              const params = new URLSearchParams({ query: text });
              if (selectedKbId) params.set('kbIds', selectedKbId);
              navigate(`/chat?${params.toString()}`);
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
        onUploaded={() => selectedKbId && fetchKbDocuments(selectedKbId).then(setDocuments)}
      />
      <Modal
        title="新建共享知识库"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={async () => {
          const values = await form.validateFields();
          try {
            await createKnowledgeBase({ ...values, visibility: 'shared' });
            message.success('共享知识库已创建');
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
        </Form>
      </Modal>
    </div>
  );
}
