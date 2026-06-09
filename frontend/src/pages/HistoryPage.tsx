import { Card, List, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchConversations, type Conversation } from '../api/chat';

export default function HistoryPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Conversation[]>([]);

  useEffect(() => {
    fetchConversations().then(setItems).catch(() => setItems([]));
  }, []);

  return (
    <Card title="历史会话">
      <List
        dataSource={items}
        renderItem={(item) => (
          <List.Item className="history-item" onClick={() => navigate(`/chat?conversationId=${item.id}`)}>
            <List.Item.Meta title={item.title} description={item.updated_at} />
          </List.Item>
        )}
        locale={{ emptyText: <Typography.Text type="secondary">暂无会话</Typography.Text> }}
      />
    </Card>
  );
}
