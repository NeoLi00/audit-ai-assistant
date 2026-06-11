import {
  AuditOutlined,
  DatabaseOutlined,
  HomeOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Button, Tooltip, Typography } from 'antd';
import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { UserInfo } from '../api/auth';

type SidebarProps = {
  user?: UserInfo | null;
  onLogout?: () => void;
  collapsed?: boolean;
  onToggle?: () => void;
};

export default function Sidebar({ user, onLogout, collapsed = false, onToggle }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const selectedRoute = location.pathname === '/' ? '/' : `/${location.pathname.split('/')[1]}`;
  const items = useMemo(() => {
    const base = [
      { key: '/', icon: <HomeOutlined />, label: '工作台' },
      { key: '/kb', icon: <DatabaseOutlined />, label: '知识库' },
      { key: '/settings', icon: <SettingOutlined />, label: '设置' },
    ];
    if (user?.role === 'system_admin' || user?.role === 'audit_manager') {
      base.push({ key: '/admin', icon: <ToolOutlined />, label: '管理后台' });
    }
    return base;
  }, [user?.role]);

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="workspace-rail-head">
        <div className="workspace-brand">
          <span className="workspace-brand-icon">
            <AuditOutlined />
          </span>
          <Typography.Title level={5} className="workspace-panel-title">
            审计 AI 助手
          </Typography.Title>
        </div>
        <Tooltip title={collapsed ? '展开侧边栏' : '收起侧边栏'}>
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
            onClick={onToggle}
          />
        </Tooltip>
      </div>
      <div className="workspace-quick-actions">
        <Button className="workspace-action-row" type="text" icon={<PlusOutlined />} onClick={() => navigate('/')}>
          新对话
        </Button>
      </div>
      <nav className="workspace-nav sidebar-nav" aria-label="主导航">
        {items.map((item) => (
          <button
            key={item.key}
            type="button"
            className={selectedRoute === item.key ? 'workspace-nav-item active' : 'workspace-nav-item'}
            onClick={() => navigate(item.key)}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-spacer" />
      {user && (
        <div className="workspace-user-footer">
          <div className="workspace-user-chip">
            <span className="workspace-user-avatar">{user.display_name.slice(0, 1).toUpperCase()}</span>
            <span className="workspace-user-copy">
              <span className="workspace-user-name">{user.display_name}</span>
              <span className="workspace-user-role">{userSubtitle(user)}</span>
            </span>
            {onLogout && (
              <Tooltip title="退出">
                <Button type="text" size="small" icon={<LogoutOutlined />} aria-label="退出" onClick={onLogout} />
              </Tooltip>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    system_admin: '系统管理员',
    audit_manager: '审计管理员',
    auditor: '审计人员',
  };
  return labels[role] || role;
}

function userSubtitle(user: UserInfo) {
  const role = roleLabel(user.role);
  if (user.display_name === role) {
    return user.department || role;
  }
  return role;
}
