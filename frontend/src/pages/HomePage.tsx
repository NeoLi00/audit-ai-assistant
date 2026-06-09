import {
  AuditOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { Select, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchKnowledgeBases, type KnowledgeBase } from '../api/kb';
import ChatInput from '../components/ChatInput';
import ModelStatusBadge from '../components/ModelStatusBadge';

export default function HomePage() {
  const navigate = useNavigate();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [kbIds, setKbIds] = useState<string[]>([]);

  useEffect(() => {
    fetchKnowledgeBases()
      .then((items) => {
        setKnowledgeBases(items);
        setKbIds(items[0]?.id ? [items[0].id] : []);
      })
      .catch(() => undefined);
  }, []);

  const goChat = (query: string) => {
    const params = new URLSearchParams({ query });
    if (kbIds.length) params.set('kbIds', kbIds.join(','));
    navigate(`/chat?${params.toString()}`);
  };

  return (
    <div className="home-page">
      <section className="home-hero">
        <div className="home-logo">
          <AuditOutlined />
        </div>
        <Typography.Title className="home-title">审计 AI 助手</Typography.Title>
        <Typography.Paragraph className="home-subtitle">
          基于本地知识库的审计问答与文件分析平台
        </Typography.Paragraph>
        <div className="home-controls">
          <Select
            mode="multiple"
            suffixIcon={<DatabaseOutlined />}
            placeholder="选择一个或多个知识库"
            value={kbIds}
            onChange={setKbIds}
            maxTagCount="responsive"
            options={knowledgeBases.map((kb) => ({
              value: kb.id,
              label: `${kb.name}（${kb.visibility === 'shared' ? '共享' : '个人'}）`,
            }))}
          />
          <ModelStatusBadge />
        </div>
        <div className="home-input">
          <ChatInput
            onSubmit={(text) => goChat(text)}
            onUploadClick={() => navigate('/chat?upload=1')}
          />
        </div>
      </section>
    </div>
  );
}
