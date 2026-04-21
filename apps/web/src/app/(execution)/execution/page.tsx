"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api-client";

interface EventSummary {
  event_id: string;
  status: string;
  chief_complaint: string;
  triage_level: string;
  recommended_department: string;
  created_at: string;
  source_session_id?: string;
  archived?: boolean;
}

interface Task {
  id: string;
  type: "medication" | "followup" | "record" | "care";
  title: string;
  description: string;
  priority: "high" | "medium" | "low";
  actionable: boolean;
  status?: "pending" | "executing" | "completed";
}

function ExecutionContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const eventId = searchParams.get("eventId");

  const PAGE_SIZE = 10;
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [currentEvent, setCurrentEvent] = useState<EventSummary | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [completionRate, setCompletionRate] = useState(0);
  const [executed, setExecuted] = useState(false);
  const [executingTaskId, setExecutingTaskId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "pending" | "done">("all");
  const [page, setPage] = useState(1);
  const [archivingId, setArchivingId] = useState<string | null>(null);

  useEffect(() => {
    if (!eventId) {
      let cancelled = false;
      setLoading(true);
      setTasks([]);
      api.listEvents().then((data) => {
        if (cancelled) return;
        setEvents(data || []);
        setLoading(false);
      }).catch(() => {
        if (cancelled) return;
        setEvents([]);
        setLoading(false);
      });

      return () => {
        cancelled = true;
      };
    }

    let cancelled = false;
    setLoading(true);
    setEvents([]);
    setCurrentEvent(null);
    setTasks([]);
    setExecuted(false);
    setCompletionRate(0);

    Promise.all([api.getEvent(eventId), api.getEventTasks(eventId)]).then(([eventData, taskData]) => {
      if (cancelled) return;
      const tasksWithStatus = (taskData.tasks || []).map((t: Task) => ({
        ...t,
        status: t.status || ("pending" as const),
      }));
      setCurrentEvent(eventData as EventSummary);
      setTasks(tasksWithStatus);
      setLoading(false);
    }).catch(() => {
      if (cancelled) return;
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [eventId]);

  const handleTaskClick = async (taskId: string) => {
    const task = tasks.find((t) => t.id === taskId);
    if (!task || executingTaskId || task.status === "completed" || !eventId) return;

    setExecutingTaskId(taskId);
    setTasks((prev) =>
      prev.map((t) =>
        t.id === taskId ? { ...t, status: "executing" } : t
      )
    );

    try {
      // 调用后端 API 保存任务完成状态
      await api.completeTask(eventId, taskId);

      // 延迟后标记为完成
      setTimeout(() => {
        setTasks((prev) =>
          prev.map((t) =>
            t.id === taskId ? { ...t, status: "completed" } : t
          )
        );
        setExecutingTaskId(null);
      }, 600);
    } catch (error) {
      // 恢复状态
      setTasks((prev) =>
        prev.map((t) =>
          t.id === taskId ? { ...t, status: "pending" } : t
        )
      );
      setExecutingTaskId(null);
      alert("标记任务失败，请重试");
    }
  };

  const completedCount = tasks.filter((t) => t.status === "completed").length;

  const handleArchive = async (eid: string) => {
    if (archivingId) return;
    setArchivingId(eid);
    try {
      await api.archiveEvent(eid);
      setEvents((prev) => prev.map((e) => e.event_id === eid ? { ...e, archived: true } : e));
    } catch {
      alert("归档失败，请重试");
    } finally {
      setArchivingId(null);
    }
  };

  const handleExecute = async () => {
    if (!eventId || executing) return;
    setExecuting(true);
    setCompletionRate(0);

    try {
      // 模拟任务执行进度
      const interval = setInterval(() => {
        setCompletionRate((prev) => {
          if (prev >= 90) {
            clearInterval(interval);
            return 90;
          }
          return prev + Math.random() * 30;
        });
      }, 400);

      // 调用后端执行 API
      await api.executeEvent(eventId);

      // 执行后重新拉取任务，确保任务清单和进度条与后端一致
      const taskData = await api.getEventTasks(eventId);
      const refreshedTasks: Task[] = (taskData.tasks || []).map((t: Task) => ({
        ...t,
        status: t.status || ("pending" as const),
      }));
      setTasks(refreshedTasks);
      
      clearInterval(interval);
      setCompletionRate(100);
      setExecuted(refreshedTasks.length > 0 && refreshedTasks.every((t: Task) => t.status === "completed"));
      setExecuting(false);
    } catch (error) {
      setExecuting(false);
      alert("执行失败，请重试");
    }
  };

  if (!eventId) {
    const triageLabelMap: Record<string, string> = {
      observe: "居家观察",
      outpatient: "门诊就诊",
      urgent_visit: "急诊就诊",
      emergency: "立即急救",
    };
    const statusLabelMap: Record<string, string> = {
      CREATED: "已创建",
      CONFIRMED: "已确认",
      EXECUTED: "已执行",
    };
    const filteredEvents = events.filter((e) => {
      if (filter === "pending") return e.status !== "EXECUTED";
      if (filter === "done") return e.status === "EXECUTED";
      return true;
    });
    const totalPages = Math.ceil(filteredEvents.length / PAGE_SIZE);
    const pagedEvents = filteredEvents.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    return (
      <div className="p-8 space-y-6">
        <div className="bg-primary-fixed/30 border-l-4 border-primary rounded-r-xl px-6 py-3 flex items-center justify-between">
          <div>
            <h1 className="font-headline font-bold text-xl text-on-surface">通用执行</h1>
            <p className="text-on-surface-variant text-sm">点击任意事件查看执行详情与任务清单</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-secondary"></span>
            <span className="text-xs font-semibold text-secondary">系统运行中</span>
          </div>
        </div>

        <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
          <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              {(["all", "pending", "done"] as const).map((val) => {
                const labels = { all: "全部", pending: "未完成", done: "已完成" };
                const counts = {
                  all: events.length,
                  pending: events.filter((e) => e.status !== "EXECUTED").length,
                  done: events.filter((e) => e.status === "EXECUTED").length,
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
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-primary-container/40 text-primary">
              共 {filteredEvents.length} 条
            </span>
          </div>

          {loading ? (
            <div className="py-12 text-center text-on-surface-variant">加载中...</div>
          ) : filteredEvents.length === 0 ? (
            <div className="py-12 text-center text-on-surface-variant">
              {filter === "pending" ? "暂无未完成事件" : filter === "done" ? "暂无已完成事件" : "暂无健康事件"}
            </div>
          ) : (
            <>
              <div className="space-y-3">
                {pagedEvents.map((event) => {
                  const createdAt = new Date(event.created_at).toLocaleString("zh-CN", { hour12: false });
                  const isArchiving = archivingId === event.event_id;
                  return (
                    <div key={event.event_id} className="flex items-center gap-3 p-4 rounded-xl bg-surface-container border border-transparent hover:border-outline-variant/20 transition-all">
                      <button
                        onClick={() => router.push(`/execution?eventId=${event.event_id}`)}
                        className="flex items-start gap-4 flex-1 text-left min-w-0"
                      >
                        <div className="w-11 h-11 rounded-2xl bg-primary-fixed/40 flex items-center justify-center shrink-0">
                          <span className="material-symbols-outlined text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>assignment</span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="font-semibold text-on-surface truncate">{event.chief_complaint || "健康事件"}</p>
                            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                              event.status === "EXECUTED"
                                ? "bg-secondary-container/40 text-secondary"
                                : event.status === "CONFIRMED"
                                ? "bg-primary-container/40 text-primary"
                                : "bg-surface-container-high text-on-surface-variant"
                            }`}>
                              {statusLabelMap[event.status] ?? event.status}
                            </span>
                            {event.archived && (
                              <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-tertiary-container/40 text-tertiary">已归档</span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 mt-1 text-xs text-on-surface-variant flex-wrap">
                            <span>{createdAt}</span>
                            {event.recommended_department && <span>{event.recommended_department}</span>}
                            {event.triage_level && <span>{triageLabelMap[event.triage_level] ?? event.triage_level}</span>}
                          </div>
                        </div>
                      </button>
                      <div className="shrink-0 flex items-center gap-2">
                        <button
                          onClick={() => handleArchive(event.event_id)}
                          disabled={Boolean(event.archived) || isArchiving}
                          className="px-3 py-1.5 rounded-xl text-xs font-semibold transition-all disabled:opacity-50 bg-primary text-on-primary hover:opacity-80"
                        >
                          {event.archived ? "已归档" : isArchiving ? "归档中..." : "归档到档案"}
                        </button>
                        <span className="material-symbols-outlined text-on-surface-variant text-[18px]">chevron_right</span>
                      </div>
                    </div>
                  );
                })}
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
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      {/* 返回按钮 */}
      <button
        onClick={() => router.push("/execution")}
        className="flex items-center gap-1.5 mb-4 text-sm font-medium text-on-surface-variant hover:text-primary transition-colors"
      >
        <span className="material-symbols-outlined text-[18px]">arrow_back</span>
        返回列表
      </button>

      {/* 执行区域指示条 */}
      <div className="bg-primary-fixed/30 border-l-4 border-primary rounded-r-xl px-6 py-3 mb-6 flex items-center justify-between">
        <div>
          <p className="text-xs font-bold text-primary uppercase tracking-widest">执行区域</p>
          <h1 className="font-headline font-bold text-xl text-on-surface mt-0.5">执行控制台</h1>
          <p className="text-on-surface-variant text-sm">基于诊断事件 {eventId.slice(0, 8)}... 的执行任务</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-secondary"></span>
          <span className="text-xs font-semibold text-secondary">系统运行中</span>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* 左侧：任务列表 */}
        <div className="col-span-8 space-y-6">
          <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-headline font-bold text-on-surface">任务清单</h2>
              <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                completedCount === tasks.length && tasks.length > 0
                  ? "bg-secondary-container/40 text-secondary"
                  : "bg-primary-container/40 text-primary"
              }`}>
                {completedCount}/{tasks.length} 已完成
              </span>
            </div>
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="flex flex-col items-center gap-2">
                  <div className="flex gap-2">
                    <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
                    <div className="w-2 h-2 rounded-full bg-primary animate-pulse delay-75"></div>
                    <div className="w-2 h-2 rounded-full bg-primary animate-pulse delay-150"></div>
                  </div>
                  <p className="text-sm text-on-surface-variant">加载任务中...</p>
                </div>
              </div>
            ) : tasks.length === 0 ? (
              <div className="flex items-center justify-center py-12">
                <p className="text-on-surface-variant">暂无任务</p>
              </div>
            ) : (
              <div className="space-y-3">
                {tasks.map((task) => (
                  <div
                    key={task.id}
                    onClick={() => !executed && handleTaskClick(task.id)}
                    className={`flex items-start gap-4 p-4 rounded-xl transition-all cursor-pointer ${
                      task.status === "completed"
                        ? "bg-secondary-container/20 border border-secondary/30"
                        : task.status === "executing"
                        ? "bg-primary-container/20 border border-primary/30 animate-pulse"
                        : "bg-surface-container hover:bg-surface-container-high border border-transparent"
                    }`}
                  >
                    <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition-all ${
                      task.status === "completed"
                        ? "border-secondary bg-secondary/20"
                        : task.status === "executing"
                        ? "border-primary bg-primary/20 animate-spin"
                        : task.actionable
                        ? "border-primary bg-primary/20"
                        : "border-outline-variant"
                    }`}>
                      {task.status === "completed" ? (
                        <span className="text-secondary text-sm">✓</span>
                      ) : task.actionable && task.status !== "executing" ? (
                        <span className="w-2 h-2 rounded-full bg-primary"></span>
                      ) : null}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <p className={`font-semibold ${
                          task.status === "completed"
                            ? "text-on-surface/60 line-through"
                            : "text-on-surface"
                        }`}>
                          {task.title}
                        </p>
                        {task.priority === "high" && (
                          <span className="px-2 py-1 bg-error-container/40 text-error rounded-full text-xs font-bold">
                            高优先级
                          </span>
                        )}
                      </div>
                      <p className={`text-sm mt-1 ${
                        task.status === "completed"
                          ? "text-on-surface-variant/60"
                          : "text-on-surface-variant"
                      }`}>
                        {task.description}
                      </p>
                      <div className="flex items-center gap-2 mt-2">
                        <span className={`text-xs px-2 py-1 rounded-full ${
                          task.type === "medication" ? "bg-secondary-container/40 text-secondary" :
                          task.type === "followup" ? "bg-tertiary-container/40 text-tertiary" :
                          task.type === "record" ? "bg-primary-container/40 text-primary" :
                          "bg-surface-container/40 text-on-surface-variant"
                        }`}>
                          {task.type === "medication" ? "用药" : 
                           task.type === "followup" ? "随访" :
                           task.type === "record" ? "档案" : "护理"}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 执行进度 */}
          <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
            <h2 className="font-headline font-bold text-on-surface mb-4">执行进度</h2>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-on-surface-variant">完成度</span>
              <span className="text-sm font-semibold text-primary">
                {tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0}%
              </span>
            </div>
            <div className="h-2 bg-surface-container rounded-full overflow-hidden">
              <div 
                className="h-full bg-primary rounded-full transition-all duration-300" 
                style={{ width: `${tasks.length > 0 ? (completedCount / tasks.length) * 100 : completionRate}%` }}
              ></div>
            </div>
            <p className="text-xs text-on-surface-variant mt-3">
              {executing ? "正在执行任务..." : executed ? "所有任务已执行完成" : `已完成 ${completedCount}/${tasks.length} 项任务`}
            </p>
          </div>
        </div>

        {/* 右侧：操作区 */}
        <div className="col-span-4 space-y-4">
          <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
            <h2 className="font-headline font-bold text-on-surface mb-4">快速操作</h2>
            <div className="space-y-3">
              <button 
                onClick={() => router.push(`/event-confirm/${eventId}`)}
                className="w-full py-3 px-4 bg-surface-container text-on-surface rounded-xl font-semibold hover:bg-surface-container-high transition-all"
              >
                返回事件卡
              </button>
              <button 
                onClick={handleExecute}
                disabled={executing || executed}
                className={`w-full py-3 px-4 rounded-xl font-semibold transition-all ${
                  executing ? "bg-primary/50 text-on-primary cursor-wait" :
                  executed ? "bg-primary-container text-primary cursor-default" :
                  "bg-primary text-on-primary hover:opacity-90 cursor-pointer"
                }`}
              >
                {executing ? "执行中..." : executed ? "已执行完成" : "执行所有任务"}
              </button>
            </div>
          </div>

          <div className="bg-primary-fixed/30 rounded-2xl p-6 border border-primary/20">
            <p className="text-xs font-bold text-primary uppercase tracking-widest">系统状态</p>
            <p className="text-sm text-on-surface mt-2">所有任务已就绪，等待用户触发执行</p>
          </div>

          <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
            <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">继续诊断</p>
            <p className="text-sm text-on-surface mt-2">需要回到原始问诊会话补充信息时，可直接返回继续 AI 诊断。</p>
            <button
              onClick={() => currentEvent?.source_session_id && router.push(`/chat/${currentEvent.source_session_id}`)}
              disabled={!currentEvent?.source_session_id}
              className="mt-4 w-full py-3 px-4 rounded-xl bg-primary text-on-primary font-semibold hover:opacity-90 transition-all disabled:opacity-50"
            >
              返回继续 AI 诊断
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ExecutionPage() {
  return (
    <Suspense fallback={<div className="p-8">加载中...</div>}>
      <ExecutionContent />
    </Suspense>
  );
}
