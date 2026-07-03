"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

interface LLMConfigModalProps {
  onClose: () => void;
  onSaved: () => void;
  required?: boolean;
}

export default function LLMConfigModal({ onClose, onSaved, required = false }: LLMConfigModalProps) {
  const { t } = useLang();
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
  const [existingMasked, setExistingMasked] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

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
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!apiKey.trim() && !existingMasked) { setError(t("请输入 API Key", "Please enter API Key")); return; }
    if (!baseUrl.trim()) { setError(t("请输入 Base URL", "Please enter Base URL")); return; }
    if (!model.trim()) { setError(t("请输入聊天模型名称", "Please enter chat model name")); return; }
    setSaving(true);
    setError("");
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
      onSaved();
    } catch (e: any) {
      setError(e.message || t("保存失败", "Save failed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-surface-container rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 pt-6 pb-2 flex-shrink-0">
          <h2 className="text-xl font-headline font-bold text-on-surface">{t("配置 AI 模型", "Configure AI Model")}</h2>
          <p className="text-sm text-on-surface-variant mt-1">
            {required ? t("请先配置 AI 模型才能开始问诊", "Please configure AI model before starting consultation") : t("填写 LLM API 配置信息", "Fill in LLM API configuration")}
          </p>
        </div>

        {/* Form */}
        <div className="px-6 py-4 space-y-4 overflow-y-auto flex-1">
          {/* 获取 API Key 引导 */}
          {required && !existingMasked && (
            <div className="rounded-xl bg-primary/5 border border-primary/20 p-4">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-primary text-xl mt-0.5">help_outline</span>
                <div className="space-y-2 text-sm text-on-surface">
                  <p className="font-medium">{t("如何获取 API Key？", "How to get an API Key?")}</p>
                  <ol className="list-decimal pl-4 space-y-1 text-on-surface-variant">
                    <li>{t("选择一个 AI 服务商（如 OpenAI、小米大模型等）", "Choose an AI provider (e.g., OpenAI, Xiaomi LLM, etc.)")}</li>
                    <li>{t("注册账号并登录", "Register and log in")}</li>
                    <li>{t("在控制台中找到「API Key」或「密钥管理」", "Find 'API Key' or 'Key Management' in the console")}</li>
                    <li>{t("创建并复制 API Key", "Create and copy the API Key")}</li>
                  </ol>
                  <p className="text-xs text-on-surface-variant/70 mt-2">
                    {t("提示：API Key 仅保存在服务器端，不会泄露", "Note: API Key is only stored on the server, never exposed")}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* API Key */}
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1.5">API Key</label>
            {existingMasked && !apiKey && (
              <p className="text-xs text-on-surface-variant mb-1">{t("当前已配置", "Currently configured")}: {existingMasked}（{t("留空则不修改", "Leave empty to keep unchanged")}）</p>
            )}
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={existingMasked ? t("留空不修改，或输入新 Key", "Leave empty to keep, or enter new Key") : "sk-..."}
                className="w-full px-4 py-2.5 pr-10 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-on-surface"
              >
                <span className="material-symbols-outlined text-[18px]">{showKey ? "visibility_off" : "visibility"}</span>
              </button>
            </div>
          </div>

          {/* Base URL */}
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1.5">{t("Base URL（聊天模型）", "Base URL (Chat Model)")}</label>
            <input
              type="url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://token-plan-cn.xiaomimimo.com/v1"
              className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm"
            />
            <p className="text-xs text-on-surface-variant mt-1.5">
              {t("常见服务商：", "Common providers:")}
              <button type="button" onClick={() => setBaseUrl("https://api.openai.com/v1")} className="text-primary hover:underline ml-1">OpenAI</button>
              <span className="mx-1">·</span>
              <button type="button" onClick={() => setBaseUrl("https://token-plan-cn.xiaomimimo.com/v1")} className="text-primary hover:underline">小米大模型</button>
              <span className="mx-1">·</span>
              <button type="button" onClick={() => setBaseUrl("https://api.deepseek.com/v1")} className="text-primary hover:underline">DeepSeek</button>
            </p>
          </div>

          {/* Chat Model */}
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1.5">{t("聊天模型", "Chat Model")}</label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="mimo-v2-omni"
              className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm"
            />
            <p className="text-xs text-on-surface-variant mt-1.5">
              {t("模型名称需与服务商一致，如 gpt-4o、mimo-v2-omni 等", "Model name must match provider, e.g., gpt-4o, mimo-v2-omni, etc.")}
            </p>
          </div>

          {/* Advanced toggle */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1 text-sm text-primary hover:text-primary/80 transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">
              {showAdvanced ? "expand_less" : "expand_more"}
            </span>
            {showAdvanced ? t("收起高级配置", "Hide Advanced") : t("展开高级配置（ASR / TTS / 多模态）", "Show Advanced (ASR / TTS / Multimodal)")}
          </button>

          {showAdvanced && (
            <div className="space-y-4 pl-1 border-l-2 border-primary/20 ml-1">
              {/* ASR */}
              <div className="pl-4">
                <label className="block text-sm font-medium text-on-surface mb-1.5">{t("语音识别模型（ASR）", "Speech Recognition Model (ASR)")}</label>
                <p className="text-xs text-on-surface-variant mb-2">{t("用于语音输入转文字，留空则使用上方聊天模型配置", "For voice input to text, leave empty to use chat model config above")}</p>
                <input type="text" value={asrModel} onChange={(e) => setAsrModel(e.target.value)} placeholder="mimo-v2.5-asr"
                  className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
                <input type="url" value={asrBaseUrl} onChange={(e) => setAsrBaseUrl(e.target.value)} placeholder={t("留空则使用上方 Base URL", "Leave empty to use Base URL above")}
                  className="w-full px-4 py-2.5 mt-2 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
              </div>

              {/* TTS */}
              <div className="pl-4">
                <label className="block text-sm font-medium text-on-surface mb-1.5">{t("语音合成模型（TTS）", "Text-to-Speech Model (TTS)")}</label>
                <p className="text-xs text-on-surface-variant mb-2">{t("用于将回复转为语音播放，留空则使用上方聊天模型配置", "For converting replies to speech, leave empty to use chat model config above")}</p>
                <input type="text" value={ttsModel} onChange={(e) => setTtsModel(e.target.value)} placeholder="mimo-v2.5-tts"
                  className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
                <input type="url" value={ttsBaseUrl} onChange={(e) => setTtsBaseUrl(e.target.value)} placeholder={t("留空则使用上方 Base URL", "Leave empty to use Base URL above")}
                  className="w-full px-4 py-2.5 mt-2 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
              </div>

              {/* Multimodal */}
              <div className="pl-4">
                <label className="block text-sm font-medium text-on-surface mb-1.5">{t("多模态模型（Vision）", "Multimodal Model (Vision)")}</label>
                <p className="text-xs text-on-surface-variant mb-2">{t("用于分析上传的图片（如化验单、病历照片），留空则使用上方聊天模型配置", "For analyzing uploaded images (e.g., lab reports, medical photos), leave empty to use chat model config above")}</p>
                <input type="text" value={omniModel} onChange={(e) => setOmniModel(e.target.value)} placeholder="mimo-v2-omni"
                  className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
                <input type="url" value={omniBaseUrl} onChange={(e) => setOmniBaseUrl(e.target.value)} placeholder={t("留空则使用上方 Base URL", "Leave empty to use Base URL above")}
                  className="w-full px-4 py-2.5 mt-2 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm" />
              </div>
            </div>
          )}

          {error && <p className="text-sm text-error">{error}</p>}
        </div>

        {/* Actions */}
        <div className="px-6 pb-6 flex gap-3 justify-end flex-shrink-0">
          {!required && (
            <button
              onClick={onClose}
              className="px-5 py-2.5 rounded-xl text-sm font-medium text-on-surface-variant hover:bg-surface-container-high transition-colors"
            >
              {t("取消", "Cancel")}
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 rounded-xl text-sm font-semibold bg-primary text-on-primary hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving ? t("保存中...", "Saving...") : t("保存配置", "Save Config")}
          </button>
        </div>
      </div>
    </div>
  );
}
