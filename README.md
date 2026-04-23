## 项目已部署上线：https://smartcare-web-production.up.railway.app/

adb reverse tcp:8001 tcp:8001
docker compose -f infra/docker/docker-compose.yml up -d --build

一个面向家庭健康场景的全栈应用，包含：
- 健康问诊与结论生成
- 药物相互作用查询技能
- 挂号预约技能
- 健康档案（EHR）生成与管理
- 技能管理（接入、调用、日志）
- 患者心率模拟，用于联调问诊链路。
- 手机端调整心率，web网页会同时感知到心率变化，发生心率风险会触发真人医生接管。

## 1. 项目结构

- `apps/web`：Next.js 前端
- `services/api`：FastAPI 后端
- `infra/docker/docker-compose.yml`：本地一键启动（Postgres + Redis + API + Web）

## 2. 主要技术栈

- 前端：Next.js 16、React 19、TypeScript、Tailwind
- 后端：FastAPI、SQLAlchemy、Pydantic
- 数据库：PostgreSQL
- 缓存：Redis
- 生命体征接入：IoT `simulate` / `webhook` 双通道、HMAC-SHA256 签名校验、自动风险分级与接管触发
- 移动端模拟器方案：
  - Web 方案：`apps/web` 内置心率模拟页面（推荐联调）
  - Android 原生方案：`Heartbeat-AndroidNative`（Kotlin + OkHttp + Android Studio APK）
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

说明：

- 当前项目的主业务接口要求登录后访问，前端受保护页面会跳转到 `/auth`
- 后端数据库 schema 目前采用“开发环境可自动建表，正式环境建议 Alembic 迁移”的兼容策略
- 若在非开发环境部署，建议显式设置 `AUTO_CREATE_TABLES=false`

### 3.2 启动所有服务

在项目根目录执行：

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

### 3.3 访问地址

- 前端：http://localhost:3001
- 后端文档：http://localhost:8001/docs
- 健康检查：http://localhost:8001/health

## 4. 网页心率模拟中心（推荐联调入口）
为避免手机 App 打包/网络策略带来的不确定性，项目已提供网页端心率模拟入口：

- 路由：`/iot-simulator`
- 功能：
  - 调整心率（`+/-1`、`+/-5`、预设 `70/105/128`）
  - 单次推送、连续推送
  - 实时查看请求/响应日志
  - 查看后端最近生命体征与风险等级

## 5. Heartbeat-AndroidNative（Android Studio 打包 APK）

### 5.1 打包步骤

1. Android Studio 打开 `Heartbeat-AndroidNative`
2. 等待 Gradle Sync 完成
3. 菜单：`Build > Build Bundle(s) / APK(s) > Build APK(s)`
4. 构建完成后点击 `Locate` 打开产物目录

### 5.2 真机联调要点

- 本机 API：执行 `adb -s <deviceId> reverse tcp:8001 tcp:8001`
- App 中 `baseUrl` 填 `http://127.0.0.1:8001`
- `simulate` 模式使用 Web 同账号 token（不带 `Bearer ` 前缀）

## 6. 技能接入说明（技能管理页）

前端路径：`/skills`，点击“接入新技能”。

### 6.1 药物相互作用技能

建议填写：

- 技能标识：`drug-interaction`
- 名称：`药物相互作用`
- 分类：`用药安全`
- 关键词：`药物相互作用,合用,同服,冲突,用药风险`
- 触发示例：
  - `阿司匹林和华法林能一起吃吗`
  - `克拉霉素和秋水仙碱能同用吗`

### 6.2 挂号技能

建议填写：

- 技能标识：`appointment-booking`
- 名称：`挂号预约`
- 分类：`就医服务`
- 关键词：`挂号,预约,排班,号源,医院,科室`
- 触发示例：
  - `帮我查明天内科号源`
  - `我想预约神经内科`
