import { UploadOutlined } from '@ant-design/icons';
import { Button, message, Modal, Space, Tag, Upload } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { useState } from 'react';
import { uploadTempFile, type TempFile } from '../api/chat';

type FileUploadPanelProps = {
  open: boolean;
  conversationId?: string;
  onClose: () => void;
  onUploaded: (file: TempFile) => void;
};

export default function FileUploadPanel({ open, conversationId, onClose, onUploaded }: FileUploadPanelProps) {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!conversationId) {
      message.warning('请先创建会话');
      return;
    }
    if (!files.length) {
      message.warning('请选择文件');
      return;
    }
    setSubmitting(true);
    try {
      for (const item of files.slice(0, 5)) {
        const formData = new FormData();
        formData.append('file', item.originFileObj as File);
        const temp = await uploadTempFile(conversationId, formData);
        onUploaded(temp);
      }
      setFiles([]);
      onClose();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '上传失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="临时上传文件" open={open} onCancel={onClose} onOk={submit} confirmLoading={submitting}>
      <Space orientation="vertical" className="full-width">
        <Upload
          multiple
          maxCount={5}
          beforeUpload={() => false}
          fileList={files}
          onChange={({ fileList }) => setFiles(fileList)}
        >
          <Button icon={<UploadOutlined />}>选择文件</Button>
        </Upload>
        <Space wrap>
          {files.map((file) => (
            <Tag key={file.uid}>{file.name}</Tag>
          ))}
        </Space>
      </Space>
    </Modal>
  );
}

