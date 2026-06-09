import {
  AuditOutlined,
  DatabaseOutlined,
  HistoryOutlined,
  HomeOutlined,
  MessageOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Menu } from 'antd';
import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { UserInfo } from '../api/auth';

type SidebarProps = {
  user?: UserInfo | null;
};

export default function Sidebar({ user }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const items = useMemo(() => {
    const base = [
      { key: '/', icon: <HomeOutlined />, label: '首页' },
      { key: '/chat', icon: <MessageOutlined />, label: 'AI 对话' },
      { key: '/kb', icon: <DatabaseOutlined />, label: '知识库' },
      { key: '/history', icon: <HistoryOutlined />, label: '历史记录' },
      { key: '/settings', icon: <SettingOutlined />, label: '设置' },
    ];
    if (user?.role === 'system_admin' || user?.role === 'audit_manager') {
      base.push({ key: '/admin', icon: <ToolOutlined />, label: '管理后台' });
    }
    return base;
  }, [user?.role]);

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <AuditOutlined />
      </div>
      <Menu
        mode="inline"
        selectedKeys={[location.pathname === '/' ? '/' : `/${location.pathname.split('/')[1]}`]}
        items={items}
        onClick={(event) => navigate(event.key)}
        className="sidebar-menu"
      />
    </aside>
  );
}

