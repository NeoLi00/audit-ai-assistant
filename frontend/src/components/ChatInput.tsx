import { PaperClipOutlined, SendOutlined } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import TextArea from 'antd/es/input/TextArea';
import { useState } from 'react';

type ChatInputProps = {
  value?: string;
  disabled?: boolean;
  fixed?: boolean;
  placeholder?: string;
  onSubmit: (text: string) => void;
  onUploadClick?: () => void;
};

export default function ChatInput({
  value = '',
  disabled,
  fixed,
  placeholder = '输入审计问题，回答将基于所选知识库',
  onSubmit,
  onUploadClick,
}: ChatInputProps) {
  const [text, setText] = useState(value);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setText('');
  };

  const className = ['chat-input', fixed ? 'fixed' : '', onUploadClick ? '' : 'without-upload']
    .filter(Boolean)
    .join(' ');

  return (
    <div className={className}>
      {onUploadClick && (
        <Tooltip title="上传文件">
          <Button icon={<PaperClipOutlined />} onClick={onUploadClick} />
        </Tooltip>
      )}
      <TextArea
        value={text}
        onChange={(event) => setText(event.target.value)}
        onPressEnter={(event) => {
          if (!event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
        autoSize={{ minRows: 1, maxRows: 5 }}
        placeholder={placeholder}
      />
      <Tooltip title="发送">
        <Button type="primary" icon={<SendOutlined />} disabled={disabled || !text.trim()} onClick={submit} />
      </Tooltip>
    </div>
  );
}
