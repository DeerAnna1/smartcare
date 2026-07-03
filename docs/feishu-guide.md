# 飞书 Webhook 高风险告警配置

智愈使用飞书群聊的“自定义机器人” Webhook。问诊文本或穿戴设备数据触发高风险人工接管时，API 会异步发送告警卡片，不阻塞用户看到紧急建议。

飞书官方说明：<https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot>

## 1. 创建群自定义机器人

1. 进入接收告警的飞书群聊。
2. 打开群设置中的“机器人”，添加“自定义机器人”。
3. 设置名称，例如“智愈风险告警”。
4. 复制以 `https://open.feishu.cn/open-apis/bot/v2/hook/` 开头的 Webhook URL。
5. 在安全设置中选择一种方式：
   - 推荐“签名校验”：复制飞书生成的签名密钥。
   - 或使用“关键词”：填写 `智愈` 或 `高风险`，告警标题中包含这两个关键词。

Webhook URL 和签名密钥都属于敏感凭据，不要提交到 Git。

## 2. 应用内配置（推荐）

1. 登录智愈。
2. 进入“管理 → 模型配置”。
3. 在“飞书 Webhook 告警”中填写 Webhook URL。
4. 如果飞书启用了签名校验，填写签名密钥。
5. 打开“启用告警”，点击“保存飞书配置”。
6. 点击“发送测试告警”，确认群内收到标记为测试的卡片。

应用内配置按用户隔离，并优先于全局环境变量。

## 3. 环境变量配置（全局）

在 `infra/docker/.env` 中配置：

```bash
FEISHU_ALERT_ENABLED=true
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
FEISHU_WEBHOOK_SECRET=飞书签名密钥
```

如果未启用签名校验，`FEISHU_WEBHOOK_SECRET` 留空。修改后重新创建 API 容器，使环境变量生效：

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build api
```

Railway 部署时，在 API 服务的 Variables 中设置同名变量后重新部署。

## 4. 自动触发条件

- 问诊文本命中高风险规则并创建人工接管工单。
- 最近穿戴设备数据为 `high`，用户继续问诊时触发接管。
- IoT Webhook 新上报的高风险数据直接创建接管工单。目前心率 `>= 120 bpm` 判定为高风险。

系统会对同一会话已有的待处理/处理中工单去重，避免同一风险反复通知。

## 5. 排查

- HTTP 成功但群内无消息：检查飞书返回的业务错误码、关键词或签名密钥。
- `Ip Not Allowed`：检查机器人 IP 白名单。
- 配置测试失败：确认 URL 为 V2 自定义机器人地址，并查看 API 日志中的“飞书告警发送失败”。
- 全局配置不生效：确认 Docker Compose/Railway 已传入变量并重启 API。
