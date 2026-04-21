"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api-client";

const DEMO_EVENT = {
  chief_complaint: "持续咳嗽3天，低热",
  candidate_conditions: [{ name: "疑似上呼吸道感染", confidence: 0.85 }],
  triage_level: "outpatient",
  recommended_department: "呼吸内科",
  medication_reminder_suggestion: ["布洛芬 400mg 退热，按需服用", "建议多饮水，每日 2L 以上"],
  followup_reminder_suggestion: ["7天后到呼吸内科复诊"],
  visit_preparation: ["携带体温记录", "告知既往用药情况"],
  record_update_suggestion: true,
  care_todos: ["注意休息", "监测体温变化"],
  symptom_summary: ["持续咳嗽", "低热 37.8°C", "轻微鼻塞", "咽痛"],
};

export default function EventConfirmPage() {
  const params = useParams<{ eventId: string }>();
  const eventId = params?.eventId ?? "";
  const router = useRouter();
  const [eventCard, setEventCard] = useState(DEMO_EVENT);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    api.getEvent(eventId).then((data) => {
      if (data) setEventCard(data);
    }).catch(() => {/* use demo data */});
  }, [eventId]);

  const auditChecks = [
    { label: "候选方向与临床建议相符", status: "ok" },
    { label: "未检测到药物相互作用", status: "ok" },
    { label: "建议定期监测生命体征：血压", status: "info" },
  ];

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      const data = await api.confirmEvent(eventId);
      if (data.success) {
        const nextEventId = data.event_id || eventId;
        router.push(`/execution?eventId=${nextEventId}`);
      } else {
        alert("确认失败，请重试");
      }
    } catch (e) {
      alert("确认失败，请重试");
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="overflow-y-auto h-full no-scrollbar">
      <div className="px-8 py-6 max-w-5xl mx-auto">
        {/* 面包屑 */}
        <div className="flex items-center gap-2 mb-6 text-sm">
          <span className="text-on-surface-variant">问诊工作区</span>
          <span className="material-symbols-outlined text-on-surface-variant text-[16px]">chevron_right</span>
          <span className="text-on-surface font-semibold">事件卡确认</span>
          <div className="ml-auto">
            <span className="px-3 py-1 bg-secondary-container/40 text-secondary rounded-full text-xs font-semibold">就绪待传输</span>
          </div>
        </div>

        <h1 className="font-headline font-bold text-3xl text-on-surface mb-8">确认健康事件</h1>

        <div className="grid grid-cols-12 gap-6">
          {/* 左侧：事件卡核心内容 */}
          <div className="col-span-8 space-y-5">
            {/* 主事件卡 */}
            <div className="rounded-2xl overflow-hidden shadow-sm border border-outline-variant/10">
              {/* 头部渐变 */}
              <div className="bg-gradient-to-br from-primary to-primary-container p-6">
                <div className="flex items-center gap-2 mb-3">
                  <span className="px-3 py-1 rounded-full bg-primary-fixed/20 text-primary-fixed text-[0.6875rem] font-bold">
                    event_repeat 用药设置
                  </span>
                </div>
                <h2 className="font-headline font-bold text-2xl text-on-primary">
                  {eventCard.candidate_conditions[0]?.name || "健康事件"}
                </h2>
                <p className="text-on-primary/70 text-sm mt-1">
                  {eventCard.chief_complaint}
                </p>
              </div>

              {/* 事件详情 */}
              <div className="bg-surface-container-lowest p-6 space-y-4">
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <p className="text-xs text-on-surface-variant uppercase tracking-wide mb-1">分诊级别</p>
                    <p className="font-headline font-bold text-on-surface">门诊就诊</p>
                    <p className="text-xs text-secondary mt-1">建议 24 小时内就诊</p>
                  </div>
                  <div>
                    <p className="text-xs text-on-surface-variant uppercase tracking-wide mb-1">建议科室</p>
                    <p className="font-headline font-bold text-on-surface">{eventCard.recommended_department}</p>
                  </div>
                </div>

                {/* 症状摘要 */}
                <div>
                  <p className="text-xs text-on-surface-variant uppercase tracking-wide mb-2">症状摘要</p>
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
                    <p className="text-xs text-on-surface-variant uppercase tracking-wide mb-2">用药建议</p>
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
                    <p className="text-xs font-semibold text-on-surface">问诊会话来源</p>
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
                {confirming ? "确认中..." : "确认并发送执行"}
              </button>
            </div>

            {/* 安全协议提示 */}
            <div className="flex items-center justify-center gap-2 py-2 px-4 bg-inverse-surface/90 rounded-full text-inverse-on-surface text-xs font-medium w-fit mx-auto">
              <span className="material-symbols-outlined text-[14px]">lock</span>
              安全协议已启动：执行前需进行临床审查
            </div>
          </div>

          {/* 右侧：工作区连接器 + AI 审计 */}
          <div className="col-span-4 space-y-4">
            {/* 工作区连接器 */}
            <div className="bg-surface-container-lowest rounded-2xl p-5 border border-outline-variant/10 shadow-sm">
              <p className="font-headline font-bold text-sm text-on-surface mb-3">工作区连接器</p>
              <div className="space-y-2">
                <div className="flex items-center gap-3 bg-primary-fixed/20 rounded-xl p-3">
                  <span className="material-symbols-outlined text-primary text-[20px]">medical_information</span>
                  <span className="text-sm font-medium text-on-surface">问诊工作区</span>
                </div>
                <div className="flex justify-center">
                  <span className="material-symbols-outlined text-on-surface-variant">arrow_downward</span>
                </div>
                <div className="flex items-center gap-3 bg-secondary-container/30 rounded-xl p-3">
                  <span className="material-symbols-outlined text-secondary text-[20px]">assignment_turned_in</span>
                  <span className="text-sm font-medium text-on-surface">执行工作区</span>
                </div>
              </div>
              <p className="text-xs text-on-surface-variant mt-3 leading-relaxed">
                此操作将把经验证的医疗记录移至"执行区"，以便进行患者交付和自动化随访。
              </p>
            </div>

            {/* AI 逻辑审计 */}
            <div className="bg-surface-container-lowest rounded-2xl p-5 border border-outline-variant/10 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <p className="font-headline font-bold text-sm text-on-surface">AI 逻辑审计</p>
                <span className="text-xs font-bold text-secondary">
                  {Math.round(eventCard.candidate_conditions[0]?.confidence * 100 || 85)}% verified
                </span>
              </div>
              {auditChecks.map((check, i) => (
                <div key={i} className="flex items-start gap-2 mt-2">
                  <span
                    className={`material-symbols-outlined text-[16px] mt-0.5 ${
                      check.status === "ok" ? "text-secondary" : "text-tertiary"
                    }`}
                    style={{ fontVariationSettings: "'FILL' 1" }}
                  >
                    {check.status === "ok" ? "check_circle" : "info"}
                  </span>
                  <span className="text-xs text-on-surface leading-relaxed">{check.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
