import { InboxOutlined } from '@ant-design/icons';
import { Form, Input, message, Modal, Select, Upload } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { useEffect, useState } from 'react';
import { uploadDocument } from '../api/documents';
import type { KnowledgeBase } from '../api/kb';

type UploadModalProps = {
  open: boolean;
  knowledgeBases: KnowledgeBase[];
  selectedKbId?: string;
  onClose: () => void;
  onUploaded: () => void;
};

export default function UploadModal({
  open,
  knowledgeBases,
  selectedKbId,
  onClose,
  onUploaded,
}: UploadModalProps) {
  const [form] = Form.useForm();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    const selectedExists = knowledgeBases.some((kb) => kb.id === selectedKbId);
    form.setFieldsValue({
      kb_id: selectedExists ? selectedKbId : knowledgeBases[0]?.id,
    });
  }, [form, knowledgeBases, open, selectedKbId]);

  const submit = async () => {
    const values = await form.validateFields();
    if (!files.length) {
      message.warning('请选择文件');
      return;
    }
    setSubmitting(true);
    try {
      for (const item of files) {
        const formData = new FormData();
        formData.append('file', item.originFileObj as File);
        formData.append('kb_id', values.kb_id);
        if (values.department_category) {
          formData.append('department_category', values.department_category);
        }
        if (values.business_type) {
          formData.append('business_type', values.business_type);
        }
        if (values.tags) {
          formData.append('tags', values.tags);
        }
        await uploadDocument(formData);
      }
      message.success('上传任务已创建');
      setFiles([]);
      onUploaded();
      onClose();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '上传失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="上传到知识库"
      open={open}
      onCancel={onClose}
      onOk={submit}
      confirmLoading={submitting}
      width={640}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          kb_id: selectedKbId,
          visibility: 'private',
        }}
      >
        <Form.Item name="kb_id" label="知识库" rules={[{ required: true, message: '请选择知识库' }]}>
          <Select
            options={knowledgeBases.map((kb) => ({
              value: kb.id,
              label: `${kb.name}${kb.visibility === 'shared' ? '（共享）' : '（个人）'}`,
            }))}
          />
        </Form.Item>
        <Form.Item name="department_category" label="材料分类">
          <Input placeholder="可选，由管理员或上传者自定义" />
        </Form.Item>
        <Form.Item name="business_type" label="材料说明">
          <Input placeholder="可选，例如资料来源、项目名称或用途" />
        </Form.Item>
        <Form.Item name="tags" label="标签">
          <Input placeholder="多个标签用英文逗号分隔" />
        </Form.Item>
        <Upload.Dragger
          multiple
          maxCount={5}
          beforeUpload={() => false}
          fileList={files}
          onChange={({ fileList }) => setFiles(fileList)}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p>拖拽文件到此处，或点击选择文件</p>
          <p className="ant-upload-hint">支持 Word、Excel、PDF、png、jpg、jpeg、tiff，单文件最大 50MB</p>
        </Upload.Dragger>
      </Form>
    </Modal>
  );
}
