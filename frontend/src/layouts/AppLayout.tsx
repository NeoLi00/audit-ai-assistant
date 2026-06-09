import { LoginOutlined, LogoutOutlined } from '@ant-design/icons';
import { Button, Form, Input, Layout, message, Modal, Space, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { fetchMe, login, logout, type UserInfo } from '../api/auth';
import Sidebar from '../components/Sidebar';

const PAGE_TITLES: Record<string, string> = {
  '/': '首页',
  '/chat': 'AI 对话',
  '/kb': '知识库',
  '/history': '历史记录',
  '/settings': '设置',
  '/admin': '管理后台',
};

export default function AppLayout() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();
  const location = useLocation();
  const title = PAGE_TITLES[`/${location.pathname.split('/')[1]}`] || PAGE_TITLES[location.pathname] || '审计 AI 助手';

  useEffect(() => {
    const token = localStorage.getItem('audit_ai_token');
    const cached = localStorage.getItem('audit_ai_user');
    if (cached) {
      setUser(JSON.parse(cached) as UserInfo);
    }
    if (token) {
      fetchMe()
        .then((me) => {
          setUser(me);
          localStorage.setItem('audit_ai_user', JSON.stringify(me));
        })
        .catch(() => setLoginOpen(true));
    } else {
      setLoginOpen(true);
    }
  }, []);

  const submitLogin = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      const result = await login(values.username, values.password);
      localStorage.setItem('audit_ai_token', result.access_token);
      localStorage.setItem('audit_ai_user', JSON.stringify(result.user));
      setUser(result.user);
      setLoginOpen(false);
      message.success('登录成功');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登录失败');
    } finally {
      setSubmitting(false);
    }
  };

  const submitLogout = async () => {
    try {
      await logout();
    } catch {
      // Token may already be expired; local cleanup still matters.
    }
    localStorage.removeItem('audit_ai_token');
    localStorage.removeItem('audit_ai_user');
    setUser(null);
    setLoginOpen(true);
  };

  return (
    <Layout className="app-shell">
      <Sidebar user={user} />
      <Layout className="main-shell">
        <header className="topbar">
          <div>
            <Typography.Title level={4} className="page-title">
              {title}
            </Typography.Title>
            <Typography.Text type="secondary">本地知识库 · 审计问答 · 文件分析</Typography.Text>
          </div>
          <Space>
            {user ? (
              <>
                <Typography.Text>{user.display_name}</Typography.Text>
                <Button icon={<LogoutOutlined />} onClick={submitLogout}>
                  退出
                </Button>
              </>
            ) : (
              <Button icon={<LoginOutlined />} onClick={() => setLoginOpen(true)}>
                登录
              </Button>
            )}
          </Space>
        </header>
        <main className="page-content">
          <Outlet />
        </main>
      </Layout>
      <Modal
        title="登录审计 AI 助手"
        open={loginOpen}
        onOk={submitLogin}
        onCancel={() => setLoginOpen(Boolean(!user))}
        confirmLoading={submitting}
        maskClosable={Boolean(user)}
      >
        <Form form={form} layout="vertical" initialValues={{ username: 'admin', password: 'admin123' }}>
          <Form.Item name="username" label="账号" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Typography.Text type="secondary">默认账号：admin/admin123、auditor/auditor123、manager/manager123</Typography.Text>
        </Form>
      </Modal>
    </Layout>
  );
}

