## 项目已部署上线：https://smartcare-web-production.up.railway.app/

**SmartCare / 智愈** — 面向家庭健康场景的中文全栈健康助手：以「问诊工作区」收集症状与分诊、生成结构化健康事件卡片；「执行工作区」驱动用药提醒、健康档案（EHR）、挂号预约、IoT 生命体征与风险接管等下游动作。

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

### 能力概览

- 健康问诊与结论生成（LangGraph 多轮编排）
- 药物相互作用查询技能
- 挂号预约技能
- 健康档案（EHR）生成与管理
- 技能管理（接入、调用、日志）
- 网页端心率模拟，用于联调 IoT 与问诊链路；高风险生命体征可触发真人医生接管流程
- **RAG**：后端提供医学知识库加载与检索 API（ChromaDB 向量检索，供问诊/扩展能力使用）

## 1. 项目结构


| 路径                              | 说明                                                         |
| ----------------------------------- | -------------------------------------------------------------- |
| `apps/web`                        | Next.js 16 前端（React 19、Tailwind v4、中文 UI）            |
| `services/api`                    | FastAPI 异步后端（SQLAlchemy 2.0、LangGraph、Skill Runtime） |
| `infra/docker/docker-compose.yml` | 本地一键启动：Postgres + Redis + API + Web                   |
| `stitch_healthloop_agent`         | 设计参考 / 原型 HTML（非运行时代码）                         |

说明：`apps/web/prisma/` 为历史遗留目录，业务数据以 FastAPI + PostgreSQL 为准。

## 2. 主要技术栈

- **前端**：Next.js 16、React 19、TypeScript、Tailwind CSS v4
- **后端**：FastAPI、SQLAlchemy（asyncpg）、Pydantic Settings
- **数据库**：PostgreSQL；**缓存**：Redis
- **生命体征**：IoT `simulate` / `webhook`、HMAC-SHA256 签名校验、风险分级与接管
- **心率 / 生命体征模拟**：Web 路由 `/iot-simulator`
- **部署**：Docker；生产环境可参考 Railway

### 2.1 问诊对话（前端 ↔ 后端）

- 主路径为 **SSE 流式**：`POST /api/v1/consultations/{id}/messages/stream`，前端消费事件流并在客户端做 **逐字展示（打字机效果）**，发送后展示「分析中」状态。
- 会话仍通过 **定时轮询**（约 2.5s）拉取 `GET .../consultations/{id}`，用于同步会话状态、红标、真人接管等，并在非流式场景与服务器消息对齐。
- 「生成阶段性结论」等少数调用仍可使用非流式 `POST .../messages`。

### 2.2 AI / Agent 与 Skill

- OpenAI 兼容 API（`OPENAI_BASE_URL` + `OPENAI_API_KEY`）：问诊、结构化生成等
- **LangGraph**：问诊多步骤状态机
- **自研 Skill Runtime**：技能注册、启停、调用、日志、降级
- **HTTPX**：远程 HTTP 数据源（如药物相互作用）
- **Pydantic**：请求/响应与结构化数据校验
- **可观测性**：可选 Langfuse（`LANGFUSE_*` 环境变量）

已提供但为预留/部分接入：

- **MCP**：技能配置中可写 `mcp_server` 字段；完整 MCP Gateway 调用待产品化接入

### 2.3 RAG 知识库 API（需登录）

前缀：`/api/v1/rag`

- `POST /load`：加载内置医学知识到向量库
- `GET /search?q=...`：检索调试
- `GET /stats`：库统计

依赖与向量库细节见 `services/api/requirements.txt` 与 `app/services/rag_*.py`。

## 3. 本地快速启动（推荐）

### 3.1 准备环境变量

在 `infra/docker` 下创建 `.env`：

```bash
cd infra/docker
cp .env.example .env
```

在 `.env` 中至少配置 `OPENAI_API_KEY`（及按需的 `OPENAI_BASE_URL`、`LLM_MODEL` 等）。

说明：

- 主业务接口需登录；受保护页面会跳转 `/auth`
- 开发环境可自动建表；生产建议 `AUTO_CREATE_TABLES=false` 并走 Alembic
- 后端 CORS：Docker 示例中已包含 `http://localhost:3001`；若仅本地跑 API，注意 `services/api` 的 `CORS_ORIGINS` 与前端端口一致

### 3.2 启动所有服务

在项目根目录：

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

### 3.3 访问地址（Docker 默认端口）


| 服务       | 地址                         |
| ------------ | ------------------------------ |
| 前端       | http://localhost:3001        |
| API 文档   | http://localhost:8001/docs   |
| 健康检查   | http://localhost:8001/health |
| PostgreSQL | 宿主机`5433` → 容器 5432    |
| Redis      | 宿主机`6380` → 容器 6379    |

## 4. 网页心率模拟中心（联调入口）

- **路由**：`/iot-simulator`
- **功能**：调整心率（`+/-1`、`+/-5`、预设 `70/105/128`）、单次/连续推送、请求响应日志、最近生命体征与风险等级

## 5. 技能接入说明（技能管理页）

前端路径：`/skills`，点击「接入新技能」。

### 5.1 药物相互作用技能

建议填写：

- 技能标识：`drug-interaction`
- 名称：`药物相互作用`
- 分类：`用药安全`
- 关键词：`药物相互作用,合用,同服,冲突,用药风险`
- 触发示例：
  - `阿司匹林和华法林能一起吃吗`
  - `克拉霉素和秋水仙碱能同用吗`

### 5.2 挂号技能

建议填写：

- 技能标识：`appointment-booking`
- 名称：`挂号预约`
- 分类：`就医服务`
- 关键词：`挂号,预约,排班,号源,医院,科室`
- 触发示例：
  - `帮我查明天内科号源`
  - `我想预约神经内科`
