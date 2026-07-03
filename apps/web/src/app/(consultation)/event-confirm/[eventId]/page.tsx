"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

type EventCard = {
  status: string;
  chief_complaint: string;
  candidate_conditions: Array<{ name: string; confidence: number }>;
  triage_level: string;
  recommended_department: string;
  medication_reminder_suggestion: string[];
  symptom_summary: string[];
};

export default function EventConfirmPage() {
  const params = useParams<{ eventId: string }>();
  const eventId = params?.eventId ?? "";
  const router = useRouter();
  const { t } = useLang();
  const [eventCard, setEventCard] = useState<EventCard | null>(null);
  const [loadError, setLoadError] = useState("");
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    api.getEvent(eventId)
      .then((data) => setEventCard(data as EventCard))
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : t("获取事件卡失败", "Failed to load event")));
  }, [eventId, t]);

  if (loadError) return <div className="p-8 text-error">{loadError}</div>;
  if (!eventCard) return <div className="p-8 text-on-surface-variant">{t("正在加载事件卡…", "Loading event…")}</div>;

  const triageLabels: Record<string, string> = {
    observe: t("居家观察", "Observe at home"),
    outpatient: t("门诊就诊", "Outpatient visit"),
    urgent_visit: t("尽快就诊", "Urgent visit"),
    emergency: t("急诊", "Emergency"),
  };

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      const data = await api.confirmEvent(eventId);
      if (data.success) {
        const nextEventId = data.event_id || eventId;
        router.push(`/execution?eventId=${nextEventId}`);
      } else {
        alert(t("确认失败，请重试", "Confirmation failed, please retry"));
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("未知错误", "Unknown error");
      alert(`${t("确认失败", "Confirmation failed")}：${msg}`);
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="overflow-y-auto h-full no-scrollbar">
      <div className="px-8 py-6 max-w-5xl mx-auto">
        {/* 面包屑 */}
        <div className="flex items-center gap-2 mb-6 text-sm">
          <span className="text-on-surface-variant">{t("问诊工作区", "Consultation Workspace")}</span>
          <span className="material-symbols-outlined text-on-surface-variant text-[16px]">chevron_right</span>
          <span className="text-on-surface font-semibold">{t("事件卡确认", "Event Card Confirmation")}</span>
          <div className="ml-auto">
            <span className="px-3 py-1 bg-secondary-container/40 text-secondary rounded-full text-xs font-semibold">{eventCard.status}</span>
          </div>
        </div>

        <h1 className="font-headline font-bold text-2xl sm:text-3xl text-on-surface mb-6 sm:mb-8">{t("确认健康事件", "Confirm Health Event")}</h1>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* 左侧：事件卡核心内容 */}
          <div className="lg:col-span-8 space-y-5 min-w-0">
            {/* 主事件卡 */}
            <div className="rounded-2xl overflow-hidden shadow-sm border border-outline-variant/10">
              {/* 头部渐变 */}
              <div className="bg-gradient-to-br from-primary to-primary-container p-6">
                <div className="flex items-center gap-2 mb-3">
                  <span className="px-3 py-1 rounded-full bg-primary-fixed/20 text-primary-fixed text-[0.6875rem] font-bold">
                    event_repeat {t("用药设置", "Medication Setup")}
                  </span>
                </div>
                <h2 className="font-headline font-bold text-2xl text-on-primary">
                  {eventCard.candidate_conditions[0]?.name || t("健康事件", "Health Event")}
                </h2>
                <p className="text-on-primary/70 text-sm mt-1">
                  {eventCard.chief_complaint}
                </p>
              </div>

              {/* 事件详情 */}
              <div className="bg-surface-container-lowest p-6 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
                  <div>
                    <p className="text-xs text-on-surface-variant uppercase tracking-wide mb-1">{t("分诊级别", "Triage Level")}</p>
                    <p className="font-headline font-bold text-on-surface">{triageLabels[eventCard.triage_level] || eventCard.triage_level}</p>
                  </div>
                  <div>
                    <p className="text-xs text-on-surface-variant uppercase tracking-wide mb-1">{t("建议科室", "Recommended Department")}</p>
                    <p className="font-headline font-bold text-on-surface">{eventCard.recommended_department}</p>
                  </div>
                </div>

                {/* 症状摘要 */}
                <div>
                  <p className="text-xs text-on-surface-variant uppercase tracking-wide mb-2">{t("症状摘要", "Symptom Summary")}</p>
                  <div className="flex flex-wrap gap-2">
                    {eventCard.symptom_summary.map((s, i) => (
                      <span key={i} className="px-3 py-1 bg-surface-container rounded-full text-xs text-on-surface font-medium">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>

                {/* 提醒建议 */}
                {eventCard.medication_reminder_suggestion.length > 0 && (
                  <div>
                    <p className="text-xs text-on-surface-variant uppercase tracking-wide mb-2">{t("用药建议", "Medication Advice")}</p>
                    {eventCard.medication_reminder_suggestion.map((s, i) => (
                      <div key={i} className="flex items-start gap-2 mt-1">
                        <span className="material-symbols-outlined text-tertiary text-[16px] mt-0.5" style={{ fontVariationSettings: "'FILL' 1" }}>medication</span>
                        <span className="text-sm text-on-surface">{s}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* 来源追踪 */}
                <div className="flex items-center gap-3 bg-surface-container rounded-xl p-3 mt-2">
                  <span className="material-symbols-outlined text-on-surface-variant text-[20px]">chat_paste_go</span>
                  <div>
                    <p className="text-xs font-semibold text-on-surface">{t("问诊会话来源", "Consultation Session Source")}</p>
                    <p className="text-xs text-on-surface-variant">ID: {eventId.slice(0, 8)}...</p>
                  </div>
                </div>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-3">
              <button
                onClick={handleConfirm}
                disabled={confirming}
                className="flex-1 py-4 px-6 bg-primary text-on-primary rounded-xl font-semibold flex items-center justify-center gap-2 shadow-md hover:opacity-90 active:scale-95 transition-all disabled:opacity-50 text-lg"
              >
                <span className="material-symbols-outlined">rocket_launch</span>
                {confirming ? t("确认中...", "Confirming...") : t("确认并发送执行", "Confirm & Execute")}
              </button>
            </div>

          </div>

          {/* 右侧：工作区连接器 + AI 审计 */}
          <div className="lg:col-span-4 space-y-4 min-w-0">
            {/* 工作区连接器 */}
            <div className="bg-surface-container-lowest rounded-2xl p-5 border border-outline-variant/10 shadow-sm">
              <p className="font-headline font-bold text-sm text-on-surface mb-3">{t("工作区连接器", "Workspace Connector")}</p>
              <div className="space-y-2">
                <div className="flex items-center gap-3 bg-primary-fixed/20 rounded-xl p-3">
                  <span className="material-symbols-outlined text-primary text-[20px]">medical_information</span>
                  <span className="text-sm font-medium text-on-surface">{t("问诊工作区", "Consultation Workspace")}</span>
                </div>
                <div className="flex justify-center">
                  <span className="material-symbols-outlined text-on-surface-variant">arrow_downward</span>
                </div>
                <div className="flex items-center gap-3 bg-secondary-container/30 rounded-xl p-3">
                  <span className="material-symbols-outlined text-secondary text-[20px]">assignment_turned_in</span>
                  <span className="text-sm font-medium text-on-surface">{t("执行工作区", "Execution Workspace")}</span>
                </div>
              </div>
              <p className="text-xs text-on-surface-variant mt-3 leading-relaxed">
                {t("此操作将把经验证的医疗记录移至\"执行区\"，以便进行患者交付和自动化随访。", "This operation will move verified medical records to the execution zone for patient delivery and automated follow-up.")}
              </p>
            </div>

            {/* 模型输出置信度；不生成未经后端返回的审计结论。 */}
            <div className="bg-surface-container-lowest rounded-2xl p-5 border border-outline-variant/10 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <p className="font-headline font-bold text-sm text-on-surface">{t("AI 逻辑审计", "AI Logic Audit")}</p>
                <span className="text-xs font-bold text-secondary">
                  {eventCard.candidate_conditions[0]
                    ? `${Math.round(eventCard.candidate_conditions[0].confidence * 100)}%`
                    : t("无数据", "No data")}
                </span>
              </div>
              <p className="text-xs text-on-surface-variant">
                {t("仅展示事件卡返回的候选方向置信度。", "Only confidence returned by the event API is shown.")}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
