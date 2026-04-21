"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";

interface Session {
  session_id: string;
  status: string;
  created_at: string;
  chief_complaint: string;
  triage_level: string;
  skill_tags?: string[];
}

const statusLabel: Record<string, string> = {
  INIT: "初始化",
  COLLECTING: "采集中",
  FOLLOW_UP: "追问中",
  RISK_ESCALATED: "高风险",
  SUMMARY_READY: "结论已就绪",
  EVENT_CARD_READY: "事件卡已生成",
  CLOSED: "已关闭",
};

const triageLabel: Record<string, string> = {
  observe: "居家观察",
  outpatient: "门诊就诊",
  urgent_visit: "急诊就诊",
  emergency: "立即急救",
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
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<"all" | "active" | "done" | "favorite">("all");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("确认删除该问诊记录？此操作不可撤销。")) return;
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
    if (!confirm(`确认删除选中的 ${selectedIds.size} 条问诊记录？此操作不可撤销。`)) return;
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
    const cachedFavorites = localStorage.getItem(FAVORITE_KEY);
    if (cachedFavorites) {
      try {
        setFavoriteIds(new Set(JSON.parse(cachedFavorites) as string[]));
      } catch {
        setFavoriteIds(new Set());
      }
    }

    api.listSessions()
      .then((data) => setSessions(data))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-headline font-bold text-3xl text-on-surface">历史问诊</h1>
          <p className="text-on-surface-variant text-sm mt-1">查看并继续以往的问诊记录</p>
        </div>
      </div>



      {loading ? (
        <div className="flex items-center justify-center py-24 text-on-surface-variant">
          <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin mr-3" />
          加载中...
        </div>
      ) : sessions.length === 0 ? (
        <div className="text-center py-24 bg-surface-container-lowest rounded-2xl border border-outline-variant/10">
          <span className="material-symbols-outlined text-on-surface-variant text-[48px] block mb-3">chat_bubble_outline</span>
          <p className="font-semibold text-on-surface">暂无历史问诊</p>
          <p className="text-sm text-on-surface-variant mt-1 mb-4">开始第一次问诊吧</p>
          <Link href="/chat/new" className="px-5 py-2.5 bg-primary text-on-primary rounded-xl font-semibold text-sm inline-block">新建问诊</Link>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 flex-wrap mb-4">
              {(["all", "active", "done", "favorite"] as const).map((val) => {
                const labels = { all: "全部", active: "进行中", done: "已完成", favorite: "收藏" };
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
                    className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-all ${
                      filter === val
                        ? "bg-primary text-on-primary shadow-sm"
                        : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high"
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
            <div className="flex items-center gap-3 mb-3 px-4 py-2.5 bg-error-container/20 border border-error/20 rounded-xl">
              <span className="text-sm font-semibold text-error flex-1">已选 {selectedIds.size} 条</span>
              <button onClick={() => setSelectedIds(new Set())} className="text-xs text-on-surface-variant hover:text-on-surface transition-colors">取消选择</button>
              <button
                onClick={() => void handleBatchDelete()}
                disabled={batchDeleting}
                className="px-3 py-1.5 bg-error text-on-error rounded-xl text-xs font-semibold hover:opacity-90 disabled:opacity-50 transition-all flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-[14px]">delete_sweep</span>
                {batchDeleting ? "删除中..." : `删除 ${selectedIds.size} 条`}
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
              全选当前页
            </label>
          </div>
          <div className="space-y-3">
            {pageItems.map((s) => (
            <Link
              key={s.session_id}
              href={`/chat/${s.session_id}`}
              className={`block rounded-2xl border shadow-sm p-5 hover:shadow-md transition-all group ${selectedIds.has(s.session_id) ? "bg-primary-fixed/20 border-primary/30" : "bg-surface-container-lowest border-outline-variant/10"}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(s.session_id)}
                    onChange={(e) => {
                      e.stopPropagation();
                      setSelectedIds((prev) => { const n = new Set(prev); e.target.checked ? n.add(s.session_id) : n.delete(s.session_id); return n; });
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
                        {new Date(s.created_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="text-xs bg-surface-container text-on-surface-variant px-2 py-0.5 rounded-full">
                        {statusLabel[s.status] ?? s.status}
                      </span>
                      {s.triage_level && (
                        <span className={`text-xs font-medium ${triageColor[s.triage_level] ?? "text-on-surface-variant"}`}>
                          {triageLabel[s.triage_level] ?? s.triage_level}
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
                    title={favoriteIds.has(s.session_id) ? "取消收藏" : "收藏"}
                  >
                    <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: favoriteIds.has(s.session_id) ? "'FILL' 1" : "'FILL' 0" }}>
                      star
                    </span>
                  </button>
                  <button
                    onClick={(e) => void handleDelete(e, s.session_id)}
                    disabled={deletingId === s.session_id}
                    className="p-1.5 text-on-surface-variant hover:text-error hover:bg-error-container/20 rounded-lg transition-all disabled:opacity-40"
                    title="删除"
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
            <div className="flex items-center justify-center gap-2 mt-6 pt-4 border-t border-outline-variant/10">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-xl text-sm font-medium text-on-surface-variant hover:bg-surface-container transition-all disabled:opacity-40"
              >
                上一页
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`w-8 h-8 rounded-xl text-sm font-semibold transition-all ${
                    page === p ? "bg-primary text-on-primary" : "text-on-surface-variant hover:bg-surface-container"
                  }`}
                >
                  {p}
                </button>
              ))}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 rounded-xl text-sm font-medium text-on-surface-variant hover:bg-surface-container transition-all disabled:opacity-40"
              >
                下一页
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
