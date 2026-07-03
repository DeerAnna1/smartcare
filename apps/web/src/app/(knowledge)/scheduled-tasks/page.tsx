"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

interface ScheduledTask {
  id: string;
  title: string;
  topic: string;
  schedule_cron: string;
  schedule_natural: string;
  content_template: string;
  status: string;
  last_run_at: string | null;
  next_run_at: string | null;
  unread_count: number;
  created_at: string;
}

interface TaskLog {
  id: string;
  task_id: string;
  content: string;
  status: string;
  error_message: string;
  executed_at: string;
}

export default function ScheduledTasksPage() {
  const { t } = useLang();
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [scheduleInput, setScheduleInput] = useState("");
  const [parsedSchedule, setParsedSchedule] = useState("");
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [selectedTask, setSelectedTask] = useState<ScheduledTask | null>(null);
  const [taskLogs, setTaskLogs] = useState<TaskLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [executing, setExecuting] = useState<string | null>(null);

  const loadTasks = async () => {
    setLoading(true);
    try {
      const data = await api.listScheduledTasks();
      setTasks(data);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    api.listScheduledTasks()
      .then((data) => {
        if (!cancelled) setTasks(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleParse = async () => {
    if (!scheduleInput.trim()) return;
    setParsing(true);
    try {
      const data = await api.parseSchedule(scheduleInput.trim());
      setParsedSchedule(data.cron || "");
    } catch {
    } finally {
      setParsing(false);
    }
  };

  const handleAdd = async () => {
    if (!title.trim() || !scheduleInput.trim()) return;
    setSaving(true);
    try {
      await api.createScheduledTask({
        title: title.trim(),
        topic: topic.trim() || title.trim(),
        schedule_natural: scheduleInput.trim(),
        schedule_cron: parsedSchedule,
      });
      setTitle("");
      setTopic("");
      setScheduleInput("");
      setParsedSchedule("");
      setShowAdd(false);
      loadTasks();
    } catch {
      alert(t("创建失败", "Creation failed"));
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (id: string) => {
    try {
      await api.toggleScheduledTask(id);
      loadTasks();
    } catch {
      alert(t("操作失败", "Operation failed"));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(t("确认删除该任务？", "Delete this task?"))) return;
    try {
      await api.deleteScheduledTask(id);
      loadTasks();
    } catch {
      alert(t("删除失败", "Delete failed"));
    }
  };

  const handleShowLogs = async (task: ScheduledTask) => {
    setSelectedTask(task);
    setLogsLoading(true);
    try {
      const logs = await api.getScheduledTaskLogs(task.id);
      setTaskLogs(logs);
      // 标记为已读
      await api.markScheduledTaskRead(task.id);
      // 更新本地未读状态
      setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, unread_count: 0 } : t));
    } catch {
      setTaskLogs([]);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleExecute = async (task: ScheduledTask) => {
    setExecuting(task.id);
    try {
      const result = await api.executeScheduledTask(task.id);
      if (result.status === "success") {
        await loadTasks();
      } else {
        alert(`${t("执行失败", "Execution failed")}: ${result.error}`);
      }
    } catch {
      alert(t("执行失败", "Execution failed"));
    } finally {
      setExecuting(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-5 sm:px-6">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setShowAdd(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-on-primary shadow-sm hover:opacity-90"
        >
          <span className="material-symbols-outlined text-[18px]">add_alarm</span>
          {t("新建任务", "New Task")}
        </button>
      </div>

      {/* 新建弹窗 */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-container rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-bold text-on-surface mb-4">{t("新建科普任务", "New Task")}</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-on-surface mb-1">{t("任务标题", "Task Title")}</label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={t("每日血糖管理科普", "Daily blood sugar management tips")}
                  className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-on-surface mb-1">{t("科普话题", "Topic")}</label>
                <input
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder={t("糖尿病饮食注意事项", "Diabetes diet tips")}
                  className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-on-surface mb-1">{t("定时规则（自然语言）", "Schedule (natural language)")}</label>
                <div className="flex gap-2">
                  <input
                    value={scheduleInput}
                    onChange={(e) => { setScheduleInput(e.target.value); setParsedSchedule(""); }}
                    placeholder={t("每天早上9点", "Every day at 9am")}
                    className="flex-1 px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 text-sm"
                  />
                  <button onClick={handleParse} disabled={parsing} className="px-3 py-2.5 rounded-xl bg-surface-container text-on-surface-variant text-sm hover:bg-surface-container-high">
                    {parsing ? t("解析中", "Parsing...") : t("解析", "Parse")}
                  </button>
                </div>
                {parsedSchedule && (
                  <p className="text-xs text-primary mt-1">Cron: {parsedSchedule}</p>
                )}
              </div>
            </div>
            <div className="flex gap-3 justify-end mt-5">
              <button onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-xl text-sm text-on-surface-variant hover:bg-surface-container-high">{t("取消", "Cancel")}</button>
              <button onClick={handleAdd} disabled={saving} className="px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-medium hover:opacity-90 disabled:opacity-50">
                {saving ? t("创建中...", "Creating...") : t("创建", "Create")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 任务列表 */}
      {loading ? (
        <p className="text-on-surface-variant text-sm py-12 text-center">{t("加载中...", "Loading...")}</p>
      ) : tasks.length === 0 ? (
        <p className="text-on-surface-variant text-sm py-12 text-center">{t("暂无任务", "No tasks yet")}</p>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <div
              key={task.id}
              className="relative cursor-pointer rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-4 transition-all hover:-translate-y-0.5 hover:border-primary/20 hover:shadow-sm"
              onClick={() => handleShowLogs(task)}
            >
              {/* 未读红点 */}
              {task.unread_count > 0 && (
                <span className="absolute top-3 right-3 min-w-[18px] h-[18px] px-1 bg-error text-on-error rounded-full text-[10px] font-bold flex items-center justify-center">
                  {task.unread_count}
                </span>
              )}
              <div className="flex items-start justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-sm font-semibold text-on-surface">{task.title}</h3>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${task.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                      {task.status === "active" ? t("运行中", "Running") : t("已暂停", "Paused")}
                    </span>
                  </div>
                  <p className="text-xs text-on-surface-variant mb-1">{t("话题", "Topic")}: {task.topic}</p>
                  <p className="text-xs text-on-surface-variant">
                    {task.schedule_natural || task.schedule_cron}
                    {task.last_run_at && ` · ${t("上次执行", "Last run")}: ${new Date(task.last_run_at).toLocaleString("zh-CN")}`}
                  </p>
                  {task.status === "active" && task.next_run_at && (
                    <p className="mt-1 text-xs font-medium text-primary">
                      {t("下次执行", "Next run")}: {new Date(task.next_run_at).toLocaleString("zh-CN")}
                    </p>
                  )}
                </div>
                <div className="flex gap-1 ml-3" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => handleExecute(task)}
                    disabled={executing === task.id}
                    className="inline-flex items-center gap-1 whitespace-nowrap rounded-lg bg-primary/10 px-2.5 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/15 disabled:opacity-50"
                    title={t("立即生成一次科普内容并写入执行记录", "Generate content now and save it to the execution log")}
                  >
                    <span className="material-symbols-outlined text-[15px]">
                      {executing === task.id ? "hourglass_empty" : "bolt"}
                    </span>
                    {executing === task.id ? t("测试中", "Testing") : t("快速测试", "Quick Test")}
                  </button>
                  <button
                    onClick={() => handleToggle(task.id)}
                    className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors"
                    title={task.status === "active" ? t("暂停", "Pause") : t("启用", "Enable")}
                  >
                    <span className="material-symbols-outlined text-[18px]">{task.status === "active" ? "pause" : "play_arrow"}</span>
                  </button>
                  <button onClick={() => handleDelete(task.id)} className="p-1.5 rounded-full hover:bg-error/10 text-on-surface-variant hover:text-error transition-colors" title={t("删除", "Delete")}>
                    <span className="material-symbols-outlined text-[18px]">delete</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 任务详情/日志弹窗 */}
      {selectedTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-container rounded-2xl shadow-2xl w-full max-w-2xl mx-4 p-6 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-on-surface">{selectedTask.title}</h2>
                <p className="text-xs text-on-surface-variant">{t("话题", "Topic")}: {selectedTask.topic} · {selectedTask.schedule_natural || selectedTask.schedule_cron}</p>
              </div>
              <button
                onClick={() => { setSelectedTask(null); setTaskLogs([]); }}
                className="p-1.5 rounded-full hover:bg-surface-container-high"
              >
                <span className="material-symbols-outlined text-lg text-on-surface-variant">close</span>
              </button>
            </div>

            <div className="flex items-center gap-2 mb-4">
              <button
                onClick={() => handleExecute(selectedTask)}
                disabled={executing === selectedTask.id}
                className="px-3 py-1.5 rounded-lg bg-primary text-on-primary text-xs font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-[14px]">
                  {executing === selectedTask.id ? "hourglass_empty" : "bolt"}
                </span>
                {executing === selectedTask.id ? t("测试中...", "Testing...") : t("快速测试一次", "Run quick test")}
              </button>
              <span className="text-xs text-on-surface-variant">
                {t("点击按钮使用 AI 生成科普内容", "Click to generate content with AI")}
              </span>
            </div>

            <div className="flex-1 overflow-y-auto">
              <h3 className="text-sm font-semibold text-on-surface mb-3">{t("执行记录", "Execution History")}</h3>
              {logsLoading ? (
                <p className="text-on-surface-variant text-sm py-4 text-center">{t("加载中...", "Loading...")}</p>
              ) : taskLogs.length === 0 ? (
                <p className="text-on-surface-variant text-sm py-4 text-center">{t("暂无执行记录，点击上方按钮立即执行一次", "No execution history. Click the button above to run now.")}</p>
              ) : (
                <div className="space-y-3">
                  {taskLogs.map((log) => (
                    <div key={log.id} className="p-3 rounded-lg bg-surface-container-lowest border border-outline-variant/15">
                      <div className="flex items-center justify-between mb-2">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${log.status === "success" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                          {log.status === "success" ? t("成功", "Success") : t("失败", "Failed")}
                        </span>
                        <span className="text-[10px] text-on-surface-variant">
                          {new Date(log.executed_at).toLocaleString("zh-CN")}
                        </span>
                      </div>
                      {log.content && (
                        <div className="prose prose-sm max-w-none text-on-surface prose-headings:text-on-surface prose-p:text-on-surface prose-strong:text-on-surface prose-li:text-on-surface">
                          <ReactMarkdown>{log.content}</ReactMarkdown>
                        </div>
                      )}
                      {log.error_message && (
                        <p className="text-xs text-error mt-1">{log.error_message}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
