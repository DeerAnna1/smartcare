## 项目已部署上线：https://smartcare-web-production.up.railway.app/

一个面向家庭健康场景的全栈应用，包含：
- 健康问诊与结论生成
- 药物相互作用查询技能
- 挂号预约技能
- 健康档案（EHR）生成与管理
- 技能管理（接入、调用、日志）

## 1. 项目结构

- `apps/web`：Next.js 前端
- `services/api`：FastAPI 后端
- `infra/docker/docker-compose.yml`：本地一键启动（Postgres + Redis + API + Web）

## 2. 主要技术栈

- 前端：Next.js 16、React 19、TypeScript、Tailwind
- 后端：FastAPI、SQLAlchemy、Pydantic
- 数据库：PostgreSQL
- 缓存：Redis
- 部署：Docker / Railway

#### 2.1 AI / Agent 与 Skill 现状

- OpenAI 兼容 API（可通过 `OPENAI_BASE_URL` 适配 OpenAI 兼容网关）
  - 用途：问诊对话、结构化内容生成（如 EHR 摘要）
- LangGraph（状态图编排）
  - 用途：问诊多步骤编排、状态流转、路由控制
- 自研 Skill Runtime（Skill 管理 + 执行）
  - 用途：技能注册、启停、调用、日志记录、降级返回
- HTTPX
  - 用途：远程 HTTP 数据源调用（如药物相互作用查询）
- Pydantic（Schema 校验）
  - 用途：请求/响应模型校验、结构化数据约束

已提供但当前为“预留/部分接入”：

- MCP（Model Context Protocol）
  - 现状：已支持在技能中配置 `mcp_server` 字段；真实 MCP Gateway 调用逻辑标记为待接入

## 3. 本地快速启动（推荐）

### 3.1 准备环境变量

在 `infra/docker` 下创建 `.env`：

```bash
cd infra/docker
cp .env.example .env
```

### 3.2 启动所有服务

在项目根目录执行：

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

### 3.3 访问地址

- 前端：http://localhost:3001
- 后端文档：http://localhost:8001/docs
- 健康检查：http://localhost:8001/health

## 4. 技能接入说明（技能管理页）

前端路径：`/skills`，点击“接入新技能”。

### 4.1 药物相互作用技能

建议填写：

- 技能标识：`drug-interaction`
- 名称：`药物相互作用`
- 分类：`用药安全`
- 关键词：`药物相互作用,合用,同服,冲突,用药风险`
- 触发示例：
  - `阿司匹林和华法林能一起吃吗`
  - `克拉霉素和秋水仙碱能同用吗`

### 4.2 挂号技能

建议填写：

- 技能标识：`appointment-booking`
- 名称：`挂号预约`
- 分类：`就医服务`
- 关键词：`挂号,预约,排班,号源,医院,科室`
- 触发示例：
  - `帮我查明天内科号源`
  - `我想预约神经内科`

