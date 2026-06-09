import { ApiOutlined, CheckCircleOutlined, CloudSyncOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Descriptions, Form, Input, message, Space, Tag, Typography } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import {
  configureLocalEmbedding,
  configureLocalLLM,
  fetchModelHealth,
  fetchModelSetup,
  type RuntimeModelConfig,
} from '../api/admin';
import ModelStatusBadge from '../components/ModelStatusBadge';

type LLMForm = {
  base_url: string;
  model?: string;
};

type EmbeddingForm = {
  base_url: string;
  model?: string;
  api_key: string;
};

export default function SettingsPage() {
  const [health, setHealth] = useState<Record<string, unknown>>({});
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeModelConfig>({});
  const [llmSaving, setLlmSaving] = useState(false);
  const [embeddingSaving, setEmbeddingSaving] = useState(false);
  const [llmForm] = Form.useForm<LLMForm>();
  const [embeddingForm] = Form.useForm<EmbeddingForm>();

  const refreshStatus = useCallback(async () => {
    const [setup, modelHealth] = await Promise.all([
      fetchModelSetup().catch(() => ({} as RuntimeModelConfig)),
      fetchModelHealth().catch(() => ({})),
    ]);
    setRuntimeConfig(setup);
    setHealth(modelHealth);
    llmForm.setFieldsValue({ base_url: '', model: '' });
    embeddingForm.setFieldsValue({ base_url: '', model: '', api_key: '' });
  }, [embeddingForm, llmForm]);

  useEffect(() => {
    refreshStatus().catch(() => undefined);
  }, [refreshStatus]);

  return (
    <Space direction="vertical" className="full-width" size={16}>
      <Card title="模型服务">
        <Space direction="vertical">
          <ModelStatusBadge />
          <Typography.Text type="secondary">
            这里配置本地部署模型的 OpenAI-compatible 服务地址。点击配置时会实际调用模型接口验证，不通过不会保存。
          </Typography.Text>
        </Space>
      </Card>

      <Card title="LLM 服务">
        <Form
          name="llm-model-config"
          form={llmForm}
          layout="vertical"
          initialValues={{ base_url: '', model: '' }}
          onFinish={async (values) => {
            setLlmSaving(true);
            try {
              const config = await configureLocalLLM({
                base_url: values.base_url.trim(),
                model: values.model?.trim() || undefined,
              });
              setRuntimeConfig(config);
              fetchModelHealth().then(setHealth).catch(() => setHealth({}));
              message.success(config.llm?.validation?.message || 'LLM 服务已验证并启用');
            } catch (error) {
              message.error(error instanceof Error ? error.message : 'LLM 配置失败');
            } finally {
              setLlmSaving(false);
            }
          }}
        >
          <Form.Item
            name="base_url"
            label="LLM 服务 URL"
            rules={[{ required: true, message: '请填写 LLM 服务 URL' }]}
            extra="例如：http://127.0.0.1:8000/v1 或完整 /v1/chat/completions。会尝试 /models，并实际验证 /chat/completions。"
          >
            <Input placeholder="http://127.0.0.1:8000/v1" autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="model"
            label="LLM 模型名称（可选）"
            extra="服务不支持 /models 或需要固定模型名时填写，例如：local-chat-model。"
          >
            <Input placeholder="local-chat-model" autoComplete="off" />
          </Form.Item>
          <Space direction="vertical">
            <Button type="primary" icon={<ApiOutlined />} htmlType="submit" loading={llmSaving}>
              验证并配置 LLM
            </Button>
            <ServiceValidationStatus
              configured={Boolean(runtimeConfig.llm?.base_url)}
              baseUrl={runtimeConfig.llm?.base_url}
              model={runtimeConfig.llm?.model}
              validation={runtimeConfig.llm?.validation}
            />
          </Space>
        </Form>
      </Card>

      <Card title="Embedding 服务">
        <Form
          name="embedding-model-config"
          form={embeddingForm}
          layout="vertical"
          initialValues={{ base_url: '', model: '', api_key: '' }}
          onFinish={async (values) => {
            setEmbeddingSaving(true);
            try {
              const config = await configureLocalEmbedding({
                base_url: values.base_url.trim(),
                model: values.model?.trim() || undefined,
                api_key: values.api_key.trim(),
              });
              setRuntimeConfig(config);
              fetchModelHealth().then(setHealth).catch(() => setHealth({}));
              embeddingForm.setFieldValue('api_key', '');
              message.success(config.embedding?.validation?.message || 'Embedding 服务已验证并启用');
            } catch (error) {
              message.error(error instanceof Error ? error.message : 'Embedding 配置失败');
            } finally {
              setEmbeddingSaving(false);
            }
          }}
        >
          <Form.Item
            name="base_url"
            label="Embedding 服务 URL"
            rules={[{ required: true, message: '请填写 Embedding 服务 URL' }]}
            extra="例如：http://127.0.0.1:9000/v1 或完整 /embeddings。会尝试 /models，并实际验证 /embeddings 和向量维度。"
          >
            <Input placeholder="http://127.0.0.1:9000/v1" autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="model"
            label="Embedding 模型名称（可选）"
            extra="服务不支持 /models 或需要固定模型名时填写，例如：local-embedding-model。"
          >
            <Input placeholder="local-embedding-model" autoComplete="off" />
          </Form.Item>
          <Form.Item name="api_key" label="Embedding API Key">
            <Input.Password placeholder="本地服务不需要 key 时可留空" autoComplete="off" />
          </Form.Item>
          <Space direction="vertical">
            <Button type="primary" icon={<CloudSyncOutlined />} htmlType="submit" loading={embeddingSaving}>
              验证并配置 Embedding
            </Button>
            <ServiceValidationStatus
              configured={Boolean(runtimeConfig.embedding?.base_url)}
              baseUrl={runtimeConfig.embedding?.base_url}
              model={runtimeConfig.embedding?.model}
              dim={runtimeConfig.embedding?.dim}
              apiKeySet={runtimeConfig.embedding?.api_key_set}
              validation={runtimeConfig.embedding?.validation}
            />
          </Space>
        </Form>
      </Card>

      <Card title="当前状态">
        <Space direction="vertical" className="full-width">
          <Button icon={<ReloadOutlined />} onClick={() => refreshStatus().catch(() => message.error('刷新失败'))}>
            刷新状态
          </Button>
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="LLM">
              {JSON.stringify(health.llm || {})}
            </Descriptions.Item>
            <Descriptions.Item label="Embedding">
              {JSON.stringify(health.embedding || {})}
            </Descriptions.Item>
            <Descriptions.Item label="登录方式">账号密码 MVP</Descriptions.Item>
            <Descriptions.Item label="权限过滤">后端 RAG 检索层执行</Descriptions.Item>
          </Descriptions>
        </Space>
      </Card>
    </Space>
  );
}

function ServiceValidationStatus({
  configured,
  baseUrl,
  model,
  dim,
  apiKeySet,
  validation,
}: {
  configured: boolean;
  baseUrl?: string;
  model?: string;
  dim?: number;
  apiKeySet?: boolean;
  validation?: { status?: string; message?: string; checked_at?: string; sample?: string };
}) {
  if (!configured) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        尚未配置。
      </Typography.Text>
    );
  }
  return (
    <Space direction="vertical" size={4}>
      <Space wrap>
        <Tag icon={<CheckCircleOutlined />} color={validation?.status === 'ok' ? 'green' : 'blue'}>
          {validation?.message || '已配置'}
        </Tag>
        {model ? <Tag>{model}</Tag> : null}
        {dim ? <Tag>dim={dim}</Tag> : null}
        {apiKeySet ? <Tag color="blue">key 已保存</Tag> : null}
      </Space>
      {baseUrl ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          当前 URL：{baseUrl}
        </Typography.Text>
      ) : null}
      {validation?.checked_at ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          最近验证：{validation.checked_at}
        </Typography.Text>
      ) : null}
      {validation?.sample ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          LLM 测试回复：{validation.sample}
        </Typography.Text>
      ) : null}
    </Space>
  );
}
