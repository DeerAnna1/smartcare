"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api-client";

interface Skill {
  id: string;
  skill_id: string;
  name: string;
  description: string;
  category: string;
  status: string;
  confirm_required: boolean;
  version: string;
  keywords: string[];
  trigger_examples: string[];
  created_at: string;
}

interface InvocationLog {
  id: string;
  trace_id: string;
  tool_name: string;
  latency_ms: number;
  result_status: string;
  error_reason: string | null;
  created_at: string;
}

interface InvokeResult {
  skill_id: string;
  status: string;
  result?: Record<string, unknown>;
  error?: string;
  trace_id?: string;
}

const statusConfig: Record<string, { label: string; color: string; dot: string }> = {
  ACTIVE: { label: "运行中", color: "text-secondary bg-secondary-container/40", dot: "bg-secondary" },
  DISABLED: { label: "已禁用", color: "text-error bg-error-container/30", dot: "bg-error" },
  ERROR: { label: "异常", color: "text-error bg-error-container/30", dot: "bg-error" },
};

const defaultFormState = {
  skill_id: "",
  name: "",
  description: "",
  category: "健康管理",
  keywords: "",
  trigger_examples: "",
  mcp_server: "",
  confirm_required: false,
  version: "1.0.0",
};

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showInvokeModal, setShowInvokeModal] = useState<Skill | null>(null);
  const [showLogsModal, setShowLogsModal] = useState<Skill | null>(null);

  const [form, setForm] = useState(defaultFormState);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [invokeInput, setInvokeInput] = useState("{}");
  const [invokeResult, setInvokeResult] = useState<InvokeResult | null>(null);
  const [invoking, setInvoking] = useState(false);

  const [logs, setLogs] = useState<InvocationLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.listSkills();
      setSkills(data as Skill[]);
    } catch {
      setError("加载技能列表失败，请检查网络连接");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadSkills(); }, [loadSkills]);

  const handleCreate = async () => {
    if (!form.skill_id.trim() || !form.name.trim()) {
      setCreateError("skill_id 和名称为必填项");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      await api.createSkill({
        skill_id: form.skill_id.trim(),
        name: form.name.trim(),
        description: form.description.trim(),
        category: form.category.trim(),
        keywords: form.keywords.split(",").map((k) => k.trim()).filter(Boolean),
        trigger_examples: form.trigger_examples.split("\n").map((e) => e.trim()).filter(Boolean),
        mcp_server: form.mcp_server.trim() || undefined,
        confirm_required: form.confirm_required,
        version: form.version.trim() || "1.0.0",
        tools: [],
        degrade_policy: {},
      });
      setShowCreateModal(false);
      setForm(defaultFormState);
      void loadSkills();
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "注册失败");
    } finally {
      setCreating(false);
    }
  };

  const handleToggleStatus = async (skill: Skill) => {
    const next = skill.status === "ACTIVE" ? "DISABLED" : "ACTIVE";
    try {
      await api.updateSkillStatus(skill.skill_id, next);
      setSkills((prev) => prev.map((s) => s.skill_id === skill.skill_id ? { ...s, status: next } : s));
    } catch { alert("更新状态失败"); }
  };

  const handleDelete = async (skill: Skill) => {
    if (!confirm(`确认删除技能「${skill.name}」？此操作不可撤销。`)) return;
    try {
      await api.deleteSkill(skill.skill_id);
      setSkills((prev) => prev.filter((s) => s.skill_id !== skill.skill_id));
    } catch { alert("删除失败"); }
  };

  const handleInvoke = async () => {
    if (!showInvokeModal) return;
    let parsed: Record<string, unknown>;
    try { parsed = JSON.parse(invokeInput) as Record<string, unknown>; }
    catch { alert("输入参数必须是合法 JSON"); return; }
    setInvoking(true);
    setInvokeResult(null);
    try {
      const result = await api.invokeSkill(showInvokeModal.skill_id, parsed);
      setInvokeResult(result as InvokeResult);
    } catch (e) {
      setInvokeResult({ skill_id: showInvokeModal.skill_id, status: "failed", error: e instanceof Error ? e.message : "调用失败" });
    } finally { setInvoking(false); }
  };

  const handleShowLogs = async (skill: Skill) => {
    setShowLogsModal(skill);
    setLogsLoading(true);
    setLogs([]);
    try {
      const data = await api.getSkillLogs(skill.skill_id);
      setLogs(data as InvocationLog[]);
    } catch { setLogs([]); }
    finally { setLogsLoading(false); }
  };

  const activeCount = skills.filter((s) => s.status === "ACTIVE").length;
  const PAGE_SIZE = 10;
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`确认删除选中的 ${selectedIds.size} 个技能？此操作不可撤销。`)) return;
    setBatchDeleting(true);
    try {
      await Promise.all([...selectedIds].map((id) => api.deleteSkill(id)));
      setSkills((prev) => prev.filter((s) => !selectedIds.has(s.skill_id)));
      setSelectedIds(new Set());
    } catch {
      alert("部分删除失败，请重试");
    } finally {
      setBatchDeleting(false);
    }
  };

  const pageSkills = skills.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const allPageSkillsSelected = pageSkills.length > 0 && pageSkills.every((s) => selectedIds.has(s.skill_id));

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {/* 页头 */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-headline font-bold text-3xl text-on-surface">技能管理</h1>
          <p className="text-on-surface-variant text-sm mt-1">
            管理 Agent 技能包，支持手动注册与 MCP 接入。
            {!loading && (
              <span className="ml-2 text-secondary font-medium">已激活 {activeCount} / {skills.length} 项</span>
            )}
          </p>
        </div>
        <button
          onClick={() => { setShowCreateModal(true); setForm(defaultFormState); setCreateError(""); }}
          className="px-5 py-2.5 bg-primary text-on-primary rounded-xl font-semibold flex items-center gap-2 hover:opacity-90 transition-all"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          接入新技能
        </button>
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-24 text-on-surface-variant">
          <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin mr-3" />
          加载中...
        </div>
      ) : error ? (
        <div className="text-center py-24">
          <span className="material-symbols-outlined text-error text-[48px] block mb-3">error</span>
          <p className="text-error font-medium">{error}</p>
          <button onClick={() => void loadSkills()} className="mt-4 px-5 py-2 bg-primary text-on-primary rounded-xl text-sm font-semibold">重试</button>
        </div>
      ) : skills.length === 0 ? (
        <div className="text-center py-24 bg-surface-container-lowest rounded-2xl border border-outline-variant/10">
          <span className="material-symbols-outlined text-on-surface-variant text-[48px] block mb-3">extension</span>
          <p className="font-semibold text-on-surface">暂无技能</p>
          <p className="text-sm text-on-surface-variant mt-1 mb-4">点击「接入新技能」注册第一个 Agent 技能包</p>
          <button onClick={() => setShowCreateModal(true)} className="px-5 py-2.5 bg-primary text-on-primary rounded-xl font-semibold text-sm">接入新技能</button>
        </div>
      ) : (
        <>
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-3 mb-4 px-4 py-2.5 bg-error-container/20 border border-error/20 rounded-xl">
              <span className="text-sm font-semibold text-error flex-1">已选 {selectedIds.size} 个</span>
              <button onClick={() => setSelectedIds(new Set())} className="text-xs text-on-surface-variant hover:text-on-surface transition-colors">取消选择</button>
              <button
                onClick={() => void handleBatchDelete()}
                disabled={batchDeleting}
                className="px-3 py-1.5 bg-error text-on-error rounded-xl text-xs font-semibold hover:opacity-90 disabled:opacity-50 transition-all flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-[14px]">delete_sweep</span>
                {batchDeleting ? "删除中..." : `删除 ${selectedIds.size} 个`}
              </button>
            </div>
          )}
          <div className="flex items-center gap-2 mb-2">
            <label className="flex items-center gap-1.5 cursor-pointer select-none text-xs text-on-surface-variant hover:text-on-surface transition-colors">
              <input
                type="checkbox"
                checked={allPageSkillsSelected}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedIds((prev) => { const n = new Set(prev); pageSkills.forEach((s) => n.add(s.skill_id)); return n; });
                  } else {
                    setSelectedIds((prev) => { const n = new Set(prev); pageSkills.forEach((s) => n.delete(s.skill_id)); return n; });
                  }
                }}
                className="rounded"
              />
              全选当前页
            </label>
          </div>
          <div className="space-y-3">
            {pageSkills.map((skill) => {
            const sc = statusConfig[skill.status] ?? { label: skill.status, color: "text-on-surface-variant", dot: "bg-on-surface-variant" };
            return (
              <div key={skill.skill_id} className={`rounded-2xl border shadow-sm p-5 flex items-center gap-4 ${selectedIds.has(skill.skill_id) ? "bg-primary-fixed/20 border-primary/30" : "bg-surface-container-lowest border-outline-variant/10"}`}>
                <input
                  type="checkbox"
                  checked={selectedIds.has(skill.skill_id)}
                  onChange={(e) => setSelectedIds((prev) => { const n = new Set(prev); e.target.checked ? n.add(skill.skill_id) : n.delete(skill.skill_id); return n; })}
                  className="rounded shrink-0"
                />
                <div className="w-12 h-12 rounded-2xl bg-primary-fixed/40 flex items-center justify-center shrink-0">
                  <span className="material-symbols-outlined text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>extension</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-headline font-bold text-on-surface">{skill.name}</span>
                    <span className="text-xs text-on-surface-variant font-mono bg-surface-container px-2 py-0.5 rounded-full">{skill.skill_id}</span>
                    <span className="text-xs text-on-surface-variant">v{skill.version}</span>
                    {skill.confirm_required && <span className="text-xs bg-tertiary-container/50 text-tertiary px-2 py-0.5 rounded-full">需确认</span>}
                  </div>
                  <p className="text-sm text-on-surface-variant mt-0.5 truncate">{skill.description}</p>
                  {skill.keywords.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {skill.keywords.slice(0, 6).map((kw) => (
                        <span key={kw} className="text-xs bg-surface-container text-on-surface-variant px-2 py-0.5 rounded-full">{kw}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ${sc.color}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
                    {sc.label}
                  </span>
                  <button onClick={() => void handleShowLogs(skill)} title="调用日志" className="p-2 text-on-surface-variant hover:bg-surface-container rounded-xl transition-all">
                    <span className="material-symbols-outlined text-[18px]">receipt_long</span>
                  </button>
                  <button onClick={() => { setShowInvokeModal(skill); setInvokeInput("{}"); setInvokeResult(null); }} title="调用" className="p-2 text-on-surface-variant hover:bg-surface-container rounded-xl transition-all">
                    <span className="material-symbols-outlined text-[18px]">play_circle</span>
                  </button>
                  <button onClick={() => void handleToggleStatus(skill)} title={skill.status === "ACTIVE" ? "禁用" : "启用"} className="p-2 text-on-surface-variant hover:bg-surface-container rounded-xl transition-all">
                    <span className="material-symbols-outlined text-[18px]">{skill.status === "ACTIVE" ? "toggle_on" : "toggle_off"}</span>
                  </button>
                  <button onClick={() => void handleDelete(skill)} title="删除" className="p-2 text-error hover:bg-error-container/20 rounded-xl transition-all">
                    <span className="material-symbols-outlined text-[18px]">delete</span>
                  </button>
                </div>
              </div>
            );
          })}
          </div>
          {Math.ceil(skills.length / PAGE_SIZE) > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6 pt-4 border-t border-outline-variant/10">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-xl text-sm font-medium text-on-surface-variant hover:bg-surface-container transition-all disabled:opacity-40"
              >
                上一页
              </button>
              {Array.from({ length: Math.ceil(skills.length / PAGE_SIZE) }, (_, i) => i + 1).map((p) => (
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
                onClick={() => setPage((p) => Math.min(Math.ceil(skills.length / PAGE_SIZE), p + 1))}
                disabled={page === Math.ceil(skills.length / PAGE_SIZE)}
                className="px-3 py-1.5 rounded-xl text-sm font-medium text-on-surface-variant hover:bg-surface-container transition-all disabled:opacity-40"
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}

      {/* ── 创建技能弹窗 ── */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-headline font-bold text-xl text-on-surface">接入新技能</h2>
              <button onClick={() => setShowCreateModal(false)} className="p-1 hover:bg-surface-container rounded-lg">
                <span className="material-symbols-outlined text-on-surface-variant">close</span>
              </button>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-on-surface-variant block mb-1">技能标识 *</label>
                  <input value={form.skill_id} onChange={(e) => setForm((f) => ({ ...f, skill_id: e.target.value }))} placeholder="如 med-reminder" className="w-full border border-outline-variant/30 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-on-surface-variant block mb-1">版本</label>
                  <input value={form.version} onChange={(e) => setForm((f) => ({ ...f, version: e.target.value }))} placeholder="1.0.0" className="w-full border border-outline-variant/30 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">名称 *</label>
                <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="技能显示名称" className="w-full border border-outline-variant/30 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
              </div>
              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">描述</label>
                <textarea value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} rows={2} placeholder="技能功能说明..." className="w-full border border-outline-variant/30 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-on-surface-variant block mb-1">分类</label>
                  <input value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} placeholder="健康管理" className="w-full border border-outline-variant/30 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-on-surface-variant block mb-1">MCP 服务地址</label>
                  <input value={form.mcp_server} onChange={(e) => setForm((f) => ({ ...f, mcp_server: e.target.value }))} placeholder="http://localhost:3100" className="w-full border border-outline-variant/30 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">关键词（逗号分隔）</label>
                <input value={form.keywords} onChange={(e) => setForm((f) => ({ ...f, keywords: e.target.value }))} placeholder="用药提醒, 复诊, 健康档案" className="w-full border border-outline-variant/30 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
              </div>
              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">触发示例（每行一条）</label>
                <textarea value={form.trigger_examples} onChange={(e) => setForm((f) => ({ ...f, trigger_examples: e.target.value }))} rows={3} placeholder={"帮我设置用药提醒\n明天要复诊，帮我记一下"} className="w-full border border-outline-variant/30 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none" />
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.confirm_required} onChange={(e) => setForm((f) => ({ ...f, confirm_required: e.target.checked }))} className="rounded" />
                <span className="text-sm text-on-surface">调用前需要用户二次确认</span>
              </label>
              {createError && <p className="text-sm text-error bg-error-container/20 rounded-xl px-3 py-2">{createError}</p>}
              <div className="flex gap-3 pt-2">
                <button onClick={() => setShowCreateModal(false)} className="flex-1 py-2.5 border border-outline-variant/30 text-on-surface rounded-xl text-sm font-medium hover:bg-surface-container transition-all">取消</button>
                <button onClick={() => void handleCreate()} disabled={creating} className="flex-1 py-2.5 bg-primary text-on-primary rounded-xl text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-all">
                  {creating ? "注册中..." : "注册技能"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 调用技能弹窗 ── */}
      {showInvokeModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-headline font-bold text-lg text-on-surface">调用技能</h2>
                <p className="text-sm text-on-surface-variant">{showInvokeModal.name}</p>
              </div>
              <button onClick={() => setShowInvokeModal(null)} className="p-1 hover:bg-surface-container rounded-lg">
                <span className="material-symbols-outlined text-on-surface-variant">close</span>
              </button>
            </div>
            {showInvokeModal.trigger_examples.length > 0 && (
              <div className="mb-3">
                <p className="text-xs font-semibold text-on-surface-variant mb-1">触发示例</p>
                <ul className="space-y-1">
                  {showInvokeModal.trigger_examples.slice(0, 3).map((ex, i) => (
                    <li key={i} className="text-xs text-on-surface-variant bg-surface-container rounded-lg px-2 py-1">{ex}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="mb-4">
              <label className="text-xs font-semibold text-on-surface-variant block mb-1">输入参数（JSON）</label>
              <textarea value={invokeInput} onChange={(e) => setInvokeInput(e.target.value)} rows={5} className="w-full font-mono text-xs border border-outline-variant/30 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none" />
            </div>
            {showInvokeModal.confirm_required && (
              <p className="text-xs text-tertiary bg-tertiary-container/20 rounded-xl px-3 py-2 mb-3 flex items-center gap-2">
                <span className="material-symbols-outlined text-[14px]">warning</span>
                此技能需确认，请在 JSON 中加入 &quot;confirmed&quot;: true
              </p>
            )}
            {invokeResult && (
              <div className={`rounded-xl p-3 mb-4 text-xs font-mono ${invokeResult.status === "success" || invokeResult.status === "degraded" ? "bg-secondary-container/20 text-on-surface" : "bg-error-container/20 text-error"}`}>
                <p className="font-bold mb-1">状态：{invokeResult.status}
                  {invokeResult.trace_id && <span className="font-normal text-on-surface-variant ml-2">trace: {invokeResult.trace_id}</span>}
                </p>
                <pre className="whitespace-pre-wrap break-all">{invokeResult.error ?? JSON.stringify(invokeResult.result, null, 2)}</pre>
              </div>
            )}
            <div className="flex gap-3">
              <button onClick={() => setShowInvokeModal(null)} className="flex-1 py-2.5 border border-outline-variant/30 text-on-surface rounded-xl text-sm font-medium">关闭</button>
              <button onClick={() => void handleInvoke()} disabled={invoking} className="flex-1 py-2.5 bg-primary text-on-primary rounded-xl text-sm font-semibold hover:opacity-90 disabled:opacity-50">
                {invoking ? "调用中..." : "发起调用"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── 调用日志弹窗 ── */}
      {showLogsModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl p-6 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between mb-4 shrink-0">
              <div>
                <h2 className="font-headline font-bold text-lg text-on-surface">调用日志</h2>
                <p className="text-sm text-on-surface-variant">{showLogsModal.name}</p>
              </div>
              <button onClick={() => setShowLogsModal(null)} className="p-1 hover:bg-surface-container rounded-lg">
                <span className="material-symbols-outlined text-on-surface-variant">close</span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto space-y-2">
              {logsLoading ? (
                <div className="flex items-center justify-center py-10 text-on-surface-variant text-sm">
                  <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin mr-2" />加载中...
                </div>
              ) : logs.length === 0 ? (
                <div className="text-center py-10 text-on-surface-variant text-sm">暂无调用记录</div>
              ) : (
                logs.map((log) => (
                  <div key={log.id} className="bg-surface-container rounded-xl px-4 py-3 text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className={`font-bold ${log.result_status === "success" ? "text-secondary" : log.result_status === "degraded" ? "text-tertiary" : "text-error"}`}>{log.result_status.toUpperCase()}</span>
                      <span className="text-on-surface-variant">{log.latency_ms}ms · {new Date(log.created_at).toLocaleString("zh-CN")}</span>
                    </div>
                    <p className="text-on-surface-variant font-mono truncate">trace: {log.trace_id}</p>
                    {log.error_reason && <p className="text-error mt-1">{log.error_reason}</p>}
                  </div>
                ))
              )}
            </div>
            <button onClick={() => setShowLogsModal(null)} className="mt-4 w-full py-2.5 border border-outline-variant/30 text-on-surface rounded-xl text-sm font-medium shrink-0">关闭</button>
          </div>
        </div>
      )}
    </div>
  );
}
