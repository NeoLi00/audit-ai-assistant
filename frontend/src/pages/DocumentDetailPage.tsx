import { DeleteOutlined, SaveOutlined, SyncOutlined } from '@ant-design/icons';
import { Button, Card, Descriptions, Empty, Input, message, Modal, Space, Tag, Typography } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { fetchMe, type UserInfo } from '../api/auth';
import {
  deleteDocument,
  fetchDocument,
  fetchDocumentBlocks,
  fetchDocumentChunks,
  submitOcrCorrection,
  type DocumentBlock,
  type DocumentChunk,
} from '../api/documents';
import type { DocumentItem } from '../api/kb';

export default function DocumentDetailPage() {
  const navigate = useNavigate();
  const { documentId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const chunkId = searchParams.get('chunkId');
  const [document, setDocument] = useState<DocumentItem | null>(null);
  const [blocks, setBlocks] = useState<DocumentBlock[]>([]);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [correction, setCorrection] = useState('');
  const [user, setUser] = useState<UserInfo | null>(null);

  const load = useCallback(async () => {
    const [doc, blockItems, chunkItems] = await Promise.all([
      fetchDocument(documentId),
      fetchDocumentBlocks(documentId),
      fetchDocumentChunks(documentId),
    ]);
    setDocument(doc);
    setBlocks(blockItems);
    setChunks(chunkItems);
  }, [documentId]);

  useEffect(() => {
    load().catch(() => message.error('文档加载失败'));
  }, [load]);

  useEffect(() => {
    fetchMe().then(setUser).catch(() => setUser(null));
  }, []);

  const highlightedChunk = useMemo(() => chunks.find((chunk) => chunk.id === chunkId), [chunks, chunkId]);
  const canDeleteDocument =
    document &&
    (user?.role === 'system_admin' || (document.visibility === 'private' && document.uploaded_by === user?.id));

  if (!document) return <Empty description="文档不存在或加载中" />;

  return (
    <div className="document-detail">
      <Card>
        <Space direction="vertical" className="full-width">
          <Space className="full-width" style={{ justifyContent: 'space-between' }}>
            <Typography.Title level={5} style={{ margin: 0 }}>
              {document.file_name}
            </Typography.Title>
            {canDeleteDocument ? (
              <Button
                danger
                icon={<DeleteOutlined />}
                onClick={() => {
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
                        navigate('/kb');
                      } catch (error) {
                        message.error(error instanceof Error ? error.message : '删除失败');
                      }
                    },
                  });
                }}
              >
                删除文件
              </Button>
            ) : null}
          </Space>
          <Descriptions column={3}>
            <Descriptions.Item label="类型">{document.file_ext}</Descriptions.Item>
            <Descriptions.Item label="分类">{document.department_category}</Descriptions.Item>
            <Descriptions.Item label="业务类型">{document.business_type}</Descriptions.Item>
            <Descriptions.Item label="标签">{document.tags.join(', ') || '-'}</Descriptions.Item>
            <Descriptions.Item label="版本">{document.version}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={document.status === 'indexed' ? 'green' : document.status === 'need_review' ? 'gold' : 'blue'}>
                {document.status}
              </Tag>
            </Descriptions.Item>
          </Descriptions>
        </Space>
      </Card>
      {highlightedChunk && (
        <Card className="highlight-card" title="引用命中片段">
          <Typography.Paragraph>{highlightedChunk.text}</Typography.Paragraph>
        </Card>
      )}
      <Card title="原文预览">
        <Space direction="vertical" className="full-width">
          {blocks.map((block) => (
            <div key={block.id} className="document-block">
              <Space wrap>
                <Tag>{block.block_type}</Tag>
                {block.page_number && <Tag color="blue">第 {block.page_number} 页</Tag>}
                {block.sheet_name && <Tag color="cyan">{block.sheet_name}</Tag>}
                {block.heading_path && <Tag color="geekblue">{block.heading_path}</Tag>}
              </Space>
              <Typography.Paragraph>{block.text}</Typography.Paragraph>
            </div>
          ))}
        </Space>
      </Card>
      {document.status === 'need_review' && (
        <Card title="OCR 人工校对">
          <Space direction="vertical" className="full-width">
            <Input.TextArea
              value={correction}
              onChange={(event) => setCorrection(event.target.value)}
              autoSize={{ minRows: 5, maxRows: 12 }}
              placeholder="输入校对后的 OCR 文本"
            />
            <Space>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={async () => {
                  await submitOcrCorrection(document.id, correction);
                  message.success('校对文本已保存并重新入库');
                  load();
                }}
              >
                保存并重新入库
              </Button>
              <Button icon={<SyncOutlined />} onClick={load}>
                刷新
              </Button>
            </Space>
          </Space>
        </Card>
      )}
    </div>
  );
}
