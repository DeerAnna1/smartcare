"use client";

import { useState, use, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api-client";

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
  source_session_id?: string;
}

const triageLevelMap: Record<string, { label: string; color: string; icon: string }> = {
  observe: { label: "居家观察", color: "text-secondary", icon: "home_health" },
  outpatient: { label: "门诊就诊", color: "text-tertiary", icon: "medical_information" },
  urgent_visit: { label: "急诊就诊", color: "text-error", icon: "emergency" },
  emergency: { label: "立即急救", color: "text-error", icon: "ambulance" },
};

interface ConclusionPageProps {
  params: Promise<{ sessionId: string }>;
}

export default function ConclusionPage({ params }: ConclusionPageProps) {
  const { sessionId } = use(params);
  const router = useRouter();
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
        setError("问诊尚未完成，请返回继续问诊");
      }
    } catch (e) {
      setError("网络错误，请重试");
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
      }
    } catch (e) {
      alert("生成事件卡失败，请重试");
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
            问诊工作区
          </Link>
          <span className="text-on-surface-variant">/</span>
          <span className="text-on-surface font-semibold">阶段性结论</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-secondary"></span>
            <span className="text-xs font-medium text-secondary">会话已结束</span>
          </div>
        </div>

        <h1 className="font-headline font-bold text-3xl text-on-surface mb-8">阶段性结论</h1>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <div className="flex gap-2">
              <div className="w-3 h-3 rounded-full bg-primary animate-pulse"></div>
              <div className="w-3 h-3 rounded-full bg-primary animate-pulse delay-75"></div>
              <div className="w-3 h-3 rounded-full bg-primary animate-pulse delay-150"></div>
            </div>
            <p className="text-on-surface-variant text-sm">智能体正在生成结构化结论...</p>
          </div>
        ) : error ? (
          <div className="bg-error-container/30 border border-error/20 rounded-2xl p-6 text-center">
            <p className="text-error font-semibold">{error}</p>
            <div className="flex justify-center gap-3 mt-4">
              <button
                onClick={() => router.push(`/chat/${sessionId}`)}
                className="px-6 py-2 bg-primary text-on-primary rounded-xl font-medium"
              >
                返回继续问诊
              </button>
              {error !== "问诊尚未完成，请返回继续问诊" && (
                <button onClick={generateConclusion} className="px-6 py-2 bg-surface-container-high text-on-surface rounded-xl font-medium">
                  重试
                </button>
              )}
            </div>
          </div>
        ) : eventCard ? (
          <div className="grid grid-cols-12 gap-6">
            {/* 左侧：诊断内容 */}
            <div className="col-span-8 space-y-6">
              {/* 临床判断卡 */}
              <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
                <p className="text-on-surface-variant text-xs uppercase tracking-widest font-bold mb-3">临床判断</p>
                <div className="bg-primary-fixed/30 rounded-xl p-4 mb-4">
                  <h2 className="font-headline font-bold text-2xl text-on-surface">
                    {eventCard.candidate_conditions?.[0]?.name || "待分析"}
                  </h2>
                  <p className="text-on-surface-variant text-sm mt-2 leading-relaxed">
                    主诉：{eventCard.chief_complaint}。
                    {eventCard.symptom_summary?.join("、")}
                  </p>
                </div>
                {/* 症状摘要 */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-surface-container rounded-xl p-4">
                    <p className="text-xs font-bold text-on-surface-variant mb-2 uppercase tracking-wide">已确认症状</p>
                    {eventCard.confirmed_points?.map((pt, i) => (
                      <div key={i} className="flex items-start gap-2 mt-1">
                        <span className="material-symbols-outlined text-secondary text-[16px] mt-0.5" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                        <span className="text-sm text-on-surface">{pt}</span>
                      </div>
                    ))}
                  </div>
                  <div className="bg-surface-container rounded-xl p-4">
                    <p className="text-xs font-bold text-on-surface-variant mb-2 uppercase tracking-wide">待确认信息</p>
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
                    <h4 className="font-headline font-bold text-error text-sm">风险提示</h4>
                    {eventCard.red_flags.map((flag, i) => (
                      <p key={i} className="text-xs text-on-error-container mt-1 leading-relaxed">{flag}</p>
                    ))}
                  </div>
                </div>
              )}

              {/* 分诊与护理建议 */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-surface-container-lowest rounded-2xl p-5 border border-tertiary/20">
                  <p className="text-xs font-bold text-tertiary uppercase tracking-wide mb-3">分诊建议</p>
                  <div className={`flex items-center gap-2 font-headline font-bold text-lg ${triage?.color}`}>
                    <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>{triage?.icon}</span>
                    {triage?.label}
                  </div>
                  <p className="text-sm text-on-surface-variant mt-2">
                    建议科室：<span className="font-semibold text-on-surface">{eventCard.recommended_department}</span>
                  </p>
                </div>
                <div className="bg-surface-container-lowest rounded-2xl p-5 border border-secondary/20">
                  <p className="text-xs font-bold text-secondary uppercase tracking-wide mb-3">护理建议</p>
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
                  <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">就医准备摘要</p>
                  <span className="text-xs text-on-surface-variant flex items-center gap-1">
                    <span className="material-symbols-outlined text-[14px]">verified</span>元数据审计
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div className="text-center">
                    <p className="font-headline font-bold text-2xl text-on-surface">{eventCard.symptom_summary?.length || 0}</p>
                    <p className="text-xs text-on-surface-variant mt-1">症状数据点</p>
                  </div>
                  <div className="text-center">
                    <p className="font-headline font-bold text-2xl text-on-surface">{eventCard.candidate_conditions?.length || 0}</p>
                    <p className="text-xs text-on-surface-variant mt-1">候选方向</p>
                  </div>
                  <div className="text-center">
                    <p className="font-headline font-bold text-2xl text-secondary">
                      {((eventCard.candidate_conditions?.[0]?.confidence || 0) * 100).toFixed(0)}%
                    </p>
                    <p className="text-xs text-on-surface-variant mt-1">置信度（高）</p>
                  </div>
                </div>
                {eventCard.visit_preparation?.length > 0 && (
                  <p className="text-sm text-on-surface-variant italic border-t border-outline-variant/10 pt-3">
                    就诊建议：{eventCard.visit_preparation.join("，")}
                  </p>
                )}
              </div>
            </div>

            {/* 右侧：执行工作区 Sticky */}
            <div className="col-span-4">
              <div className="sticky top-6 space-y-4">
                <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 overflow-hidden shadow-sm">
                  <div className="bg-gradient-to-br from-primary to-primary-container p-4">
                    <span className="text-primary-fixed/80 text-[0.6875rem] font-bold uppercase tracking-widest">执行工作区</span>
                    <h3 className="font-headline font-bold text-on-primary text-lg mt-1">草稿模式</h3>
                  </div>
                  <div className="p-4 space-y-3">
                    <div className="bg-surface-container rounded-xl p-3">
                      <p className="text-xs text-on-surface-variant">主要对象</p>
                      <p className="font-semibold text-on-surface text-sm mt-0.5">当前用户</p>
                    </div>
                    <div className="bg-surface-container rounded-xl p-3">
                      <p className="text-xs text-on-surface-variant">操作类型</p>
                      <p className="font-semibold text-on-surface text-sm mt-0.5">
                        {triage?.label} · {eventCard.recommended_department}
                      </p>
                    </div>
                    <div className="bg-surface-container rounded-xl p-3">
                      <p className="text-xs text-on-surface-variant">优先级</p>
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
                      {generating ? "生成中..." : "确认并执行"}
                    </button>
                    <button
                      onClick={() => router.push(`/chat/${sessionId}`)}
                      className="w-full py-2.5 px-4 bg-surface-container text-on-surface rounded-xl font-medium text-sm flex items-center justify-center gap-2 hover:bg-surface-container-high transition-all"
                    >
                      <span className="material-symbols-outlined text-[16px]">add_comment</span>
                      继续补充
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
