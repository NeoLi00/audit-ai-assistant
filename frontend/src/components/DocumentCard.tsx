import { DeleteOutlined, FileDoneOutlined, FileTextOutlined, MessageOutlined } from '@ant-design/icons';
import { Button, Card, Progress, Space, Tag, Tooltip, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import type { DocumentItem } from '../api/kb';
import {
  documentProgressColor,
  documentProgressPercent,
  documentProgressStage,
  documentProgressStatus,
  documentStatusColor,
  documentStatusDetail,
  documentStatusLabel,
} from './documentStatus';

type DocumentCardProps = {
  document: DocumentItem;
  onDelete?: (document: DocumentItem) => void;
  onChat?: (document: DocumentItem) => void;
};

export default function DocumentCard({ document, onDelete, onChat }: DocumentCardProps) {
  const navigate = useNavigate();
  const detail = documentStatusDetail(document);
  const showDetail = detail && !['indexed', 'ready'].includes(document.status);
  const showProgress = !['indexed', 'ready'].includes(document.status);

  return (
    <Card className="document-card" hoverable onClick={() => navigate(`/documents/${document.id}`)}>
      <div className="document-card-layout">
        <div className="document-icon">
          {document.status === 'indexed' ? <FileDoneOutlined /> : <FileTextOutlined />}
        </div>
        <div className="document-card-body">
          <Typography.Text strong ellipsis={{ tooltip: document.file_name }} className="document-card-title">
            {document.file_name}
          </Typography.Text>
          <Space size={6} wrap className="document-card-tags">
            <Tag>{document.file_ext}</Tag>
            <Tag color="geekblue">{document.department_category}</Tag>
            <Tag color="cyan">{document.business_type}</Tag>
            <Tooltip title={detail || undefined}>
              <Tag color={documentStatusColor(document.status)}>{documentStatusLabel(document.status)}</Tag>
            </Tooltip>
          </Space>
          <Typography.Text type="secondary" className="document-card-meta">
            版本 {document.version} · {document.is_current_version ? '当前版本' : '历史版本'}
          </Typography.Text>
          {showDetail ? (
            <Typography.Text type="secondary" className="document-card-status-detail" ellipsis={{ tooltip: detail }}>
              {detail}
            </Typography.Text>
          ) : null}
          {showProgress ? (
            <div className="document-progress">
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
        </div>
        <Space size={2} className="document-card-actions">
          {onChat ? (
            <Tooltip title="围绕文件对话">
              <Button
                type="text"
                icon={<MessageOutlined />}
                aria-label="围绕文件对话"
                onClick={(event) => {
                  event.stopPropagation();
                  onChat(document);
                }}
              />
            </Tooltip>
          ) : null}
          {onDelete ? (
            <Tooltip title="删除文件">
              <Button
                danger
                type="text"
                icon={<DeleteOutlined />}
                aria-label="删除文件"
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(document);
                }}
              />
            </Tooltip>
          ) : null}
        </Space>
      </div>
    </Card>
  );
}
