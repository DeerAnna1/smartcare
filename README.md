## **SmartCare / 智愈** 

面向家庭健康场景的中文全栈健康助手：以「问诊工作区」完成多轮症状采集、风险分诊和健康事件生成；「执行工作区」承接用药提醒、健康档案（EHR）、挂号预约、IoT 生命体征监测等后续任务。

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

## ⚠️ 模型与数据集下载（必读）

医学数据集和本地 RAG 模型共约 3.6 GB，未包含在 Git 仓库中。基础问诊无需这些文件；如需使用本地医学知识库，请手动下载。

### 1. 医学数据集（45 MB）

内置 RAG 知识库使用 QASystemOnMedicalKG 医学数据集：

```bash
# 从 HuggingFace 下载
huggingface-cli download wangyuxinwhy/medical medical.json \
  --local-dir services/api/data/medical_datasets/

# 或使用 wget
wget -O services/api/data/medical_datasets/medical.json \
  "https://huggingface.co/datasets/wangyuxinwhy/medical/resolve/main/medical.json"
```

### 2. Embedding 模型（1.2 GB）

RAG 向量检索默认使用中文嵌入模型：

```bash
huggingface-cli download BAAI/bge-large-zh-v1.5 \
  --local-dir services/api/models/BAAI/bge-large-zh-v1.5
```

### 3. Reranker 模型（2.1 GB，可选）

如需启用重排序（`RAG_RERANKER_ENABLED=true`），还需下载：

```bash
huggingface-cli download BAAI/bge-reranker-v2-m3 \
  --local-dir services/api/models/BAAI/bge-reranker-v2-m3
```

### 4. 加载知识库

模型和数据集准备完成后，启动服务并调用 API 加载：

```bash
curl -X POST http://localhost:8001/api/v1/rag/load \
  -H "Authorization: Bearer <your_token>"
```

也可以在前端 `/knowledge-base` 页面上传并管理 PDF、Word、Excel、图片等知识文档。

### 能力概览

- 健康问诊、风险分诊与阶段性结论生成（LangGraph 多智能体编排）
- SSE 流式对话，以及图片、文档、语音和视频输入
- 健康事件卡片、推荐任务、用药提醒与挂号预约
- 健康档案（EHR）管理、问诊归档、摘要生成与 PDF 导出
- IoT 生命体征模拟、风险分级、真人接管与可选飞书告警
- RAG 医学知识库、医学知识图谱与问诊上下文增强
- 用户长期记忆与自然语言定时健康科普
- Skill、内置工具和 MCP Server 的接入、绑定、调用与日志管理

## 1. 项目结构

| 路径                              | 说明                                                         |
| --------------------------------- | ------------------------------------------------------------ |
| `apps/web`                        | Next.js 16 前端（React 19、Tailwind v4、中文 UI）            |
| `services/api`                    | FastAPI 异步后端（SQLAlchemy 2.0、LangGraph、Skill Runtime） |
| `infra/docker/docker-compose.yml` | 本地一键启动：Postgres + Redis + API + Web                  |
| `infra/production`                | 生产环境部署配置与说明                                       |
| `stitch_healthloop_agent`         | 设计参考 / 原型 HTML（非运行时代码）                         |

说明：`apps/web/prisma/` 为历史遗留目录，业务数据以 FastAPI + PostgreSQL 为准。

## 2. 主要技术栈

- **前端**：Next.js 16、React 19、TypeScript、Tailwind CSS v4
- **后端**：FastAPI、SQLAlchemy（asyncpg）、Pydantic Settings
- **AI 编排**：OpenAI 兼容 API、LangGraph 多智能体、Skill Runtime
- **数据服务**：PostgreSQL、Redis、ChromaDB、sentence-transformers
- **生命体征**：IoT `simulate` / `webhook`、HMAC-SHA256 签名校验、风险分级与接管
- **可观测性**：Langfuse、Sentry、结构化日志（均可选）
- **部署**：Docker Compose；生产环境可参考 Railway 配置

### 2.1 问诊对话（前端 ↔ 后端）

- 主路径为 **SSE 流式**：`POST /api/v1/consultations/{id}/messages/stream`，前端消费事件流并逐字展示结果。
- 支持文本、图片、文档、语音和视频输入；上传内容会参与风险检查和问诊上下文构建。
- 会话通过定时轮询同步消息生成状态、风险标记和真人接管状态。
- 阶段性结论、健康事件卡片生成等场景仍使用对应的非流式接口。

### 2.2 AI / Agent 与 Skill

- **OpenAI 兼容 API**：通过 `OPENAI_BASE_URL`、`OPENAI_API_KEY` 和 `LLM_MODEL` 配置模型
- **LangGraph**：负责分诊、病史采集、风险评估、总结等多智能体问诊流程
- **上下文增强**：组合健康档案、长期记忆、RAG 检索和医学知识图谱
- **Skill Runtime**：支持技能注册、启停、工具绑定、调用日志和失败降级
- **内置工具**：药物相互作用、挂号预约、检验指标解释、天气与 PubMed 查询等
- **MCP**：支持 Server 注册、工具发现、健康检查、调用和删除
- **可观测性**：可选 Langfuse、Sentry 和飞书风险告警

### 2.3 RAG 知识库 API（需登录）

前缀：`/api/v1/rag`

- `POST /load`：加载内置医学数据集
- `POST /ingest-file`、`POST /ingest-image`：导入文件或图片
- `GET /search?q=...`：医学知识检索
- `GET /documents`、`DELETE /documents/{id}`：查看和删除知识文档
- `GET /stats`：查看向量库统计信息

知识库管理页面为 `/knowledge-base`；依赖和实现见 `services/api/requirements.txt` 与 `services/api/app/services/rag_*.py`。

## 3. 本地快速启动（推荐）

### 3.1 准备环境变量

在 `infra/docker` 下创建 `.env`：

```bash
cd infra/docker
cp .env.example .env
```

在 `.env` 中至少配置 `OPENAI_API_KEY`，并按需修改 `OPENAI_BASE_URL`、`LLM_MODEL` 等参数。

说明：

- 主业务接口需登录；受保护页面会跳转 `/auth`
- Docker 启动时会自动执行 Alembic 迁移
- 开发环境可自动建表；生产环境建议设置 `AUTO_CREATE_TABLES=false`
- 生产环境必须修改 `AUTH_SECRET`、`WEBHOOK_SECRET` 和 `IOT_WEBHOOK_HMAC_SECRET`
- Docker 已允许 `http://localhost:3001`；单独启动前后端时需确保 `CORS_ORIGINS` 与前端端口一致

### 3.2 启动所有服务

在项目根目录执行：

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

### 3.3 访问地址（Docker 默认端口）

| 服务       | 地址                         |
| ---------- | ---------------------------- |
| 前端       | http://localhost:3001        |
| API 文档   | http://localhost:8001/docs   |
| 健康检查   | http://localhost:8001/health |
| PostgreSQL | 宿主机 `5433` → 容器 5432   |
| Redis      | 宿主机 `6380` → 容器 6379   |

## 4. 功能模块

### 4.1 问诊归档全流程

- **流程**：多轮问诊 → 阶段性结论 → 生成并确认健康事件 → 执行推荐任务 → 归档至健康档案
- **功能**：支持历史会话、风险提示、任务执行、事件归档、EHR 摘要生成与 PDF 导出

### 4.2 心率模拟

- **功能**：调整心率、单次或连续推送、查看请求日志、最近体征和风险等级
- **风险联动**：异常体征可触发风险事件、真人接管工单和已配置的飞书告警

### 4.3 知识图谱

- **功能**：搜索疾病、症状、药物等医学实体，查看节点关系和关联子图
- **问诊联动**：识别对话中的医学实体，为问诊补充结构化知识上下文

### 4.4 知识库管理

- **功能**：上传、检索、预览和删除医学知识文档，查看向量库统计信息
- **支持格式**：PDF、Word、Excel、文本和图片等，内容经过切分与向量化后用于 RAG 检索

### 4.5 长期记忆

- **功能**：保存用户明确表达的病史、过敏史、用药情况和个人偏好，并支持确认、拒绝和删除
- **问诊联动**：已确认记忆会自动加入后续问诊上下文，减少重复询问

### 4.6 定时科普

- **功能**：通过自然语言创建健康科普计划，支持查看、编辑、启停、立即执行和运行日志
- **示例**：`每天晚上八点给我推送高血压饮食科普`

### 4.7 工具管理

- **Skill**：支持技能创建、启停、工具绑定、测试调用和日志查看
- **内置工具**：药物相互作用、挂号预约、检验指标解释、天气和 PubMed 查询等
- **MCP**：支持 Server 注册、工具发现、健康检查、调用与删除；高风险工具可启用调用前确认

挂号功能如需本地演示排班数据，可执行：

```bash
docker exec med_api python3 /app/scripts/seed_registration.py
```
