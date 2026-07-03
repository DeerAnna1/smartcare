"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

interface Session {
  session_id: string;
  status: string;
  created_at: string;
  updated_at?: string;
  chief_complaint: string;
  triage_level: string;
  skill_tags?: string[];
  latest_message_id?: string;
  generation_status?: string;
}

const statusLabelZh: Record<string, string> = {
  INIT: "初始化",
  COLLECTING: "采集中",
  FOLLOW_UP: "追问中",
  RISK_ESCALATED: "高风险",
  SUMMARY_READY: "结论已就绪",
  EVENT_CARD_READY: "事件卡已生成",
  CLOSED: "已关闭",
};

const statusLabelEn: Record<string, string> = {
  INIT: "Initialized",
  COLLECTING: "Collecting",
  FOLLOW_UP: "Follow-up",
  RISK_ESCALATED: "High Risk",
  SUMMARY_READY: "Summary Ready",
  EVENT_CARD_READY: "Event Card Generated",
  CLOSED: "Closed",
};

const triageLabelZh: Record<string, string> = {
  observe: "居家观察",
  outpatient: "门诊就诊",
  urgent_visit: "急诊就诊",
  emergency: "立即急救",
};

const triageLabelEn: Record<string, string> = {
  observe: "Home Observation",
  outpatient: "Outpatient",
  urgent_visit: "Urgent Visit",
  emergency: "Emergency",
};

const triageColor: Record<string, string> = {
  observe: "text-secondary",
  outpatient: "text-tertiary",
  urgent_visit: "text-error",
  emergency: "text-error font-bold",
};

export default function ChatListPage() {
  const PAGE_SIZE = 10;
  const FAVORITE_KEY = "chat_favorite_sessions";
  const { lang } = useLang();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<"all" | "active" | "done" | "favorite">("all");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());
  const [readMessageIds, setReadMessageIds] = useState<Set<string>>(new Set());

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(lang === "en" ? "Delete this consultation? This cannot be undone." : "确认删除该问诊记录？此操作不可撤销。")) return;
    setDeletingId(sessionId);
    try {
      await api.deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      setSelectedIds((prev) => { const n = new Set(prev); n.delete(sessionId); return n; });
    } catch {
      alert("删除失败，请重试");
    } finally {
      setDeletingId(null);
    }
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(lang === "en" ? `Delete ${selectedIds.size} selected consultations? This cannot be undone.` : `确认删除选中的 ${selectedIds.size} 条问诊记录？此操作不可撤销。`)) return;
    setBatchDeleting(true);
    try {
      await Promise.all([...selectedIds].map((id) => api.deleteSession(id)));
      setSessions((prev) => prev.filter((s) => !selectedIds.has(s.session_id)));
      setSelectedIds(new Set());
    } catch {
      alert("部分删除失败，请重试");
    } finally {
      setBatchDeleting(false);
    }
  };

  const toggleFavorite = (e: React.MouseEvent, sessionId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setFavoriteIds((prev) => {
      const next = new Set(prev);
      if (next.has(sessionId)) {
        next.delete(sessionId);
      } else {
        next.add(sessionId);
      }
      localStorage.setItem(FAVORITE_KEY, JSON.stringify([...next]));
      return next;
    });
  };

  useEffect(() => {
    const readTimer = window.setTimeout(() => {
      setReadMessageIds(new Set(
        Object.keys(localStorage)
          .filter((key) => key.startsWith("read_message_") && localStorage.getItem(key) === "1")
          .map((key) => key.slice("read_message_".length))
      ));
      const cachedFavorites = localStorage.getItem(FAVORITE_KEY);
      if (cachedFavorites) {
        try {
          setFavoriteIds(new Set(JSON.parse(cachedFavorites) as string[]));
        } catch {
          setFavoriteIds(new Set());
        }
      }
    }, 0);

    let cancelled = false;
    const loadSessions = () => api.listSessions()
      .then((data) => { if (!cancelled) setSessions(data); })
      .catch(() => { if (!cancelled) setSessions([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    void loadSessions();
    const interval = window.setInterval(() => void loadSessions(), 2500);
    return () => { cancelled = true; window.clearTimeout(readTimer); window.clearInterval(interval); };
  }, []);

  const activeCount = sessions.filter((session) => ["INIT", "COLLECTING", "FOLLOW_UP", "RISK_ESCALATED", "SUMMARY_READY"].includes(session.status)).length;
  const doneCount = sessions.filter((session) => ["EVENT_CARD_READY", "CLOSED"].includes(session.status)).length;

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 md:p-6 lg:p-8">
      <section className="sr-only">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-container text-primary">
              <span className="material-symbols-outlined text-[21px]" style={{ fontVariationSettings: "'FILL' 1" }}>forum</span>
            </div>
            <div><h1 className="font-headline text-xl font-bold text-on-surface sm:text-2xl">{lang === "en" ? "Consultation History" : "历史问诊"}</h1>
            <p className="mt-1 text-sm text-on-surface-variant">{lang === "en" ? "Review, continue, and manage your consultations" : "查看、继续并管理您的历史问诊"}</p></div>
          </div>
          <div className="flex items-center gap-3">
            <div className="grid grid-cols-3 gap-2 text-center">
              {[[sessions.length, lang === "en" ? "All" : "全部"], [activeCount, lang === "en" ? "Active" : "进行中"], [doneCount, lang === "en" ? "Done" : "已完成"]].map(([value, label]) => (
                <div key={String(label)} className="min-w-[62px] rounded-xl bg-surface-container px-3 py-2">
                  <p className="font-headline text-lg font-bold text-on-surface">{value}</p><p className="text-[10px] text-on-surface-variant">{label}</p>
                </div>
              ))}
            </div>
            <Link href="/chat/new" className="inline-flex h-10 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-bold text-on-primary transition-opacity hover:opacity-90">
              <span className="material-symbols-outlined text-[19px]">add_comment</span>{lang === "en" ? "New" : "新建问诊"}
            </Link>
          </div>
        </div>
      </section>



      {loading ? (
        <div className="flex items-center justify-center py-24 text-on-surface-variant">
          <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin mr-3" />
          加载中...
        </div>
      ) : sessions.length === 0 ? (
        <div className="text-center py-20 bg-surface-container-lowest rounded-xl border border-outline-variant/15">
          <span className="material-symbols-outlined text-on-surface-variant/40 text-[40px] block mb-3">chat_bubble_outline</span>
          <p className="font-medium text-on-surface">{lang === "en" ? "No consultations yet" : "暂无历史问诊"}</p>
          <p className="text-sm text-on-surface-variant/60 mt-1 mb-4">{lang === "en" ? "Start your first consultation" : "开始第一次问诊吧"}</p>
          <Link href="/chat/new" className="px-4 py-2 bg-primary text-on-primary rounded-lg font-medium text-sm inline-block">{lang === "en" ? "New Consultation" : "新建问诊"}</Link>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-outline-variant/10 bg-surface-container-lowest p-2 shadow-sm mb-4">
              {(["all", "active", "done", "favorite"] as const).map((val) => {
                const labels = lang === "en"
                  ? { all: "All", active: "Active", done: "Done", favorite: "Favorites" }
                  : { all: "全部", active: "进行中", done: "已完成", favorite: "收藏" };
                const counts = {
                  all: sessions.length,
                  active: sessions.filter((s) => ["INIT", "COLLECTING", "FOLLOW_UP", "RISK_ESCALATED", "SUMMARY_READY"].includes(s.status)).length,
                  done: sessions.filter((s) => ["EVENT_CARD_READY", "CLOSED"].includes(s.status)).length,
                  favorite: sessions.filter((s) => favoriteIds.has(s.session_id)).length,
                };
                return (
                  <button
                    key={val}
                    onClick={() => { setFilter(val); setPage(1); }}
                    className={`rounded-xl px-4 py-2 text-xs font-bold transition-all ${
                      filter === val
                        ? "bg-primary text-on-primary shadow-sm"
                        : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
                    }`}
                  >
                    {labels[val]}
                    <span className="ml-1.5 text-xs opacity-70">({counts[val]})</span>
                  </button>
                );
              })}
            </div>
          {(() => {
            const filtered = sessions.filter((s) => {
              if (filter === "active") return ["INIT", "COLLECTING", "FOLLOW_UP", "RISK_ESCALATED", "SUMMARY_READY"].includes(s.status);
              if (filter === "done") return ["EVENT_CARD_READY", "CLOSED"].includes(s.status);
              if (filter === "favorite") return favoriteIds.has(s.session_id);
              return true;
            });
            const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
            const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
            const allPageSelected = pageItems.length > 0 && pageItems.every((s) => selectedIds.has(s.session_id));
            return (
              <>
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-3 mb-3 px-4 py-2.5 bg-error-container/10 border border-error/15 rounded-lg">
              <span className="text-sm font-semibold text-error flex-1">{lang === "en" ? `${selectedIds.size} selected` : `已选 ${selectedIds.size} 条`}</span>
              <button onClick={() => setSelectedIds(new Set())} className="text-xs text-on-surface-variant hover:text-on-surface transition-colors">{lang === "en" ? "Deselect" : "取消选择"}</button>
              <button
                onClick={() => void handleBatchDelete()}
                disabled={batchDeleting}
                className="px-3 py-1.5 bg-error text-on-error rounded-md text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-all flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-[14px]">delete_sweep</span>
                {batchDeleting ? (lang === "en" ? "Deleting..." : "删除中...") : (lang === "en" ? `Delete ${selectedIds.size}` : `删除 ${selectedIds.size} 条`)}
              </button>
            </div>
          )}
          <div className="flex items-center gap-2 mb-2">
            <label className="flex items-center gap-1.5 cursor-pointer select-none text-xs text-on-surface-variant hover:text-on-surface transition-colors">
              <input
                type="checkbox"
                checked={allPageSelected}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedIds((prev) => { const n = new Set(prev); pageItems.forEach((s) => n.add(s.session_id)); return n; });
                  } else {
                    setSelectedIds((prev) => { const n = new Set(prev); pageItems.forEach((s) => n.delete(s.session_id)); return n; });
                  }
                }}
                className="rounded"
              />
              {lang === "en" ? "Select all on page" : "全选当前页"}
            </label>
          </div>
          <div className="space-y-3">
            {pageItems.map((s) => (
            <Link
              key={s.session_id}
              href={`/chat/${s.session_id}`}
              onClick={() => {
                if (s.latest_message_id) {
                  localStorage.setItem(`read_message_${s.latest_message_id}`, "1");
                  setReadMessageIds((prev) => new Set(prev).add(s.latest_message_id as string));
                }
              }}
              className={`group block rounded-2xl border p-5 transition-all hover:-translate-y-0.5 hover:shadow-md ${selectedIds.has(s.session_id) ? "border-primary/35 bg-primary-container/15 shadow-sm" : "border-outline-variant/15 bg-surface-container-lowest hover:border-primary/20"}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <span className="mt-1.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center">
                    {(s.generation_status === "pending" || s.generation_status === "streaming") ? (
                      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary border-t-transparent" title={lang === "en" ? "Generating" : "后台生成中"} />
                    ) : s.generation_status === "completed" && s.latest_message_id && !readMessageIds.has(s.latest_message_id) ? (
                      <span className="inline-block h-2.5 w-2.5 rounded-full bg-blue-500" title={lang === "en" ? "New response" : "有新回复"} />
                    ) : null}
                  </span>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(s.session_id)}
                    onChange={(e) => {
                      e.stopPropagation();
                      setSelectedIds((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(s.session_id);
                        else next.delete(s.session_id);
                        return next;
                      });
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="mt-1 rounded shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-on-surface truncate group-hover:text-primary transition-colors">
                      {s.chief_complaint || s.triage_level || "健康咨询"}
                    </p>
                    <div className="flex items-center gap-3 mt-1 flex-wrap">
                      <span className="text-xs text-on-surface-variant">
                        {new Date(s.updated_at || s.created_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="text-xs bg-surface-container text-on-surface-variant px-2 py-0.5 rounded-full">
                        {(lang === "en" ? statusLabelEn : statusLabelZh)[s.status] ?? s.status}
                      </span>
                      {s.triage_level && (
                        <span className={`text-xs font-medium ${triageColor[s.triage_level] ?? "text-on-surface-variant"}`}>
                          {(lang === "en" ? triageLabelEn : triageLabelZh)[s.triage_level] ?? s.triage_level}
                        </span>
                      )}
                      {s.skill_tags?.map((tag) => (
                        <span key={tag} className="text-xs bg-secondary-container/40 text-secondary px-2 py-0.5 rounded-full flex items-center gap-1">
                          <span className="material-symbols-outlined text-[12px]" style={{ fontVariationSettings: "'FILL' 1" }}>bolt</span>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={(e) => toggleFavorite(e, s.session_id)}
                    className={`p-1.5 rounded-lg transition-all ${
                      favoriteIds.has(s.session_id)
                        ? "text-tertiary bg-tertiary-container/30"
                        : "text-on-surface-variant hover:text-tertiary hover:bg-tertiary-container/20"
                    }`}
                    title={favoriteIds.has(s.session_id) ? (lang === "en" ? "Unfavorite" : "取消收藏") : (lang === "en" ? "Favorite" : "收藏")}
                  >
                    <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: favoriteIds.has(s.session_id) ? "'FILL' 1" : "'FILL' 0" }}>
                      star
                    </span>
                  </button>
                  <button
                    onClick={(e) => void handleDelete(e, s.session_id)}
                    disabled={deletingId === s.session_id}
                    className="p-1.5 text-on-surface-variant hover:text-error hover:bg-error-container/20 rounded-lg transition-all disabled:opacity-40"
                    title={lang === "en" ? "Delete" : "删除"}
                  >
                    <span className="material-symbols-outlined text-[18px]">
                      {deletingId === s.session_id ? "hourglass_empty" : "delete"}
                    </span>
                  </button>
                  <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">
                    chevron_right
                  </span>
                </div>
              </div>
            </Link>
            ))}
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-1 mt-6 pt-4 border-t border-outline-variant/10">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-md text-sm text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low transition-all disabled:opacity-30"
              >
                {lang === "en" ? "Prev" : "上一页"}
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`w-8 h-8 rounded-md text-sm font-medium transition-all ${
                    page === p ? "bg-primary/10 text-primary" : "text-on-surface-variant hover:bg-surface-container-low"
                  }`}
                >
                  {p}
                </button>
              ))}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 rounded-md text-sm text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low transition-all disabled:opacity-30"
              >
                {lang === "en" ? "Next" : "下一页"}
              </button>
            </div>
          )}
              </>
            );
          })()}
        </>
      )}
    </div>
  );
}
