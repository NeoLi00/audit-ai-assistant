# 审计 AI 助手平台

面向高校审计处的本地化 AI 助手 MVP，支持知识库管理、MinerU 文档解析、mock/真实模型网关、RAG 问答、引用来源、临时文件分析、权限与操作日志。

## 技术架构

- 前端：React、TypeScript、Vite、Ant Design、React Router、Axios
- 后端：Python 3.11+、FastAPI、SQLAlchemy 2.x、Alembic、Pydantic Settings
- 基础服务：PostgreSQL、Redis、MinIO、Qdrant，OpenSearch 可选
- 异步任务：Celery，MVP 默认 `PROCESS_DOCUMENTS_INLINE=true` 便于本地调试
- 文件解析：默认 MinerU；旧轻量解析器仅保留为非默认兼容 provider
- 模型：DeepSeek API、本地 multilingual-e5-small、学校模型 URL；未配置时自动使用 mock provider

## 文件解析方式

当前 MVP 默认使用 MinerU，不再对入库文件走轻量解析 fallback：

- `.pdf/.docx/.pptx/.xlsx`、图片等由 `mineru` CLI 解析，并读取 MinerU 生成的 Markdown。
- `.doc` 会先尝试调用 LibreOffice headless 转 `.docx`，再交给 MinerU。
- `.xls` 会标记 `need_review`，建议先转为 `.xlsx` 后上传。
- 如果本机没有安装 `mineru` 命令，文档会标记 `need_review` 并提示安装 MinerU，不会悄悄回退到轻量解析。
- `MINERU_TIMEOUT=0` 表示后端不主动超时终止 MinerU；解析中会在前端展示版面分析、表格结构识别、图片/扫描件 OCR 等状态提示。
- PDF 默认按 `MINERU_PAGE_BATCH_SIZE=10` 页一段调用 MinerU。页段 Markdown 会按文件 hash 缓存在
  `.local_storage/mineru-output/pdf-batches/`，后续重新解析同一文件会跳过已完成页段；如果某一段失败，前面已完成页段仍会落库、切 chunk、生成 embedding，文档最终标记 `need_review` 并保留失败页段提示。

安装 MinerU：

```bash
cd audit-ai-assistant
make backend-install-mineru
```

也可以在后端虚拟环境中按 MinerU 官方方式安装：

```bash
cd backend
. .venv/bin/activate
uv pip install -U "mineru[all]"
```

## 知识库与账号

- 知识库分为 `shared` 共享知识库和 `private` 个人知识库。
- 系统不再预设“招标采购、资产管理”等业务分类；共享知识库名称和内容由系统管理员自行创建。
- 每个用户访问知识库时会自动拥有一个个人知识库。
- 普通用户只能上传到自己的个人知识库。
- `system_admin` 可以创建共享知识库，并上传共享知识库内容。
- `system_admin` 可以删除知识库，并在管理后台查看/整理数据库。
- 账号存储在数据库 `users` 表中；默认 seed 只创建 `admin`、`auditor`、`manager` 三个账号。
- 管理后台提供用户列表和新建账号入口；只有 `system_admin` 可以创建账号。

## 目录结构

```text
audit-ai-assistant/
  backend/      FastAPI 后端、解析、RAG、Celery、测试
  frontend/     React/Vite/Ant Design 前端
  docker-compose.yml
  .env.example
  .env.local.example
  Makefile
```

## macOS 本地测试

如果本机没有 Docker Desktop，使用 SQLite 本地模式：

```bash
cd audit-ai-assistant
make local-env
make backend-install
make backend-install-mineru
make backend-install-local-models
make seed
make backend-dev
```

另开终端：

```bash
cd audit-ai-assistant
make frontend-install
make frontend-dev
```

如果本机已安装 Docker Desktop，使用 PostgreSQL/Redis/MinIO/Qdrant：

```bash
cd audit-ai-assistant
make postgres-env
make dev-services
make backend-install
make backend-install-mineru
make backend-install-local-models
make migrate
make seed
make backend-dev
```

另开终端：

```bash
cd audit-ai-assistant
make frontend-install
make frontend-dev
```

访问 `http://localhost:5173`。默认账号：

- `admin / admin123 / system_admin`
- `auditor / auditor123 / auditor`
- `manager / manager123 / audit_manager`

## WSL Ubuntu 22.04/24.04 部署

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv nodejs npm docker.io docker-compose-plugin libreoffice
cd audit-ai-assistant
cp .env.example .env
make dev-services
make backend-install
make migrate
make seed
make backend-dev
```

如需 MinerU，请在后端虚拟环境安装 `mineru[all]` 后重启 worker/backend。macOS 本地建议用 pip/uv 安装，不走 Docker。

## 环境变量

关键变量在 `.env.example` 中：

- `DATABASE_URL`：PostgreSQL 连接
- `REDIS_URL`：Redis 连接
- `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`
- `QDRANT_URL`、`QDRANT_COLLECTION`
- `ENABLE_OPENSEARCH`、`OPENSEARCH_URL`
- `USE_MOCK_LLM`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`
- `USE_MOCK_EMBEDDING`、`EMBED_BASE_URL`、`EMBED_API_KEY`、`EMBED_MODEL`、`EMBED_DIM`
- `DOCUMENT_PARSER_PROVIDER`、`MINERU_COMMAND`、`MINERU_BACKEND`
- `LOCAL_E5_MODEL`、`LOCAL_E5_BASE_URL`、`LOCAL_E5_HOST`、`LOCAL_E5_PORT`

## 测试模型配置

设置页提供两个测试模型开关：

- DeepSeek API：在页面填入 API Key 和模型名，后端保存到本机 `.runtime_model_config.json`，前端只显示已配置，不回显密钥。
- 本地 multilingual-e5-small：点击“一键启动本地 embedding 测试”，后端会启动本地 OpenAI-compatible `/v1/embeddings` 服务；冷启动完成后页面显示“multilingual-e5-small 已就绪，可以开始测试”。

本地 e5 依赖安装：

```bash
cd audit-ai-assistant
make backend-install-local-models
```

## 配置学校千问 URL

在 `.env` 中设置：

```env
USE_MOCK_LLM=false
LLM_BASE_URL=http://your-qwen-service/v1
LLM_API_KEY=your-key-if-needed
LLM_MODEL=qwen
```

后端按 OpenAI Chat Completions 风格调用：`POST {LLM_BASE_URL}/chat/completions`。

## 配置学校 Embedding URL

```env
USE_MOCK_EMBEDDING=false
EMBED_BASE_URL=http://your-embedding-service/v1
EMBED_API_KEY=your-key-if-needed
EMBED_MODEL=school-embedding
EMBED_DIM=1024
```

后端按 OpenAI Embeddings 风格调用：`POST {EMBED_BASE_URL}/embeddings`，支持 batch。

## 常用命令

```bash
make local-env          # 写入 SQLite/no-Docker 本地 .env
make postgres-env       # 写入 Docker/PostgreSQL .env
make dev-services       # postgres/redis/minio/qdrant
make backend-install
make backend-install-mineru
make backend-install-local-models
make backend-dev        # http://localhost:8000，可用 BACKEND_PORT=8001 覆盖
make frontend-install
make frontend-dev       # http://localhost:5173，可用 FRONTEND_PORT=5174 覆盖
make migrate
make seed
make worker
make test
make lint
```

## API 验收

- 健康检查：`GET http://localhost:8000/api/health`
- 模型状态：`GET http://localhost:8000/api/health/models`
- 数据库概览：`GET /api/admin/database/overview`
- 测试模型配置：`POST /api/admin/model-setup/deepseek`、`POST /api/admin/model-setup/local-e5/start`
- 登录：`POST /api/auth/login`
- 上传到知识库：`POST /api/documents/upload`
- 删除知识库：`DELETE /api/kb/{kb_id}`，仅 `system_admin`
- RAG 问答：`POST /api/chat/conversations/{id}/messages`

## 常见问题

- LibreOffice 未安装：`.doc` 无法转换为 `.docx`，系统返回失败原因；`.docx` 不受影响。
- MinerU 未安装：上传文件状态为 `need_review`，提示安装 `mineru[all]`；系统不会改走轻量解析。
- 本地 e5 第一次启动较慢：需要下载 `intfloat/multilingual-e5-small`，页面会显示冷启动中，完成后显示可以开始测试。
- Embedding URL 不可用：本地调试请保持 `USE_MOCK_EMBEDDING=true`；接真实服务时确认 `/embeddings` 路径和维度。
- Qdrant 维度不匹配：确认 `EMBED_DIM` 与 Qdrant collection 维度一致；mock embedding 默认按该变量生成。
- MinIO 连接失败：MVP 默认启用 `USE_LOCAL_STORAGE_FALLBACK=true`，会保存到 `backend/.local_storage`。
- WSL 端口访问问题：确认 `make backend-dev` 和 `make frontend-dev` 使用 `--host 0.0.0.0`，Windows 侧访问 `localhost:5173`。
- macOS 没有 Docker：运行 `make local-env`，跳过 `make dev-services`，用 SQLite 和 mock 模型先跑通。
- 端口被占用：后端运行 `BACKEND_PORT=8001 make backend-dev`，前端运行 `FRONTEND_PORT=5174 make frontend-dev`。
- OpenSearch 未启用：系统使用 PostgreSQL 文本 contains fallback keyword search，RAG 流程仍可跑通。
