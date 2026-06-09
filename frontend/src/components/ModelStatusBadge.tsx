import { ApiOutlined, CloudSyncOutlined } from '@ant-design/icons';
import { Space, Tag, Tooltip } from 'antd';
import { useEffect, useState } from 'react';
import { fetchModelHealth } from '../api/admin';

type Health = {
  llm?: { provider?: string; model?: string; base_url_configured?: boolean };
  embedding?: { provider?: string; model?: string; dimension?: number; base_url_configured?: boolean };
};

export default function ModelStatusBadge() {
  const [health, setHealth] = useState<Health>({});

  useEffect(() => {
    fetchModelHealth().then((data) => setHealth(data as Health)).catch(() => setHealth({}));
  }, []);

  const llmMock = health.llm?.provider === 'mock';
  const embedMock = health.embedding?.provider === 'mock';

  return (
    <Space size={6} wrap>
      <Tooltip title={health.llm?.model || 'LLM 状态'}>
        <Tag icon={<ApiOutlined />} color={llmMock ? 'gold' : 'blue'}>
          LLM {llmMock ? 'Mock' : '在线'}
        </Tag>
      </Tooltip>
      <Tooltip title={health.embedding?.model || 'Embedding 状态'}>
        <Tag icon={<CloudSyncOutlined />} color={embedMock ? 'gold' : 'green'}>
          Embedding {embedMock ? 'Mock' : '在线'}
        </Tag>
      </Tooltip>
    </Space>
  );
}

