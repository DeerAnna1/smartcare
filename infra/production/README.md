# 中国大陆单机生产部署

该方案面向低并发演示或早期运营：一台中国大陆云服务器运行 Caddy、Next.js、FastAPI、PostgreSQL、Redis 和每日备份。

首次购买、域名实名、ICP/公安备案和逐步上线流程见 [腾讯云中国大陆一年部署操作手册](./DEPLOYMENT-GUIDE-CN.md)。

不要求中国大陆节点、希望跳过备案并快速上线时，使用 [中国香港一年快速部署](./QUICKSTART-HK.md)。

## 推荐资源

- Ubuntu 24.04 LTS，`4 vCPU / 4 GB RAM / >= 80 GB SSD`
- 增加 4 GB Swap
- 仅运行 1 个 API Worker，避免多 Worker 重复启动定时任务调度器
- 使用 `BAAI/bge-small-zh-v1.5`，关闭重排模型
- 安全组仅开放 `22`、`80`、`443`；SSH 端口尽量只允许管理员 IP

完整大模型和较高并发建议升级到 4 vCPU / 8 GB RAM。

## 目录内容

- `docker-compose.prod.yml`：生产服务编排
- `Caddyfile`：同源 API 反向代理和自动 HTTPS
- `.env.production.example`：生产变量模板
- `deploy.sh`：低内存顺序构建和启动
- `postgres-backup.sh`：每日数据库压缩备份，默认保留 14 天

## 1. 大陆上线前提

中国大陆服务器绑定域名对外提供网站前必须完成 ICP 备案。域名、腾讯云账号和备案主体的实名信息必须一致。健康、药品、医疗器械或实际诊疗服务可能涉及前置审批，应按真实业务范围向备案服务商确认。

如果暂时不办理备案，应选择中国香港地域；香港服务器无需 ICP 备案，但不属于中国大陆节点，延迟和稳定性会因线路而异。

## 2. 初始化服务器

使用普通 sudo 用户登录 Ubuntu。先更新系统并安装 Docker：

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 ca-certificates curl
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

退出 SSH 后重新登录，使 docker 用户组生效。

4 GB 机器创建 4 GB Swap：

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 3. 上传代码与配置

将仓库上传到服务器，例如 `/opt/med-help-agent`，然后：

```bash
cd /opt/med-help-agent/infra/production
cp .env.production.example .env.production
```

编辑 `.env.production`：

1. 没有域名时，`SITE_ADDRESS` 和 `PUBLIC_ORIGIN` 都填 `http://服务器公网IP`。域名备案并解析完成后，两项都改为 `https://域名`。
2. 为 PostgreSQL、Redis、JWT 和 Webhook 分别生成不同密钥：`openssl rand -hex 32`。
3. 填写 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和模型名称。
4. 按需填写飞书 Webhook。

`.env.production` 包含生产密钥，禁止提交 Git 或通过聊天发送。

## 4. 域名与 DNS

在域名注册商创建两条解析：

| 类型 | 主机记录 | 记录值 |
|---|---|---|
| A | `@` | 服务器公网 IPv4 |
| A | `www` | 服务器公网 IPv4 |

如果使用 `www.example.com`，只需对应的 `www` 记录。备案通过且 DNS 生效后，把 `SITE_ADDRESS` 和 `PUBLIC_ORIGIN` 都改为 `https://www.example.com`，Caddy 会自动申请和续期 HTTPS 证书。

## 5. 部署

```bash
cd /opt/med-help-agent/infra/production
sh deploy.sh
```

查看状态与日志：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f --tail=200 api web caddy
```

健康检查：

```bash
curl -fsS "${PUBLIC_ORIGIN}/backend/health"
```

## 6. 备份与恢复

数据库备份写入 `infra/production/backups/`，默认每天一次、保留 14 天。该目录应定期同步到另一台机器或对象存储，避免服务器磁盘损坏时同时丢失主库和备份。

恢复前先停止 API，再导入指定备份：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml stop api
gzip -dc backups/medhelpagent_YYYYMMDDTHHMMSSZ.sql.gz | \
  docker compose --env-file .env.production -f docker-compose.prod.yml exec -T postgres \
  psql -U medhelp -d medhelpagent
docker compose --env-file .env.production -f docker-compose.prod.yml start api
```

## 7. 更新与日常维护

更新代码后重新执行 `sh deploy.sh`。每月至少检查：

- `docker compose ... ps` 中所有容器为 healthy/running
- 服务器磁盘使用率和内存/Swap
- `backups/` 中最近一天存在可用备份
- 域名和服务器已开启自动续费，账户余额充足
- Ubuntu 安全更新和 Docker 镜像安全更新

服务器到期前至少 30 天续费；域名建议开启自动续费并保持实名认证信息有效。
