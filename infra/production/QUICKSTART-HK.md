# 中国香港一年快速部署

这是本项目最短的正式部署路径：腾讯云中国香港轻量应用服务器运行全部服务，GitHub 用于发布代码，Caddy 自动配置 HTTPS。香港服务器无需 ICP 备案，但中国大陆访问速度和稳定性不如大陆备案节点。

## 1. 购买服务器

打开 [腾讯云轻量应用服务器](https://console.cloud.tencent.com/lighthouse/instance/index)，单击 **新建**：

- 地域：`中国香港`
- 镜像：`Docker CE`；没有该选项时选择 `Ubuntu 24.04`
- 配置：最低 `2核4GB`，推荐 `4核4GB` 或 `4核8GB`，系统盘至少 `80GB`
- 时长：`1年`
- 登录：设置 SSH 密钥或强密码
- 开启：`自动续费`

付款后记录服务器公网 IP。防火墙开放 TCP `22/80/443`，不要开放 `3000/8000/5432/6379`。

## 2. 登录并克隆 GitHub 项目

在服务器控制台单击 **登录**，或从本机 SSH 登录。然后执行：

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

退出后重新登录，再执行：

```bash
sudo mkdir -p /opt/med-help-agent
sudo chown "$USER":"$USER" /opt/med-help-agent
git clone https://github.com/你的账号/你的仓库.git /opt/med-help-agent
```

私有仓库建议在 GitHub 创建只读 Deploy Key，不要把 GitHub 密码或长期 Token 写入服务器命令历史。

## 3. 配置生产变量

```bash
cd /opt/med-help-agent/infra/production
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

先把域名解析到服务器公网 IP；Caddy 的自动 HTTPS 必须使用真实域名。至少填写：

```dotenv
SITE_ADDRESS=https://你的域名
PUBLIC_ORIGIN=https://你的域名
POSTGRES_PASSWORD=独立随机密码
REDIS_PASSWORD=另一个随机密码
AUTH_SECRET=随机密钥
WEBHOOK_SECRET=随机密钥
IOT_WEBHOOK_HMAC_SECRET=随机密钥
OPENAI_API_KEY=你的模型密钥
OPENAI_BASE_URL=你的模型接口地址
LLM_MODEL=你的模型名称
```

随机值用 `openssl rand -hex 32` 生成，每个字段使用不同结果。

## 4. 一条命令启动

```bash
cd /opt/med-help-agent/infra/production
sh deploy.sh
```

首次构建通常需要数分钟。检查：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=100 api web caddy
```

## 5. 域名和 HTTPS

在腾讯云或其他正规注册商购买一个域名并完成实名认证。在 DNS 控制台添加：

| 类型 | 主机记录 | 记录值 |
|---|---|---|
| A | `@` | 服务器公网 IP |
| A | `www` | 服务器公网 IP |

确认 `.env.production` 的 `SITE_ADDRESS` 和 `PUBLIC_ORIGIN` 与实际访问地址一致，然后再次执行 `sh deploy.sh`。等待几分钟后访问：

```text
https://你的域名
https://你的域名/backend/health
```

Caddy 会自动申请并续期免费 HTTPS 证书。

## 6. 更新网站

以后每次 GitHub 发布新版本，只需登录服务器执行：

```bash
cd /opt/med-help-agent
git pull --ff-only
cd infra/production
sh deploy.sh
```

## 一年维护最低要求

- 服务器和域名开启自动续费，到期前 30 天检查余额。
- 每周检查 `docker compose ... ps` 和磁盘空间。
- 项目每天在 `infra/production/backups/` 生成数据库备份；每周下载一份到本地或对象存储。
- 更新前创建服务器快照。
- 正式收集健康数据前上线隐私政策和用户授权机制。

完成后得到：一个无需 ICP 备案、带 HTTPS、可从 GitHub 更新、数据库每日备份的网站。预计人工操作时间约 30-60 分钟，不含服务器构建和域名 DNS 生效等待时间。
