# MCP 服务配置指南

## 概述

MCP（Model Context Protocol）是一种让 AI 模型调用外部工具的协议。智愈平台支持注册自定义 MCP 服务器，让 AI 在问诊对话中自动调用你提供的工具。

## 什么是 MCP？

MCP 是一种标准化的工具调用协议，允许 AI 助手与外部服务交互。通过 MCP，你可以：

- 扩展 AI 的能力（如查询自定义数据库、调用专业 API）
- 集成内部系统（如 HIS、LIS、PACS）
- 添加行业特定工具（如药品库存查询、检验报告解读）

## 快速开始

### 1. 启动 MCP 服务器

MCP 服务器需要实现标准的 MCP 协议接口。以下是一个 Mock 示例：

```bash
cd services/api
python scripts/mock_mcp_server.py
```

默认监听 `http://localhost:9000`。

### 2. 注册 MCP 技能

1. 登录智愈平台
2. 进入 **管理 → 工具管理**
3. 点击 **「注册新技能」**
4. 填写表单：
   - **Skill ID**: 唯一标识符，如 `my-mcp-tool`
   - **名称**: 工具显示名称
   - **描述**: 工具功能说明
   - **MCP 服务地址**: 填入你的 MCP 服务器地址
     - Docker 环境: `http://host.docker.internal:9000`
     - 本地开发: `http://localhost:9000`
5. 点击 **「创建」**

### 3. 验证连接

1. 切换到 **「MCP 服务」** tab
2. 找到你注册的服务
3. 点击心率图标进行**健康检查**
4. 状态显示 `healthy` 表示连接正常

### 4. 测试调用

1. 在 MCP 服务列表中，点击播放图标
2. 输入 JSON 参数
3. 点击 **「执行调用」**
4. 查看返回结果

## 在问诊中使用

注册成功后，AI 在问诊对话中会根据用户问题自动匹配并调用合适的工具：

```
用户: 帮我查一下阿莫西林和布洛芬能不能一起吃
AI: [自动调用 check_drug_interaction 工具]
AI: 根据查询结果，阿莫西林和布洛芬可以同时使用...
```

## MCP 服务器开发

### 接口规范

MCP 服务器需要实现以下 HTTP 接口：

#### `GET /health`

健康检查端点。

**响应示例:**
```json
{
  "status": "healthy",
  "tools": ["tool_name_1", "tool_name_2"]
}
```

#### `POST /invoke`

工具调用端点。

**请求体:**
```json
{
  "tool_name": "check_drug_interaction",
  "parameters": {
    "drugs": ["阿莫西林", "布洛芬"]
  }
}
```

**响应体:**
```json
{
  "status": "success",
  "result": {
    "interaction": "无明显相互作用",
    "detail": "..."
  }
}
```

### 开发建议

1. **工具命名**: 使用 snake_case，如 `query_lab_report`
2. **参数校验**: 在服务端校验参数类型和必填项
3. **错误处理**: 返回清晰的错误信息，便于 AI 理解
4. **超时设置**: 建议单次调用不超过 30 秒
5. **幂等性**: 查询类工具应保证幂等性

## 内置工具

系统内置了以下工具，无需额外配置：

| 工具 ID | 名称 | 说明 |
|---------|------|------|
| `check_drug_interaction` | 药物相互作用查询 | 查询药物间的相互作用和安全用药建议 |
| `query_doctor_schedule` | 医生排班查询 | 按科室查询可用号源和出诊时间 |
| `lock_appointment_slot` | 挂号锁定 | 锁定预约号源（需排班 ID） |

## 常见问题

**Q: 健康检查返回 error？**
- 确认 MCP 服务器已启动且可访问
- Docker 环境中使用 `host.docker.internal` 而非 `localhost`
- 检查防火墙或网络策略是否阻止了连接

**Q: 工具调用超时？**
- 检查 MCP 服务器日志
- 确认工具执行时间在合理范围内
- 检查网络延迟

**Q: AI 不调用我的工具？**
- 确认工具状态为 ACTIVE
- 检查工具描述和关键词是否准确
- 在问诊中使用与工具相关的关键词

**Q: 如何更新工具？**
- 在工具管理页面删除旧工具
- 重新注册新版本
