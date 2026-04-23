# Heartbeat Android Native

原生 Android 版本的心率模拟器（不依赖 Expo），用于联调 Med-Help-Agent 的 IoT 风险链路。

## 功能

- 连接配置：`baseUrl`、`token`、`mode`、`userId`、`webhookSecret`
- 心率调节：`+/-1`、`+/-5`、预设（70/105/128）
- 推送模式：
  - `simulate`: `POST /api/v1/iot/simulate`
  - `webhook`: `POST /api/v1/iot/webhook`（含 HMAC SHA256）
- 支持单次推送与连续推送
- 本地保存配置（SharedPreferences）

## 打包与安装（Android Studio）

1. 打开 Android Studio
2. `Open` 选择本目录 `Heartbeat-AndroidNative`
3. 等待 Gradle Sync 完成
4. `Build > Build APK(s)`
5. 将 `app-release.apk` 安装到手机

## 联调建议

### 本机后端（推荐 USB）

1. 后端启动在电脑 `8001` 端口
2. 执行：

```bash
adb reverse tcp:8001 tcp:8001
```

3. App 中填：

- `baseUrl`: `http://127.0.0.1:8001`
- `mode`: `simulate`
- `token`: Web 端同账号的 Bearer token（不带 `Bearer ` 前缀）

### 远端后端

- `baseUrl` 填 `https://...`
- 不需要 `adb reverse`

## 排障

- `Network request failed`：先检查 baseUrl、后端是否在线、USB 是否断开。
- `401`：token 过期或错误，重新登录获取 token。
- `webhook 模式需要签名`：确认 `userId` 与 `webhookSecret` 填写正确。
