"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

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
  const { lang } = useLang();
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
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (!eventId) {
      let cancelled = false;
      // Reset list state when switching from detail mode.
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
    } catch {
      // 恢复状态
      setTasks((prev) =>
        prev.map((t) =>
          t.id === taskId ? { ...t, status: "pending" } : t
        )
      );
      setExecutingTaskId(null);
      alert(t("标记任务失败，请重试", "Failed to mark task, please retry"));
    }
  };

  const completedCount = tasks.filter((t) => t.status === "completed").length;

  const handleArchive = async (eid: string) => {
    if (archivingId) return;
    setArchivingId(eid);
    try {
      await api.archiveEvent(eid);
      setEvents((prev) => prev.map((e) => e.event_id === eid ? { ...e, archived: true } : e));
      setCurrentEvent((prev) => prev?.event_id === eid ? { ...prev, archived: true } : prev);
    } catch {
      alert(t("归档失败，请重试", "Archive failed, please retry"));
    } finally {
      setArchivingId(null);
    }
  };

  const handleUnarchive = async (eid: string) => {
    if (archivingId) return;
    if (!confirm(t("取消归档将同时删除关联健康档案及已同步的 EHR 数据，确定继续？", "Unarchiving also removes the linked health record and synced EHR data. Continue?"))) return;
    setArchivingId(eid);
    try {
      await api.unarchiveEvent(eid);
      setEvents((prev) => prev.map((e) => e.event_id === eid ? { ...e, archived: false } : e));
      setCurrentEvent((prev) => prev?.event_id === eid ? { ...prev, archived: false } : prev);
    } catch {
      alert(t("取消归档失败，请重试", "Failed to unarchive, please retry"));
    } finally {
      setArchivingId(null);
    }
  };

  const handleDelete = async (eid: string) => {
    if (deletingId) return;
    if (!confirm(t("确定删除该通用执行？关联的健康档案、EHR 同步数据和提醒也会删除，此操作不可撤销。", "Delete this execution? Linked health records, EHR sync data, and reminders will also be deleted. This cannot be undone."))) return;
    setDeletingId(eid);
    try {
      await api.deleteEvent(eid);
      setEvents((prev) => prev.filter((e) => e.event_id !== eid));
      if (eventId === eid) router.push("/execution");
    } catch {
      alert(t("删除失败，请重试", "Delete failed, please retry"));
    } finally {
      setDeletingId(null);
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
    } catch {
      setExecuting(false);
      alert(t("执行失败，请重试", "Execution failed, please retry"));
    }
  };

  const t = (zh: string, en: string) => lang === "en" ? en : zh;

  if (!eventId) {
    const triageLabelMap: Record<string, string> = lang === "en" ? {
      observe: "Home Observation", outpatient: "Outpatient", urgent_visit: "Urgent Visit", emergency: "Emergency",
    } : {
      observe: "居家观察", outpatient: "门诊就诊", urgent_visit: "急诊就诊", emergency: "立即急救",
    };
    const statusLabelMap: Record<string, string> = lang === "en" ? {
      CREATED: "Created", CONFIRMED: "Confirmed", EXECUTED: "Executed",
    } : {
      CREATED: "已创建", CONFIRMED: "已确认", EXECUTED: "已执行",
    };
    const filteredEvents = events.filter((e) => {
      if (filter === "pending") return e.status !== "EXECUTED";
      if (filter === "done") return e.status === "EXECUTED";
      return true;
    });
    const totalPages = Math.ceil(filteredEvents.length / PAGE_SIZE);
    const pagedEvents = filteredEvents.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    return (
      <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
        <section className="sr-only">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-container text-primary">
                <span className="material-symbols-outlined text-[21px]" style={{ fontVariationSettings: "'FILL' 1" }}>conversion_path</span>
              </div>
              <div><h1 className="font-headline text-xl font-bold text-on-surface sm:text-2xl">{t("通用执行", "Execution Workspace")}</h1>
              <p className="mt-1 text-sm text-on-surface-variant">{t("将问诊结论转化为可追踪、可归档的健康行动", "Turn consultation outcomes into trackable health actions")}</p></div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[
                [events.length, t("全部", "All"), "assignment"],
                [events.filter((event) => event.status !== "EXECUTED").length, t("未完成", "Pending"), "pending_actions"],
                [events.filter((event) => event.status === "EXECUTED").length, t("已完成", "Done"), "task_alt"],
              ].map(([value, label, icon]) => (
                <div key={String(label)} className="min-w-[76px] rounded-xl bg-surface-container px-3 py-2">
                  <div className="flex items-center justify-between gap-2"><span className="material-symbols-outlined text-[16px] text-on-surface-variant">{icon}</span><span className="font-headline text-lg font-bold text-on-surface">{value}</span></div>
                  <p className="text-[10px] font-semibold text-on-surface-variant">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="rounded-3xl border border-outline-variant/10 bg-surface-container-lowest p-4 shadow-sm sm:p-6">
          <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              {(["all", "pending", "done"] as const).map((val) => {
                const labels = lang === "en" ? { all: "All", pending: "Pending", done: "Done" } : { all: "全部", pending: "未完成", done: "已完成" };
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
              {t(`共 ${filteredEvents.length} 条`, `${filteredEvents.length} items`)}
            </span>
          </div>

          {loading ? (
            <div className="py-12 text-center text-on-surface-variant">{t("加载中...", "Loading...")}</div>
          ) : filteredEvents.length === 0 ? (
            <div className="py-12 text-center text-on-surface-variant">
              {filter === "pending" ? t("暂无未完成事件", "No pending events") : filter === "done" ? t("暂无已完成事件", "No completed events") : t("暂无健康事件", "No health events")}
            </div>
          ) : (
            <>
              <div className="space-y-3">
                {pagedEvents.map((event) => {
                  const createdAt = new Date(event.created_at).toLocaleString("zh-CN", { hour12: false });
                  const isArchiving = archivingId === event.event_id;
                  return (
                    <div key={event.event_id} className="flex flex-col gap-3 rounded-2xl border border-outline-variant/10 bg-surface-container-low p-4 transition-all hover:-translate-y-0.5 hover:border-primary/20 hover:bg-surface-container-lowest hover:shadow-md sm:flex-row sm:items-center">
                      <button
                        onClick={() => router.push(`/execution?eventId=${event.event_id}`)}
                        className="flex items-start gap-3 sm:gap-4 flex-1 text-left min-w-0"
                      >
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary-container">
                          <span className="material-symbols-outlined text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>assignment</span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="font-semibold text-on-surface min-w-0 truncate">{event.chief_complaint || t("健康事件", "Health Event")}</p>
                            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold shrink-0 ${
                              event.status === "EXECUTED"
                                ? "bg-secondary-container/40 text-secondary"
                                : event.status === "CONFIRMED"
                                ? "bg-primary-container/40 text-primary"
                                : "bg-surface-container-high text-on-surface-variant"
                            }`}>
                              {statusLabelMap[event.status] ?? event.status}
                            </span>
                            {event.archived && (
                              <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-tertiary-container/40 text-tertiary shrink-0">{t("已归档", "Archived")}</span>
                            )}
                          </div>
                          <div className="flex items-center gap-x-3 gap-y-1 mt-1 text-xs text-on-surface-variant flex-wrap">
                            <span>{createdAt}</span>
                            {event.recommended_department && <span>{event.recommended_department}</span>}
                            {event.triage_level && <span>{triageLabelMap[event.triage_level] ?? event.triage_level}</span>}
                          </div>
                        </div>
                      </button>
                      <div className="flex items-center gap-2 sm:shrink-0 self-end sm:self-center">
                        <button
                          onClick={() => event.archived ? handleUnarchive(event.event_id) : handleArchive(event.event_id)}
                          disabled={isArchiving}
                          className="px-3 py-1.5 rounded-xl text-xs font-semibold transition-all disabled:opacity-50 bg-primary text-on-primary hover:opacity-80"
                        >
                          {isArchiving ? t("处理中...", "Processing...") : event.archived ? t("取消归档", "Unarchive") : t("归档", "Archive")}
                        </button>
                        <button
                          onClick={() => handleDelete(event.event_id)}
                          disabled={deletingId === event.event_id}
                          className="px-3 py-1.5 rounded-xl text-xs font-semibold transition-all disabled:opacity-50 bg-error-container text-error hover:opacity-80"
                        >
                          {deletingId === event.event_id ? t("删除中...", "Deleting...") : t("删除", "Delete")}
                        </button>
                        <span className="material-symbols-outlined text-on-surface-variant text-[18px] hidden sm:block">chevron_right</span>
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
                    {t("上一页", "Prev")}
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
                    {t("下一页", "Next")}
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
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">
      {/* 返回按钮 */}
      <button
        onClick={() => router.push("/execution")}
        className="flex items-center gap-1.5 mb-4 text-sm font-medium text-on-surface-variant hover:text-primary transition-colors"
      >
        <span className="material-symbols-outlined text-[18px]">arrow_back</span>
        {t("返回列表", "Back to list")}
      </button>

      {/* 执行区域指示条 */}
      <div className="mb-6 flex items-center justify-between rounded-3xl bg-gradient-to-r from-primary-container/70 to-secondary-container/35 px-5 py-5 shadow-sm ring-1 ring-outline-variant/10 sm:px-7">
        <div>
          <p className="text-xs font-bold text-primary uppercase tracking-widest">{t("执行区域", "EXECUTION")}</p>
          <h1 className="font-headline font-bold text-xl text-on-surface mt-0.5">{t("执行控制台", "Execution Console")}</h1>
          <p className="text-on-surface-variant text-sm">{t(`基于诊断事件 ${eventId.slice(0, 8)}... 的执行任务`, `Tasks for event ${eventId.slice(0, 8)}...`)}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-secondary"></span>
          <span className="text-xs font-semibold text-secondary">{t("系统运行中", "System Running")}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* 左侧：任务列表 */}
        <div className="space-y-6 lg:col-span-8">
          <div className="rounded-3xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-headline font-bold text-on-surface">{t("任务清单", "Task List")}</h2>
              <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                completedCount === tasks.length && tasks.length > 0
                  ? "bg-secondary-container/40 text-secondary"
                  : "bg-primary-container/40 text-primary"
              }`}>
                {completedCount}/{tasks.length} {t("已完成", "Done")}
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
                  <p className="text-sm text-on-surface-variant">{t("加载任务中...", "Loading tasks...")}</p>
                </div>
              </div>
            ) : tasks.length === 0 ? (
              <div className="flex items-center justify-center py-12">
                <p className="text-on-surface-variant">{t("暂无任务", "No tasks")}</p>
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
                            {t("高优先级", "High Priority")}
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
                          {task.type === "medication" ? t("用药", "Medication") :
                           task.type === "followup" ? t("随访", "Follow-up") :
                           task.type === "record" ? t("档案", "Record") : t("护理", "Care")}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 执行进度 */}
          <div className="rounded-3xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm sm:p-6">
            <h2 className="font-headline font-bold text-on-surface mb-4">{t("执行进度", "Execution Progress")}</h2>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-on-surface-variant">{t("完成度", "Progress")}</span>
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
              {executing ? t("正在执行任务...", "Executing tasks...") : executed ? t("所有任务已执行完成", "All tasks completed") : t(`已完成 ${completedCount}/${tasks.length} 项任务`, `Completed ${completedCount}/${tasks.length} tasks`)}
            </p>
          </div>
        </div>

        {/* 右侧：操作区 */}
        <div className="space-y-4 lg:col-span-4">
          <div className="rounded-3xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm sm:p-6">
            <h2 className="font-headline font-bold text-on-surface mb-4">{t("快速操作", "Quick Actions")}</h2>
            <div className="space-y-3">
              <button
                onClick={() => router.push(`/event-confirm/${eventId}`)}
                className="w-full py-3 px-4 bg-surface-container text-on-surface rounded-xl font-semibold hover:bg-surface-container-high transition-all"
              >
                {t("返回事件卡", "Back to Event Card")}
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
                {executing ? t("执行中...", "Executing...") : executed ? t("已执行完成", "Completed") : t("执行所有任务", "Execute All Tasks")}
              </button>
              <button
                onClick={() => currentEvent?.archived ? handleUnarchive(eventId) : handleArchive(eventId)}
                disabled={archivingId === eventId}
                className="w-full py-3 px-4 rounded-xl bg-tertiary-container text-tertiary font-semibold hover:opacity-90 transition-all disabled:opacity-50"
              >
                {archivingId === eventId ? t("处理中...", "Processing...") : currentEvent?.archived ? t("取消归档", "Unarchive") : t("归档到健康档案", "Archive to Health Records")}
              </button>
              <button
                onClick={() => handleDelete(eventId)}
                disabled={deletingId === eventId}
                className="w-full py-3 px-4 rounded-xl bg-error-container text-error font-semibold hover:opacity-90 transition-all disabled:opacity-50"
              >
                {deletingId === eventId ? t("删除中...", "Deleting...") : t("删除通用执行", "Delete Execution")}
              </button>
            </div>
          </div>

          <div className="bg-primary-fixed/30 rounded-2xl p-6 border border-primary/20">
            <p className="text-xs font-bold text-primary uppercase tracking-widest">{t("系统状态", "SYSTEM STATUS")}</p>
            <p className="text-sm text-on-surface mt-2">{t("所有任务已就绪，等待用户触发执行", "All tasks ready, awaiting user execution")}</p>
          </div>

          <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
            <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">{t("继续诊断", "CONTINUE DIAGNOSIS")}</p>
            <p className="text-sm text-on-surface mt-2">{t("需要回到原始问诊会话补充信息时，可直接返回继续 AI 诊断。", "Return to the original consultation session to continue AI diagnosis.")}</p>
            <button
              onClick={() => currentEvent?.source_session_id && router.push(`/chat/${currentEvent.source_session_id}`)}
              disabled={!currentEvent?.source_session_id}
              className="mt-4 w-full py-3 px-4 rounded-xl bg-primary text-on-primary font-semibold hover:opacity-90 transition-all disabled:opacity-50"
            >
              {t("返回继续 AI 诊断", "Continue AI Diagnosis")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ExecutionPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading...</div>}>
      <ExecutionContent />
    </Suspense>
  );
}
