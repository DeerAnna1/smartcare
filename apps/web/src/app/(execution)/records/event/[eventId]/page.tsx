"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api-client";

type EventDetail = {
  event_id: string;
  source_session_id?: string;
  status: string;
  chief_complaint: string;
  symptom_summary: string[];
  triage_level: string;
  recommended_department: string;
  candidate_conditions: Array<{ name: string; confidence?: number }>;
  created_at?: string;
};

export default function RecordEventDetailPage() {
  const router = useRouter();
  const params = useParams<{ eventId: string }>();
  const eventId = params?.eventId ?? "";

  const [loading, setLoading] = useState(true);
  const [eventDetail, setEventDetail] = useState<EventDetail | null>(null);
  const [archiving, setArchiving] = useState(false);

  useEffect(() => {
    if (!eventId) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    api
      .getEvent(eventId)
      .then((data) => {
        if (cancelled) return;
        setEventDetail(data as EventDetail);
      })
      .catch(() => {
        if (cancelled) return;
        setEventDetail(null);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [eventId]);

  if (loading) {
    return <div className="p-8 text-on-surface-variant">加载事件详情中...</div>;
  }

  if (!eventDetail) {
    return (
      <div className="p-8">
        <p className="text-error font-semibold">事件详情不存在或加载失败</p>
        <button
          onClick={() => router.push("/records")}
          className="mt-4 px-4 py-2 rounded-xl bg-primary text-on-primary"
        >
          返回存档会话
        </button>
      </div>
    );
  }

  const topCondition = eventDetail.candidate_conditions?.[0];

  const handleArchive = async () => {
    if (!eventId || archiving) return;
    setArchiving(true);
    try {
      await api.archiveEvent(eventId);
      alert("已归档到健康档案");
    } catch {
      alert("归档失败，请重试");
    } finally {
      setArchiving(false);
    }
  };

  return (
    <div className="p-8 space-y-6">
      <button
        onClick={() => router.push("/records")}
        className="inline-flex items-center gap-2 text-sm text-on-surface-variant hover:text-primary transition-colors"
      >
        <span className="material-symbols-outlined text-[18px]">arrow_back</span>
        返回历史会话
      </button>

      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-on-surface-variant uppercase tracking-widest">存档会话 / 事件详情</p>
          <h1 className="font-headline font-bold text-3xl text-on-surface mt-1">健康事件详情</h1>
        </div>
        <span className="px-3 py-1 rounded-full bg-primary-container/40 text-primary text-xs font-semibold">
          {eventDetail.status}
        </span>
      </div>

      <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 p-6 space-y-4">
        <div>
          <p className="text-xs text-on-surface-variant">主诉</p>
          <p className="text-on-surface font-semibold mt-1">{eventDetail.chief_complaint || "无"}</p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-on-surface-variant">分诊级别</p>
            <p className="text-on-surface mt-1">{eventDetail.triage_level || "未标记"}</p>
          </div>
          <div>
            <p className="text-xs text-on-surface-variant">建议科室</p>
            <p className="text-on-surface mt-1">{eventDetail.recommended_department || "未标记"}</p>
          </div>
        </div>

        <div>
          <p className="text-xs text-on-surface-variant mb-2">症状摘要</p>
          <div className="flex flex-wrap gap-2">
            {(eventDetail.symptom_summary || []).map((symptom, idx) => (
              <span
                key={`${symptom}-${idx}`}
                className="px-3 py-1 rounded-full bg-surface-container text-on-surface text-xs"
              >
                {symptom}
              </span>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs text-on-surface-variant">候选诊断方向</p>
          <p className="text-on-surface mt-1">
            {topCondition?.name || "暂无"}
            {typeof topCondition?.confidence === "number" && (
              <span className="text-on-surface-variant text-sm ml-2">
                置信度 {(topCondition.confidence * 100).toFixed(0)}%
              </span>
            )}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => router.push("/records")}
          className="px-5 py-2.5 rounded-xl bg-surface-container text-on-surface font-semibold hover:bg-surface-container-high transition-all"
        >
          返回存档会话
        </button>

        <button
          onClick={handleArchive}
          disabled={archiving}
          className="px-5 py-2.5 rounded-xl bg-secondary text-on-secondary font-semibold hover:opacity-90 transition-all disabled:opacity-50"
        >
          {archiving ? "归档中..." : "归档到健康档案"}
        </button>

        <button
          onClick={() =>
            eventDetail.source_session_id
              ? router.push(`/chat/${eventDetail.source_session_id}`)
              : undefined
          }
          disabled={!eventDetail.source_session_id}
          className="px-5 py-2.5 rounded-xl bg-primary text-on-primary font-semibold hover:opacity-90 transition-all disabled:opacity-50"
        >
          返回会话继续 AI 诊断
        </button>
      </div>
    </div>
  );
}
