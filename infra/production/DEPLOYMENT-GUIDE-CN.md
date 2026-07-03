# 腾讯云中国大陆一年部署操作手册

本文面向低并发演示或早期运营环境。目标结果是一台腾讯云中国大陆轻量应用服务器、一个已实名且已备案的域名，以及通过 HTTPS 对外访问的 SmartCare 服务。

> 重要：项目包含健康咨询功能。备案的网站名称、服务内容和实际页面必须一致。若涉及互联网诊疗、药品或医疗器械信息服务，不要用“普通个人博客”等描述规避审核，应先向腾讯云备案客服和所在地主管部门确认是否需要前置审批。正式处理健康数据前，还应完成隐私政策、用户授权、账号注销和数据安全评估。

## 一、开始前准备

准备以下资料，后续页面会用到：

- 中国大陆手机号、邮箱、微信和可支付的腾讯云账号。
- 个人备案：身份证、本人手机号、常住地址。
- 单位备案：营业执照、法定代表人和网站负责人证件及联系方式；医疗相关服务优先使用单位主体。
- 3 个备选域名，例如 `smartcare-xxx.cn`。不要购买 `.org` 或 `.name` 用于大陆备案。
- 大模型 API Key。密钥只放服务器的 `.env.production`，不得提交到 Git。

最终会得到：腾讯云账号、服务器公网 IP、域名、ICP 备案号、公安备案号、可访问的 `https://你的域名`。

## 二、注册并实名认证腾讯云账号

网站：[腾讯云](https://cloud.tencent.com/)

1. 单击右上角 **免费注册**，使用微信或手机号注册。
2. 登录后，右上角头像进入 **账号信息 > 实名认证**。
3. 备案主体为个人就选择个人认证；备案主体为企业就使用企业认证。不要用个人实名账号购买后再以无关企业备案。
4. 按页面完成证件、人脸或企业打款认证。
5. 进入 **费用中心 > 账户信息**，绑定手机号和邮箱，并设置余额提醒。

得到：状态为“已实名认证”的腾讯云账号。账号实名、域名实名和备案主体应保持一致或符合腾讯云规定的关联关系。

## 三、购买一年服务器

网站：[腾讯云轻量应用服务器控制台](https://console.cloud.tencent.com/lighthouse/instance/index)

1. 单击 **新建**。
2. 地域选择目标用户附近的中国大陆地域：华南用户选广州，华东用户选上海或南京，华北用户选北京。实例创建后不能更换地域。
3. 镜像选择 **系统镜像 > Ubuntu 24.04 LTS 64位**，不要选择带 WordPress、宝塔等应用镜像。
4. 套餐优先选择 `4核4GB、SSD >= 80GB、带宽 >= 5Mbps` 的一年新用户活动。没有活动时，至少选择 `2核4GB`；若并发较高或模型常驻内存，使用 `4核8GB`。
5. 时长选 **1年**，数量 `1`，勾选 **自动续费**。
6. 登录方式优先选 **SSH 密钥**。创建并下载私钥后妥善保存；私钥无法再次下载。若只能使用密码，设置独立强密码。
7. 提交订单并付款。
8. 返回实例列表，记录 **实例 ID、公网 IPv4、地域和到期时间**。

得到：一台运行中的 Ubuntu 服务器和一个公网 IPv4。建议同时在实例详情页创建一次初始快照。

## 四、设置防火墙和监控

网站仍为轻量应用服务器控制台。

1. 打开实例详情的 **防火墙**，仅保留：TCP `80` 来源全部 IPv4、TCP `443` 来源全部 IPv4、UDP `443` 来源全部 IPv4。
2. TCP `22` 最好只允许管理员当前公网 IP，例如 `1.2.3.4/32`。管理员网络经常变化时可以临时放开，登录完成后再收紧。
3. 不要开放 `3000`、`8000`、`5432`、`6379`，它们只供容器内部使用。
4. 在实例的 **监控/告警** 中创建 CPU、内存、磁盘和流量告警，通知方式至少选择微信和短信。
5. 建议阈值：CPU 连续 5 分钟大于 85%，内存大于 90%，磁盘使用率大于 80%。

得到：公网只能访问 SSH、HTTP 和 HTTPS；资源异常时会收到通知。

## 五、注册域名并完成实名

网站：[腾讯云域名注册](https://dnspod.cloud.tencent.com/)

1. 先进入 [域名信息模板](https://console.cloud.tencent.com/domain/template) 创建模板。
2. 模板类型必须与备案主体一致，填写中文姓名或单位全称、证件号码、地址、手机号和邮箱。
3. 完成手机号、邮箱验证并等待模板显示 **实名审核通过**。
4. 回到域名注册页，查询备选域名。优先 `.cn` 或 `.com`，确认页面显示 **立即注册/立即加购**。
5. 购买时长选 `1年`，选择刚审核通过的信息模板，开启 **自动续费**，核对首年和续费价格后付款。
6. 进入 **域名注册 > 我的域名**，确认状态为正常、实名认证通过，记录到期日。

得到：一个归你使用一年的实名域名。域名付款后通常不能退款，因此应先核对拼写、主体和续费价。

## 六、提交 ICP 首次备案

网站：[腾讯云 ICP 备案控制台](https://console.cloud.tencent.com/beian)

1. 进入 **我的备案 > 开始备案/首次备案**，选择 **网站/域名**。
2. 选择备案省份。个人按证件或实际居住规则选择，单位按证件注册地址和当地管局规则选择。
3. 选择主办者性质：个人或单位；填写刚购买的根域名，不要填写 `https://`。
4. 云服务资源选择第三步购买的轻量应用服务器。
5. 主体信息严格按证件填写。单位备案的网站负责人是否必须为法定代表人，以所在省页面提示为准。
6. 网站名称使用真实、审慎且与主体相符的名称；网站服务内容按实际功能填写“健康信息管理、健康知识展示、智能健康咨询辅助”等。不要宣称在线诊断或治疗，除非确有相应资质。
7. 前置审批页面按真实业务选择。页面提示医疗、药品或医疗器械前置审批时先停止提交，联系腾讯云备案客服确认所需许可证。
8. 上传证件和补充材料，网站负责人按提示完成视频核验。
9. 提交腾讯云初审。腾讯云通常在 `1-2` 个工作日反馈；按电话或工单要求修改。
10. 腾讯云提交管局后，工信部会发送短信验证码。必须在短信要求的时限内进入短信中的工信部核验页面完成验证。
11. 等待省通信管理局审核，法定上限通常为 `20` 个工作日。
12. 审核通过后记录 ICP 备案号，例如 `粤ICP备XXXXXXXX号`。

得到：ICP备案号。备案通过前不要把大陆服务器上的网站公开对外服务。

## 七、域名解析到服务器

网站：[DNSPod 控制台](https://console.dnspod.cn/dns/list)

1. 找到域名，进入 **DNS 解析 > 添加记录**。
2. 添加根域名：记录类型 `A`，主机记录 `@`，线路类型“默认”，记录值填服务器公网 IPv4，TTL 保持默认。
3. 添加 `www`：记录类型 `A`，主机记录 `www`，记录值填相同公网 IPv4。
4. 保存后在电脑终端执行 `nslookup 你的域名`，返回服务器 IP 即解析生效。

得到：域名指向服务器。项目默认建议把 `SITE_ADDRESS` 和 `PUBLIC_ORIGIN` 都设置为完整根域名地址，例如 `https://smartcare-example.cn`。

## 八、登录服务器并安装 Docker

本机终端执行，替换用户名、私钥路径和公网 IP：

```bash
chmod 600 ~/Downloads/tencent-lighthouse.pem
ssh -i ~/Downloads/tencent-lighthouse.pem ubuntu@服务器公网IP
```

在服务器执行：

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 git ca-certificates curl
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

退出并重新 SSH 登录，然后执行：

```bash
docker --version
docker compose version
free -h
```

得到：Docker 可用，`free -h` 显示约 4GB Swap。

## 九、把项目上传到服务器

若代码已经托管在 Git 仓库，在服务器执行：

```bash
sudo mkdir -p /opt/med-help-agent
sudo chown "$USER":"$USER" /opt/med-help-agent
git clone 你的Git仓库地址 /opt/med-help-agent
```

若不使用 Git，在本机项目根目录执行：

```bash
rsync -az --exclude '.git' --exclude 'node_modules' --exclude '.venv' \
  --exclude 'services/api/models' --exclude '.env*' \
  -e 'ssh -i ~/Downloads/tencent-lighthouse.pem' ./ \
  ubuntu@服务器公网IP:/opt/med-help-agent/
```

得到：服务器存在 `/opt/med-help-agent/infra/production/docker-compose.prod.yml`。

## 十、填写生产环境变量

服务器执行：

```bash
cd /opt/med-help-agent/infra/production
cp .env.production.example .env.production
chmod 600 .env.production
openssl rand -hex 32
```

连续执行 `openssl rand -hex 32` 至少五次，每次结果分别填入数据库、Redis、JWT、Webhook 和 IoT 密钥。然后执行 `nano .env.production`，至少修改：

```dotenv
SITE_ADDRESS=https://你的已备案域名
PUBLIC_ORIGIN=https://你的已备案域名
POSTGRES_PASSWORD=随机值1
REDIS_PASSWORD=随机值2
AUTH_SECRET=随机值3
WEBHOOK_SECRET=随机值4
IOT_WEBHOOK_HMAC_SECRET=随机值5
OPENAI_API_KEY=你的模型API密钥
OPENAI_BASE_URL=你的OpenAI兼容接口地址
LLM_MODEL=接口支持的模型名
```

不要在变量值两侧添加中文引号，不要把 `.env.production` 发到聊天、邮箱或 Git。

得到：仅服务器可读的生产配置文件。

## 十一、启动项目并取得 HTTPS

服务器执行：

```bash
cd /opt/med-help-agent/infra/production
sh deploy.sh
```

首次构建和下载模型可能需要较长时间。完成后执行：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=100 api web caddy
curl -fsS https://你的域名/backend/health
```

预期结果：容器状态为 `running` 或 `healthy`，健康检查返回成功 JSON，浏览器访问 `https://你的域名` 显示登录页面，地址栏证书有效。Caddy 会自动申请和续期证书。

若失败，优先检查：域名是否解析到正确 IP、80/443 是否开放、备案是否已通过、`.env.production` 的域名和 API 配置是否正确。

## 十二、添加备案号与公安备案

1. 在网站所有页面底部展示 ICP 备案号，并链接到 [工信部备案系统](https://beian.miit.gov.cn/)。上线前应在前端实现该页脚。
2. 网站开放后 `30日内` 登录 [全国互联网安全管理服务平台](https://beian.mps.gov.cn/) 注册并实名认证。
3. 选择 **联网备案登录 > 开办主体管理 > 新办网站申请**，按页面填写主体、域名、服务器 IP、服务商“腾讯云”和网站负责人信息。
4. 按属地公安机关要求提交，审核通过后取得公安备案号。
5. 把公安备案号和平台提供的图标、链接放在网站底部。

得到：ICP备案号和公安备案号均在网站底部公开展示。

## 十三、一年稳定运行清单

- 腾讯云服务器和域名均开启自动续费，余额能覆盖续费；到期前 30 天人工检查一次。
- 每周查看控制台告警和容器状态；每月安装 Ubuntu 安全更新并重启验证。
- 项目每天生成数据库备份，但本机备份不能抵御整机损坏；至少每周把 `infra/production/backups/` 同步到腾讯云 COS 或另一台设备。
- 每月随机恢复一次最新备份，确认备份真的可用。
- 重大更新前创建服务器快照；不要把快照当数据库长期备份。
- 定期检查模型 API 余额、调用失败率、磁盘空间和 HTTPS 到期状态。
- 健康数据属于敏感个人信息。公开运营前补齐隐私政策、单独同意、最小化收集、导出/删除机制和安全事件响应流程。

## 十四、最终验收表

| 检查项 | 合格结果 |
|---|---|
| 服务器 | Ubuntu 正常运行，自动续费开启 |
| 防火墙 | 公网仅 22、80、443；22 已限制来源 |
| 域名 | 实名通过，A 记录指向服务器 IP |
| 备案 | ICP 通过，公安备案已提交或通过 |
| HTTPS | 浏览器证书有效，无混合内容警告 |
| 容器 | `postgres/redis/api/web/caddy/backup` 正常 |
| API | `/backend/health` 返回成功 |
| 备份 | 最近 24 小时内有 `.sql.gz` 且完成恢复测试 |
| 告警 | CPU、内存、磁盘告警能收到 |
| 合规 | 页脚备案号、隐私政策和用户授权已上线 |
