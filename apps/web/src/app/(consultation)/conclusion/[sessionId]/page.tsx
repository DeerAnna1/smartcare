"use client";

import { useState, use, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

interface CandidateCondition {
  name: string;
  confidence: number;
  supporting_points: string[];
  against_points: string[];
}

interface EventCard {
  event_id?: string;
  chief_complaint: string;
  symptom_summary: string[];
  duration: string;
  severity: string;
  confirmed_points: string[];
  uncertain_points: string[];
  red_flags: string[];
  candidate_conditions: CandidateCondition[];
  triage_level: string;
  recommended_department: string;
  visit_preparation: string[];
  care_todos: string[];
  medication_reminder_suggestion: string[];
  followup_reminder_suggestion: string[];
  record_update_suggestion: boolean;
  insurance_material_suggestion?: string[];
  source_session_id?: string;
}

interface ConclusionPageProps {
  params: Promise<{ sessionId: string }>;
}

export default function ConclusionPage({ params }: ConclusionPageProps) {
  const { sessionId } = use(params);
  const router = useRouter();
  const { t } = useLang();

  const triageLevelMap: Record<string, { label: string; color: string; icon: string }> = {
    observe: { label: t("居家观察", "Home Observation"), color: "text-secondary", icon: "home_health" },
    outpatient: { label: t("门诊就诊", "Outpatient Visit"), color: "text-tertiary", icon: "medical_information" },
    urgent_visit: { label: t("急诊就诊", "Urgent Visit"), color: "text-error", icon: "emergency" },
    emergency: { label: t("立即急救", "Emergency"), color: "text-error", icon: "ambulance" },
  };
  const [eventCard, setEventCard] = useState<EventCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    generateConclusion();
  }, [sessionId]);

  const generateConclusion = async () => {
    setLoading(true);
    setError("");
    setEventCard(null);
    try {
      const summary = await api.getSessionSummary(sessionId);
      if (summary.extracted_fields && summary.extracted_fields.chief_complaint) {
        setEventCard({ ...summary.extracted_fields, source_session_id: sessionId });
      } else {
        setError(t("问诊尚未完成，请返回继续问诊", "Consultation not completed, please return to continue"));
      }
    } catch (e) {
      setError(t("网络错误，请重试", "Network error, please retry"));
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateEventCard = async () => {
    if (!eventCard) return;
    setGenerating(true);
    try {
      const data = await api.createEventCard(sessionId, {
        ...eventCard,
        source_session_id: sessionId,
      });
      if (data.event_id) {
        router.push(`/event-confirm/${data.event_id}`);
      } else {
        alert(t("生成事件卡失败：未返回事件ID", "Failed to generate event card: no event ID returned"));
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("未知错误", "Unknown error");
      alert(`${t("生成事件卡失败", "Failed to generate event card")}：${msg}`);
    } finally {
      setGenerating(false);
    }
  };

  const triage = eventCard ? triageLevelMap[eventCard.triage_level] || triageLevelMap.observe : null;

  return (
    <div className="overflow-y-auto h-full no-scrollbar">
      <div className="px-8 py-6 max-w-5xl mx-auto">
        {/* 面包屑 */}
        <div className="flex items-center gap-2 mb-6 text-sm">
          <Link href={`/chat/${sessionId}`} className="text-on-surface-variant hover:text-primary transition-colors">
            {t("问诊工作区", "Consultation Workspace")}
          </Link>
          <span className="text-on-surface-variant">/</span>
          <span className="text-on-surface font-semibold">{t("阶段性结论", "Interim Conclusion")}</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-secondary"></span>
            <span className="text-xs font-medium text-secondary">{t("会话已结束", "Session Ended")}</span>
          </div>
        </div>

        <h1 className="font-headline font-bold text-2xl sm:text-3xl text-on-surface mb-6 sm:mb-8">{t("阶段性结论", "Interim Conclusion")}</h1>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <div className="flex gap-2">
              <div className="w-3 h-3 rounded-full bg-primary animate-pulse"></div>
              <div className="w-3 h-3 rounded-full bg-primary animate-pulse delay-75"></div>
              <div className="w-3 h-3 rounded-full bg-primary animate-pulse delay-150"></div>
            </div>
            <p className="text-on-surface-variant text-sm">{t("智能体正在生成结构化结论...", "AI is generating structured conclusion...")}</p>
          </div>
        ) : error ? (
          <div className="bg-error-container/30 border border-error/20 rounded-2xl p-6 text-center">
            <p className="text-error font-semibold">{error}</p>
            <div className="flex justify-center gap-3 mt-4">
              <button
                onClick={() => router.push(`/chat/${sessionId}`)}
                className="px-6 py-2 bg-primary text-on-primary rounded-xl font-medium"
              >
                {t("返回继续问诊", "Return to Consultation")}
              </button>
              {error !== t("问诊尚未完成，请返回继续问诊", "Consultation not completed, please return to continue") && (
                <button onClick={generateConclusion} className="px-6 py-2 bg-surface-container-high text-on-surface rounded-xl font-medium">
                  {t("重试", "Retry")}
                </button>
              )}
            </div>
          </div>
        ) : eventCard ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* 左侧：诊断内容 */}
            <div className="lg:col-span-8 space-y-6 min-w-0">
              {/* 临床判断卡 */}
              <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
                <p className="text-on-surface-variant text-xs uppercase tracking-widest font-bold mb-3">{t("临床判断", "Clinical Assessment")}</p>
                <div className="bg-primary-fixed/30 rounded-xl p-4 mb-4">
                  <h2 className="font-headline font-bold text-2xl text-on-surface">
                    {eventCard.candidate_conditions?.[0]?.name || t("待分析", "Pending Analysis")}
                  </h2>
                  <p className="text-on-surface-variant text-sm mt-2 leading-relaxed">
                    {t("主诉", "Chief Complaint")}：{eventCard.chief_complaint}。
                    {eventCard.symptom_summary?.join("、")}
                  </p>
                </div>
                {/* 症状摘要 */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="bg-surface-container rounded-xl p-4">
                    <p className="text-xs font-bold text-on-surface-variant mb-2 uppercase tracking-wide">{t("已确认症状", "Confirmed Symptoms")}</p>
                    {eventCard.confirmed_points?.map((pt, i) => (
                      <div key={i} className="flex items-start gap-2 mt-1">
                        <span className="material-symbols-outlined text-secondary text-[16px] mt-0.5" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                        <span className="text-sm text-on-surface">{pt}</span>
                      </div>
                    ))}
                  </div>
                  <div className="bg-surface-container rounded-xl p-4">
                    <p className="text-xs font-bold text-on-surface-variant mb-2 uppercase tracking-wide">{t("待确认信息", "Uncertain Information")}</p>
                    {eventCard.uncertain_points?.map((pt, i) => (
                      <div key={i} className="flex items-start gap-2 mt-1">
                        <span className="material-symbols-outlined text-tertiary text-[16px] mt-0.5">help</span>
                        <span className="text-sm text-on-surface">{pt}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* 红旗症状 */}
              {eventCard.red_flags && eventCard.red_flags.length > 0 && (
                <div className="bg-error-container/20 border border-error/15 p-5 rounded-2xl flex items-start gap-4">
                  <span className="material-symbols-outlined text-error" style={{ fontVariationSettings: "'FILL' 1" }}>warning</span>
                  <div>
                    <h4 className="font-headline font-bold text-error text-sm">{t("风险提示", "Risk Alert")}</h4>
                    {eventCard.red_flags.map((flag, i) => (
                      <p key={i} className="text-xs text-on-error-container mt-1 leading-relaxed">{flag}</p>
                    ))}
                  </div>
                </div>
              )}

              {/* 分诊与护理建议 */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="bg-surface-container-lowest rounded-2xl p-5 border border-tertiary/20">
                  <p className="text-xs font-bold text-tertiary uppercase tracking-wide mb-3">{t("分诊建议", "Triage Recommendation")}</p>
                  <div className={`flex items-center gap-2 font-headline font-bold text-lg ${triage?.color}`}>
                    <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>{triage?.icon}</span>
                    {triage?.label}
                  </div>
                  <p className="text-sm text-on-surface-variant mt-2">
                    {t("建议科室", "Recommended Department")}：<span className="font-semibold text-on-surface">{eventCard.recommended_department}</span>
                  </p>
                </div>
                <div className="bg-surface-container-lowest rounded-2xl p-5 border border-secondary/20">
                  <p className="text-xs font-bold text-secondary uppercase tracking-wide mb-3">{t("护理建议", "Care Recommendations")}</p>
                  {eventCard.care_todos?.slice(0, 3).map((todo, i) => (
                    <div key={i} className="flex items-start gap-2 mt-1">
                      <span className="material-symbols-outlined text-secondary text-[16px] mt-0.5" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                      <span className="text-sm text-on-surface">{todo}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* 就医准备摘要 */}
              <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10">
                <div className="flex items-center justify-between mb-4">
                  <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">{t("就医准备摘要", "Visit Preparation Summary")}</p>
                  <span className="text-xs text-on-surface-variant flex items-center gap-1">
                    <span className="material-symbols-outlined text-[14px]">verified</span>{t("元数据审计", "Metadata Audit")}
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 mb-4">
                  <div className="text-center">
                    <p className="font-headline font-bold text-2xl text-on-surface">{eventCard.symptom_summary?.length || 0}</p>
                    <p className="text-xs text-on-surface-variant mt-1">{t("症状数据点", "Symptom Data Points")}</p>
                  </div>
                  <div className="text-center">
                    <p className="font-headline font-bold text-2xl text-on-surface">{eventCard.candidate_conditions?.length || 0}</p>
                    <p className="text-xs text-on-surface-variant mt-1">{t("候选方向", "Candidate Conditions")}</p>
                  </div>
                  <div className="text-center">
                    <p className="font-headline font-bold text-2xl text-secondary">
                      {((eventCard.candidate_conditions?.[0]?.confidence || 0) * 100).toFixed(0)}%
                    </p>
                    <p className="text-xs text-on-surface-variant mt-1">{t("置信度（高）", "Confidence (High)")}</p>
                  </div>
                </div>
                {eventCard.visit_preparation?.length > 0 && (
                  <p className="text-sm text-on-surface-variant italic border-t border-outline-variant/10 pt-3">
                    {t("就诊建议", "Visit Advice")}：{eventCard.visit_preparation.join("，")}
                  </p>
                )}
              </div>
            </div>

            {/* 右侧：执行工作区 Sticky */}
            <div className="lg:col-span-4 min-w-0">
              <div className="sticky top-6 space-y-4">
                <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 overflow-hidden shadow-sm">
                  <div className="bg-gradient-to-br from-primary to-primary-container p-4">
                    <span className="text-primary-fixed/80 text-[0.6875rem] font-bold uppercase tracking-widest">{t("执行工作区", "Execution Workspace")}</span>
                    <h3 className="font-headline font-bold text-on-primary text-lg mt-1">{t("草稿模式", "Draft Mode")}</h3>
                  </div>
                  <div className="p-4 space-y-3">
                    <div className="bg-surface-container rounded-xl p-3">
                      <p className="text-xs text-on-surface-variant">{t("主要对象", "Primary Subject")}</p>
                      <p className="font-semibold text-on-surface text-sm mt-0.5">{t("当前用户", "Current User")}</p>
                    </div>
                    <div className="bg-surface-container rounded-xl p-3">
                      <p className="text-xs text-on-surface-variant">{t("操作类型", "Operation Type")}</p>
                      <p className="font-semibold text-on-surface text-sm mt-0.5">
                        {triage?.label} · {eventCard.recommended_department}
                      </p>
                    </div>
                    <div className="bg-surface-container rounded-xl p-3">
                      <p className="text-xs text-on-surface-variant">{t("优先级", "Priority")}</p>
                      <p className={`font-semibold text-sm mt-0.5 ${triage?.color}`}>{triage?.label}</p>
                    </div>
                  </div>
                  <div className="p-4 space-y-3">
                    <button
                      onClick={handleGenerateEventCard}
                      disabled={generating}
                      className="w-full py-3 px-4 bg-primary text-on-primary rounded-xl font-semibold flex items-center justify-center gap-2 shadow-md hover:opacity-90 active:scale-95 transition-all disabled:opacity-50"
                    >
                      <span className="material-symbols-outlined text-[18px]">rocket_launch</span>
                      {generating ? t("生成中...", "Generating...") : t("确认并执行", "Confirm & Execute")}
                    </button>
                    <button
                      onClick={() => router.push(`/chat/${sessionId}`)}
                      className="w-full py-2.5 px-4 bg-surface-container text-on-surface rounded-xl font-medium text-sm flex items-center justify-center gap-2 hover:bg-surface-container-high transition-all"
                    >
                      <span className="material-symbols-outlined text-[16px]">add_comment</span>
                      {t("继续补充", "Continue Adding")}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
