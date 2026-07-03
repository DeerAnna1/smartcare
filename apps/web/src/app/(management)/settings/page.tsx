"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

export default function SettingsPage() {
  const { t } = useLang();
  const errorMessage = (error: unknown, fallback: string) => error instanceof Error ? error.message : fallback;
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://token-plan-cn.xiaomimimo.com/v1");
  const [model, setModel] = useState("mimo-v2-omni");
  const [asrModel, setAsrModel] = useState("mimo-v2.5-asr");
  const [asrBaseUrl, setAsrBaseUrl] = useState("");
  const [ttsModel, setTtsModel] = useState("mimo-v2.5-tts");
  const [ttsBaseUrl, setTtsBaseUrl] = useState("");
  const [omniModel, setOmniModel] = useState("mimo-v2-omni");
  const [omniBaseUrl, setOmniBaseUrl] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [existingMasked, setExistingMasked] = useState("");
  const [loading, setLoading] = useState(true);

  // 飞书配置状态
  const [feishuUrl, setFeishuUrl] = useState("");
  const [feishuSecret, setFeishuSecret] = useState("");
  const [feishuSecretConfigured, setFeishuSecretConfigured] = useState(false);
  const [showFeishuSecret, setShowFeishuSecret] = useState(false);
  const [feishuEnabled, setFeishuEnabled] = useState(false);
  const [feishuSaving, setFeishuSaving] = useState(false);
  const [feishuTesting, setFeishuTesting] = useState(false);
  const [feishuSuccess, setFeishuSuccess] = useState("");
  const [feishuError, setFeishuError] = useState("");

  useEffect(() => {
    api.getLLMConfig().then((cfg) => {
      if (cfg.has_config) {
        setExistingMasked(cfg.api_key_masked);
        setBaseUrl(cfg.base_url || "https://token-plan-cn.xiaomimimo.com/v1");
        setModel(cfg.model || "mimo-v2-omni");
        setAsrModel(cfg.asr_model || "mimo-v2.5-asr");
        setAsrBaseUrl(cfg.asr_base_url || "");
        setTtsModel(cfg.tts_model || "mimo-v2.5-tts");
        setTtsBaseUrl(cfg.tts_base_url || "");
        setOmniModel(cfg.omni_model || "mimo-v2-omni");
        setOmniBaseUrl(cfg.omni_base_url || "");
      }
    }).catch(() => {}).finally(() => setLoading(false));

    // 加载飞书配置
    api.getFeishuConfig().then((cfg) => {
      setFeishuUrl(cfg.webhook_url || "");
      setFeishuEnabled(cfg.enabled || false);
      setFeishuSecretConfigured(cfg.secret_configured || false);
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!apiKey.trim() && !existingMasked) { setError(t("请输入 API Key", "Please enter API Key")); return; }
    if (!baseUrl.trim()) { setError(t("请输入 Base URL", "Please enter Base URL")); return; }
    if (!model.trim()) { setError(t("请输入聊天模型名称", "Please enter chat model name")); return; }
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await api.updateLLMConfig({
        api_key: apiKey.trim() || undefined,
        base_url: baseUrl.trim(),
        model: model.trim(),
        asr_model: asrModel.trim(),
        asr_base_url: asrBaseUrl.trim(),
        tts_model: ttsModel.trim(),
        tts_base_url: ttsBaseUrl.trim(),
        omni_model: omniModel.trim(),
        omni_base_url: omniBaseUrl.trim(),
      });
      setSuccess(t("配置已保存", "Config saved"));
      setApiKey("");
      // 刷新 masked key
      const cfg = await api.getLLMConfig();
      setExistingMasked(cfg.api_key_masked);
    } catch (error: unknown) {
      setError(errorMessage(error, t("保存失败", "Save failed")));
    } finally {
      setSaving(false);
    }
  };

  const handleFeishuSave = async () => {
    setFeishuSaving(true);
    setFeishuError("");
    setFeishuSuccess("");
    try {
      await api.updateFeishuConfig({
        webhook_url: feishuUrl.trim(),
        enabled: feishuEnabled,
        ...(feishuSecret.trim() ? { webhook_secret: feishuSecret.trim() } : {}),
      });
      setFeishuSuccess(t("飞书配置已保存", "Feishu config saved"));
      if (feishuSecret.trim()) {
        setFeishuSecretConfigured(true);
        setFeishuSecret("");
      }
    } catch (error: unknown) {
      setFeishuError(errorMessage(error, t("保存失败", "Save failed")));
    } finally {
      setFeishuSaving(false);
    }
  };

  const handleFeishuTest = async () => {
    setFeishuTesting(true);
    setFeishuError("");
    setFeishuSuccess("");
    try {
      await api.updateFeishuConfig({
        webhook_url: feishuUrl.trim(),
        enabled: feishuEnabled,
        ...(feishuSecret.trim() ? { webhook_secret: feishuSecret.trim() } : {}),
      });
      await api.testFeishuConfig();
      setFeishuSuccess(t("测试告警已发送，请检查飞书群", "Test alert sent. Check your Feishu group."));
      if (feishuSecret.trim()) {
        setFeishuSecretConfigured(true);
        setFeishuSecret("");
      }
    } catch (error: unknown) {
      setFeishuError(errorMessage(error, t("测试发送失败", "Test delivery failed")));
    } finally {
      setFeishuTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-5 sm:px-6">
        <p className="text-on-surface-variant text-sm">{t("加载中...", "Loading...")}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-4 py-5 sm:px-6">

      <div className="space-y-5 rounded-3xl border border-outline-variant/15 bg-surface-container-lowest p-5 shadow-sm sm:p-6">
        <div className="flex items-center gap-3 border-b border-outline-variant/10 pb-4"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-container text-primary"><span className="material-symbols-outlined text-[20px]">model_training</span></div><div><h2 className="font-bold text-on-surface">{t("模型服务", "Model Service")}</h2><p className="text-xs text-on-surface-variant">{t("聊天、语音与多模态模型连接参数", "Connection settings for chat, speech, and multimodal models")}</p></div></div>
        {/* API Key */}
        <div>
          <label className="block text-sm font-medium text-on-surface mb-1.5">API Key</label>
          {existingMasked && !apiKey && (
            <p className="text-xs text-on-surface-variant mb-1">{t("当前", "Current")}: {existingMasked}（{t("留空则不修改", "Leave empty to keep")}）</p>
          )}
          <div className="relative">
            <input
              type={showKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={existingMasked ? t("留空不修改，或输入新 Key", "Leave empty to keep, or enter new key") : "sk-..."}
              className="w-full px-4 py-2.5 pr-10 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm"
            />
            <button type="button" onClick={() => setShowKey(!showKey)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-on-surface">
              <span className="material-symbols-outlined text-[18px]">{showKey ? "visibility_off" : "visibility"}</span>
            </button>
          </div>
        </div>

        {/* Base URL */}
        <div>
          <label className="block text-sm font-medium text-on-surface mb-1.5">Base URL</label>
          <input type="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://token-plan-cn.xiaomimimo.com/v1"
            className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
        </div>

        {/* Chat Model */}
        <div>
          <label className="block text-sm font-medium text-on-surface mb-1.5">{t("聊天模型", "Chat Model")}</label>
          <input type="text" value={model} onChange={(e) => setModel(e.target.value)} placeholder="mimo-v2-omni"
            className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
        </div>

        <hr className="border-outline-variant/20" />
        <p className="text-sm font-medium text-on-surface-variant">{t("高级模型配置", "Advanced Model Configuration")}</p>

        {/* ASR */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("语音识别模型", "Speech Recognition Model")} (ASR)</label>
            <input type="text" value={asrModel} onChange={(e) => setAsrModel(e.target.value)} placeholder="mimo-v2.5-asr"
              className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-on-surface-variant mb-1">ASR Base URL（{t("留空用上方", "Leave empty to use above")}）</label>
            <input type="url" value={asrBaseUrl} onChange={(e) => setAsrBaseUrl(e.target.value)} placeholder={t("默认同上", "Same as above")}
              className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
          </div>
        </div>

        {/* TTS */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("语音合成模型", "Text-to-Speech Model")} (TTS)</label>
            <input type="text" value={ttsModel} onChange={(e) => setTtsModel(e.target.value)} placeholder="mimo-v2.5-tts"
              className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-on-surface-variant mb-1">TTS Base URL（{t("留空用上方", "Leave empty to use above")}）</label>
            <input type="url" value={ttsBaseUrl} onChange={(e) => setTtsBaseUrl(e.target.value)} placeholder={t("默认同上", "Same as above")}
              className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
          </div>
        </div>

        {/* Multimodal */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("多模态模型", "Multimodal Model")} (Vision)</label>
            <input type="text" value={omniModel} onChange={(e) => setOmniModel(e.target.value)} placeholder="mimo-v2-omni"
              className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("多模态", "Multimodal")} Base URL（{t("留空用上方", "Leave empty to use above")}）</label>
            <input type="url" value={omniBaseUrl} onChange={(e) => setOmniBaseUrl(e.target.value)} placeholder={t("默认同上", "Same as above")}
              className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
          </div>
        </div>

        {error && <p className="text-sm text-error">{error}</p>}
        {success && <p className="text-sm text-green-600">{success}</p>}

        <button onClick={handleSave} disabled={saving}
          className="w-full px-5 py-2.5 rounded-xl text-sm font-semibold bg-primary text-on-primary hover:opacity-90 transition-opacity disabled:opacity-50">
          {saving ? t("保存中...", "Saving...") : t("保存配置", "Save Configuration")}
        </button>
      </div>

      {/* ─── 飞书 Webhook 告警配置 ─────────────────────────────────── */}
      <div className="space-y-5 rounded-3xl border border-outline-variant/15 bg-surface-container-lowest p-5 shadow-sm sm:p-6">
        <div>
            <h2 className="text-lg font-bold text-on-surface">{t("飞书 Webhook 告警", "Feishu Webhook Alerts")}</h2>
            <p className="text-xs text-on-surface-variant mt-0.5">{t("高风险患者自动发送告警到飞书群。配置指南见", "Auto-send alerts for high-risk patients to Feishu. Guide: ")} <code className="bg-surface-container px-1 rounded text-xs">docs/feishu-guide.md</code></p>
        </div>

        {/* Webhook URL 输入 */}
        <div>
          <label className="block text-sm font-medium text-on-surface mb-1.5">Webhook URL</label>
          <input
            type="url"
            value={feishuUrl}
            onChange={(e) => setFeishuUrl(e.target.value)}
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
            className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-on-surface mb-1.5">
            {t("签名校验密钥（可选）", "Signature secret (optional)")}
          </label>
          <div className="relative">
            <input
              type={showFeishuSecret ? "text" : "password"}
              value={feishuSecret}
              onChange={(e) => setFeishuSecret(e.target.value)}
              placeholder={feishuSecretConfigured ? t("已配置，留空则不修改", "Configured; leave blank to keep") : t("飞书机器人安全设置中的签名密钥", "Secret from the bot security settings")}
              className="w-full px-4 py-2.5 pr-10 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm"
            />
            <button
              type="button"
              onClick={() => setShowFeishuSecret(!showFeishuSecret)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-on-surface"
              title={showFeishuSecret ? t("隐藏密钥", "Hide secret") : t("显示密钥", "Show secret")}
            >
              <span className="material-symbols-outlined text-[18px]">{showFeishuSecret ? "visibility_off" : "visibility"}</span>
            </button>
          </div>
        </div>

        {/* 启用开关 */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-on-surface">{t("启用告警", "Enable Alerts")}</p>
            <p className="text-xs text-on-surface-variant">{t("开启后高风险信号将自动发送到飞书", "High-risk signals will be sent to Feishu automatically when enabled")}</p>
          </div>
          <button
            onClick={() => setFeishuEnabled(!feishuEnabled)}
            className={`relative w-11 h-6 rounded-full transition-colors ${feishuEnabled ? "bg-primary" : "bg-surface-container-highest"}`}
          >
            <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${feishuEnabled ? "translate-x-5" : ""}`} />
          </button>
        </div>

        {feishuError && <p className="text-sm text-error">{feishuError}</p>}
        {feishuSuccess && <p className="text-sm text-green-600">{feishuSuccess}</p>}

        <div className="flex flex-col gap-2 sm:flex-row">
          <button onClick={handleFeishuSave} disabled={feishuSaving || feishuTesting}
            className="flex-1 px-5 py-2.5 rounded-xl text-sm font-semibold bg-primary text-on-primary hover:opacity-90 transition-opacity disabled:opacity-50">
            {feishuSaving ? t("保存中...", "Saving...") : t("保存飞书配置", "Save Feishu Configuration")}
          </button>
          <button onClick={handleFeishuTest} disabled={feishuSaving || feishuTesting || !feishuEnabled}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-outline-variant/30 px-5 py-2.5 text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container disabled:opacity-50">
            <span className="material-symbols-outlined text-[17px]">send</span>
            {feishuTesting ? t("发送中...", "Sending...") : t("发送测试告警", "Send Test Alert")}
          </button>
        </div>
      </div>
    </div>
  );
}
