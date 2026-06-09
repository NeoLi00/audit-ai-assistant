import { FileDoneOutlined, FileTextOutlined } from '@ant-design/icons';
import { Card, Space, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
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

type DocumentCardProps = {
  document: DocumentItem;
};

export default function DocumentCard({ document }: DocumentCardProps) {
  const navigate = useNavigate();

  return (
    <Card className="document-card" hoverable onClick={() => navigate(`/documents/${document.id}`)}>
      <Space align="start">
        <div className="document-icon">
          {document.status === 'indexed' ? <FileDoneOutlined /> : <FileTextOutlined />}
        </div>
        <Space direction="vertical" size={6} className="document-card-body">
          <Typography.Text strong ellipsis>
            {document.file_name}
          </Typography.Text>
          <Space size={6} wrap>
            <Tag>{document.file_ext}</Tag>
            <Tag color="geekblue">{document.department_category}</Tag>
            <Tag color="cyan">{document.business_type}</Tag>
            <Tag color={STATUS_COLOR[document.status] || 'default'}>{document.status}</Tag>
          </Space>
          <Typography.Text type="secondary">
            版本 {document.version} · {document.is_current_version ? '当前版本' : '历史版本'}
          </Typography.Text>
        </Space>
      </Space>
    </Card>
  );
}

