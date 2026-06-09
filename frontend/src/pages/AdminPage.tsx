import { DatabaseOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Card, Descriptions, Form, Input, message, Modal, Select, Space, Tabs, Table, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import {
  createUser,
  fetchAuditLogs,
  fetchDatabaseOverview,
  fetchModelCallLogs,
  fetchTasks,
  fetchUsers,
  type DatabaseOverview,
  type RetrievalTestResult,
  testRetrieval,
  vacuumDatabase,
} from '../api/admin';
import { fetchKnowledgeBases, type KnowledgeBase } from '../api/kb';

export default function AdminPage() {
  const [users, setUsers] = useState<Record<string, unknown>[]>([]);
  const [logs, setLogs] = useState<Record<string, unknown>[]>([]);
  const [tasks, setTasks] = useState<Record<string, unknown>[]>([]);
  const [model, setModel] = useState<Record<string, unknown>>({});
  const [database, setDatabase] = useState<DatabaseOverview | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [retrievalResult, setRetrievalResult] = useState<RetrievalTestResult | null>(null);
  const [retrievalLoading, setRetrievalLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();
  const [retrievalForm] = Form.useForm<{ query: string; kb_id?: string; top_k: number }>();

  const loadUsers = () => fetchUsers().then(setUsers).catch(() => setUsers([]));
  const loadDatabase = () => fetchDatabaseOverview().then(setDatabase).catch(() => setDatabase(null));

  useEffect(() => {
    loadUsers();
    fetchAuditLogs().then(setLogs).catch(() => setLogs([]));
    fetchTasks().then(setTasks).catch(() => setTasks([]));
    fetchModelCallLogs().then(setModel).catch(() => setModel({}));
    fetchKnowledgeBases().then(setKnowledgeBases).catch(() => setKnowledgeBases([]));
    loadDatabase();
  }, []);

  return (
    <Card className="admin-card">
      <Tabs
        items={[
          {
            key: 'users',
            label: '用户列表',
            children: (
              <Space direction="vertical" className="full-width">
                <Button type="primary" onClick={() => setCreateOpen(true)}>
                  新建账号
                </Button>
                <Table
                  rowKey="id"
                  dataSource={users}
                  columns={[
                    { title: '账号', dataIndex: 'username' },
                    { title: '姓名', dataIndex: 'display_name' },
                    { title: '角色', dataIndex: 'role' },
                    { title: '部门', dataIndex: 'department' },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: 'logs',
            label: '操作日志',
            children: (
              <Table
                rowKey="id"
                dataSource={logs}
                columns={[
                  { title: '操作', dataIndex: 'action' },
                  { title: '用户', dataIndex: 'user_id' },
                  { title: '对象', dataIndex: 'target_type' },
                  { title: '状态', dataIndex: 'status' },
                  { title: '时间', dataIndex: 'created_at' },
                ]}
              />
            ),
          },
          {
            key: 'tasks',
            label: '文档处理任务',
            children: (
              <Table
                rowKey="document_id"
                dataSource={tasks}
                columns={[
                  { title: '文件', dataIndex: 'file_name' },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    render: (status: string) => <Tag>{status}</Tag>,
                  },
                  { title: '错误', dataIndex: 'error_message' },
                  { title: '更新时间', dataIndex: 'updated_at' },
                ]}
              />
            ),
          },
          {
            key: 'models',
            label: '模型服务状态',
            children: (
              <Table
                rowKey="key"
                pagination={false}
                dataSource={Object.entries((model.status || {}) as Record<string, unknown>).map(([key, value]) => ({
                  key,
                  value: JSON.stringify(value),
                }))}
                columns={[
                  { title: '服务', dataIndex: 'key' },
                  { title: '状态', dataIndex: 'value' },
                ]}
              />
            ),
          },
          {
            key: 'database',
            label: '数据库管理',
            children: (
              <Space direction="vertical" className="full-width">
                <Space wrap>
                  <Button icon={<ReloadOutlined />} onClick={loadDatabase}>
                    刷新
                  </Button>
                  <Button
                    icon={<DatabaseOutlined />}
                    onClick={async () => {
                      try {
                        const result = await vacuumDatabase();
                        message.success(result.message || '数据库整理完成');
                        loadDatabase();
                      } catch (error) {
                        message.error(error instanceof Error ? error.message : '数据库整理失败');
                      }
                    }}
                  >
                    整理数据库
                  </Button>
                </Space>
                <Descriptions column={2} bordered size="small">
                  <Descriptions.Item label="数据库类型">{database?.dialect || '-'}</Descriptions.Item>
                  <Descriptions.Item label="表数量">{database?.tables.length || 0}</Descriptions.Item>
                  {Object.entries(database?.stats || {}).map(([key, value]) => (
                    <Descriptions.Item key={key} label={key}>
                      {value}
                    </Descriptions.Item>
                  ))}
                </Descriptions>
                <Table
                  rowKey="table"
                  dataSource={database?.tables || []}
                  pagination={{ pageSize: 8 }}
                  columns={[
                    { title: '表名', dataIndex: 'table' },
                    { title: '行数', dataIndex: 'rows', width: 160 },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: 'retrieval',
            label: '检索测试',
            children: (
              <Space direction="vertical" className="full-width">
                <Form
                  form={retrievalForm}
                  layout="inline"
                  initialValues={{ top_k: 6 }}
                  onFinish={async (values) => {
                    setRetrievalLoading(true);
                    try {
                      const result = await testRetrieval({
                        query: values.query,
                        kb_id: values.kb_id || null,
                        top_k: values.top_k || 6,
                      });
                      setRetrievalResult(result);
                    } catch (error) {
                      message.error(error instanceof Error ? error.message : '检索测试失败');
                    } finally {
                      setRetrievalLoading(false);
                    }
                  }}
                >
                  <Form.Item name="query" rules={[{ required: true, message: '请输入测试问题' }]}>
                    <Input style={{ width: 320 }} placeholder="输入一个审计知识库问题" />
                  </Form.Item>
                  <Form.Item name="kb_id">
                    <Select
                      allowClear
                      style={{ width: 220 }}
                      placeholder="全部可见知识库"
                      options={knowledgeBases.map((kb) => ({
                        value: kb.id,
                        label: `${kb.name}（${kb.visibility === 'shared' ? '共享' : '个人'}）`,
                      }))}
                    />
                  </Form.Item>
                  <Form.Item name="top_k">
                    <Select
                      style={{ width: 100 }}
                      options={[3, 6, 8, 12].map((value) => ({ value, label: `Top ${value}` }))}
                    />
                  </Form.Item>
                  <Button type="primary" icon={<SearchOutlined />} htmlType="submit" loading={retrievalLoading}>
                    测试
                  </Button>
                </Form>

                {retrievalResult ? (
                  <Space direction="vertical" className="full-width">
                    <Descriptions column={2} bordered size="small">
                      <Descriptions.Item label="问题">{retrievalResult.query}</Descriptions.Item>
                      <Descriptions.Item label="命中数">{retrievalResult.evidence.length}</Descriptions.Item>
                      <Descriptions.Item label="过滤条件">
                        {JSON.stringify(retrievalResult.trace.filters || {})}
                      </Descriptions.Item>
                      <Descriptions.Item label="向量索引">
                        {JSON.stringify(retrievalResult.vector_index || {})}
                      </Descriptions.Item>
                    </Descriptions>

                    <Typography.Text strong>最终上下文</Typography.Text>
                    <Table
                      rowKey={(row) => row.chunk_id || row.parent_chunk_id || row.document_id || row.file_name || 'chunk'}
                      dataSource={retrievalResult.evidence}
                      pagination={{ pageSize: 5 }}
                      columns={[
                        { title: '文件', dataIndex: 'file_name', width: 180 },
                        { title: '类型', dataIndex: 'chunk_type', width: 90 },
                        { title: '位置', render: (_, row) => row.heading_path || row.sheet_name || row.page_number || '-' },
                        {
                          title: '片段',
                          render: (_, row) => (
                            <Typography.Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: 0 }}>
                              {row.context_text || row.text}
                            </Typography.Paragraph>
                          ),
                        },
                        { title: 'RRF', dataIndex: 'rrf_score', width: 90, render: (value) => formatScore(value) },
                      ]}
                    />

                    <Typography.Text strong>召回链路</Typography.Text>
                    <Tabs
                      items={[
                        { key: 'vector', label: 'Vector', children: <TraceTable data={retrievalResult.trace.vector} /> },
                        { key: 'keyword', label: 'Keyword', children: <TraceTable data={retrievalResult.trace.keyword} /> },
                        { key: 'fused', label: 'Fused', children: <TraceTable data={retrievalResult.trace.fused} /> },
                      ]}
                    />
                    {Object.keys(retrievalResult.trace.errors || {}).length ? (
                      <Typography.Text type="danger">
                        {JSON.stringify(retrievalResult.trace.errors)}
                      </Typography.Text>
                    ) : null}
                  </Space>
                ) : (
                  <Typography.Text type="secondary">输入问题后可以查看 dense、keyword 和融合后的召回结果。</Typography.Text>
                )}
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title="新建账号"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={async () => {
          const values = await form.validateFields();
          try {
            await createUser(values);
            message.success('账号已创建');
            setCreateOpen(false);
            form.resetFields();
            loadUsers();
          } catch (error) {
            message.error(error instanceof Error ? error.message : '创建失败');
          }
        }}
      >
        <Form form={form} layout="vertical" initialValues={{ role: 'auditor', department: '审计处' }}>
          <Form.Item name="username" label="账号" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="display_name" label="姓名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'auditor', label: 'auditor' },
                { value: 'audit_manager', label: 'audit_manager' },
                { value: 'system_admin', label: 'system_admin' },
              ]}
            />
          </Form.Item>
          <Form.Item name="department" label="部门" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

function TraceTable({ data }: { data: NonNullable<RetrievalTestResult['trace']>['vector'] }) {
  return (
    <Table
      rowKey={(row) =>
        `${row.source || 'trace'}-${row.chunk_id || row.document_id || 'item'}-${row.rrf_score || row.score || 0}`
      }
      dataSource={data}
      pagination={{ pageSize: 8 }}
      columns={[
        { title: 'chunk_id', dataIndex: 'chunk_id' },
        { title: 'document_id', dataIndex: 'document_id' },
        { title: 'source', dataIndex: 'source', width: 100 },
        { title: 'score', dataIndex: 'score', width: 110, render: (value) => formatScore(value) },
        { title: 'rrf', dataIndex: 'rrf_score', width: 110, render: (value) => formatScore(value) },
      ]}
    />
  );
}

function formatScore(value: unknown) {
  return typeof value === 'number' ? value.toFixed(4) : '-';
}
