import { FileSearchOutlined } from '@ant-design/icons';
import { Card, Space, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import type { Citation } from '../api/chat';

type CitationCardProps = {
  citation: Citation;
};

export default function CitationCard({ citation }: CitationCardProps) {
  const navigate = useNavigate();
  const location =
    citation.page_number ?? citation.sheet_name ?? citation.heading_path ?? '未标注位置';

  return (
    <Card
      size="small"
      className="citation-card"
      hoverable
      onClick={() => navigate(`/documents/${citation.document_id}?chunkId=${citation.chunk_id}`)}
    >
      <Space direction="vertical" size={4}>
        <Space>
          <FileSearchOutlined />
          <Typography.Text strong>{citation.file_name || '未知文件'}</Typography.Text>
          <Tag color="blue">{String(location)}</Tag>
        </Space>
        <Typography.Paragraph ellipsis={{ rows: 2 }} className="citation-quote">
          {citation.quote}
        </Typography.Paragraph>
      </Space>
    </Card>
  );
}

