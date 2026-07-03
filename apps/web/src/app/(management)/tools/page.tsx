"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

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
  mcp_server?: string;
  source_type: string;
  tools: Array<{ name: string; description?: string; parameters?: Record<string, unknown> }>;
  created_at: string;
}

interface BuiltinTool {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

type RuntimeType = "builtin" | "mcp" | "manual";
type ToolTab = "skill" | "mcp";

interface MCPService {
  id: string;
  server_key: string;
  name: string;
  description: string;
  url: string;
  transport: string;
  health_status: string;
  last_error?: string;
}

interface MCPTool { id: string; name: string; description?: string; read_only: boolean; requires_confirmation: boolean; }

interface InvocationLog {
  id: string;
  trace_id: string;
  tool_name: string;
  latency_ms: number;
  result_status: string;
  error_reason: string | null;
  created_at: string;
}

const BUILTIN_TEST_INPUTS: Record<string, Record<string, unknown>> = {
  "drug-safety": { drugs: ["阿莫西林", "布洛芬"] },
  "appointment-booking": { department_name: "心内科" },
  "check_drug_interaction": { drugs: ["阿莫西林", "布洛芬"] },
  "query_doctor_schedule": { department_name: "心内科" },
  "lock_appointment_slot": { schedule_id: "", patient_name: "", patient_id_last4: "" },
};

const TOOL_TEST_INPUTS: Record<string, Record<string, unknown>> = {
  pubmed_search_articles: { query: "hypertension lifestyle intervention", maxResults: 3, summaryCount: 3 },
  openfda_search_adverse_events: { category: "drug", search: 'patient.drug.medicinalproduct:"aspirin"', limit: 3 },
  simulate_ed_demo: { arrivalRate: 8, mds: 3, simulationDays: 1 },
  search_providers: { category: "Medical Billing & RCM", state: "TX", per_page: 3 },
  explain_ed_queueing: {},
};

const SKILL_TEST_TOOL_SUFFIX: Record<string, string> = {
  "drug-safety": "check_drug_interaction",
  "medical-literature-review": "pubmed_search_articles",
  "healthcare-queue-simulator": "simulate_ed_demo",
  "healthcare-provider-directory": "search_providers",
  "appointment-booking": "query_doctor_schedule",
};

function originalToolName(name: string): string {
  return name.split("__").pop() ?? name;
}

function testParamsForTool(name: string, skillId = ""): Record<string, unknown> {
  const original = originalToolName(name);
  return TOOL_TEST_INPUTS[original] ?? BUILTIN_TEST_INPUTS[name] ?? BUILTIN_TEST_INPUTS[original] ?? BUILTIN_TEST_INPUTS[skillId] ?? {};
}

function preferredSkillTool(skill: Skill) {
  const suffix = SKILL_TEST_TOOL_SUFFIX[skill.skill_id];
  return (skill.tools ?? []).find((tool) => originalToolName(tool.name) === suffix) ?? (skill.tools ?? [])[0];
}

function preferredMCPTool(tools: MCPTool[]) {
  const preferredOrder = ["pubmed_search_articles", "openfda_search_adverse_events", "simulate_ed_demo", "search_providers", "explain_ed_queueing"];
  return preferredOrder.map((suffix) => tools.find((tool) => originalToolName(tool.name) === suffix)).find(Boolean) ?? tools[0];
}

function skillDisplayName(skill: Skill): string {
  if (skill.skill_id === "drug-safety" || skill.skill_id === "drug-interaction") return "用药安全检查";
  if (skill.skill_id === "medical-literature-review") return "医学文献检索与综述";
  return skill.name;
}

function mcpDisplayName(service: MCPService): string {
  const text = `${service.server_key} ${service.name} ${service.url}`.toLowerCase();
  if (text.includes("openfda")) return "药品安全数据服务（OpenFDA）";
  if (text.includes("pubmed")) return "医学文献检索服务（PubMed）";
  if (text.includes("healthcare-queue") || text.includes("queue-simulator")) return "医疗排队与人员配置模拟服务";
  if (text.includes("healthcare-provider") || text.includes("provider-directory")) return "医疗服务机构目录服务";
  return service.name;
}

function toolDisplayName(name: string): string {
  const value = name.toLowerCase().split("__").pop() ?? name.toLowerCase();
  if (value.includes("check_drug_interaction")) return "药物相互作用检查";
  if (value.includes("query_doctor_schedule")) return "医生排班查询";
  if (value.includes("lock_appointment_slot")) return "预约号源锁定";
  if (value === "pubmed_search_articles") return "PubMed 文献搜索";
  if (value === "pubmed_fetch_articles") return "文献摘要与元数据获取";
  if (value === "pubmed_fetch_fulltext") return "开放全文获取";
  if (value === "pubmed_format_citations") return "参考文献格式化";
  if (value === "pubmed_find_related") return "相关文献与引用查询";
  if (value === "pubmed_spell_check") return "检索词拼写检查";
  if (value === "pubmed_lookup_mesh") return "医学主题词查询";
  if (value === "pubmed_lookup_citation") return "引文匹配与 PMID 查询";
  if (value === "pubmed_convert_ids") return "文献标识符转换";
  if (value === "pubmed_europepmc_search") return "Europe PMC 文献搜索";
  if (value === "explain_ed_queueing") return "急诊排队机制说明";
  if (value === "explain_walk_in_clinic") return "无预约门诊排队说明";
  if (value === "explain_appointment_office") return "预约门诊调度说明";
  if (value === "list_facility_types") return "医疗机构类型列表";
  if (value === "describe_facility") return "医疗机构类型详情";
  if (value === "simulate_ed_demo") return "急诊排队模拟";
  if (value === "recommend_md_count") return "医生配置数量建议";
  if (value === "match_practice") return "医疗服务机构智能匹配";
  if (value === "search_providers") return "医疗服务机构搜索";
  if (value === "get_provider_detail") return "医疗服务机构详情";
  if (value.includes("openfda") && value.includes("adverse")) return "药品不良事件查询";
  if (value.includes("openfda") && value.includes("animal")) return "兽药不良事件查询";
  if (value.includes("openfda") && value.includes("shortage")) return "药品短缺查询";
  if (value.includes("openfda") && value.includes("recall")) return "药品召回查询";
  if (value.includes("openfda") && value.includes("ndc")) return "药品编码查询";
  if (value.includes("openfda") && value.includes("label")) return "药品标签查询";
  if (value.includes("openfda") && value.includes("describe")) return "数据字段说明";
  if (value.includes("openfda") && value.includes("dataframe")) return "药品数据分析";
  return name;
}

export default function ToolsPage() {
  const { t } = useLang();
  const [tab, setTab] = useState<ToolTab>("skill");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [mcpServices, setMcpServices] = useState<MCPService[]>([]);
  const [mcpTools, setMcpTools] = useState<Record<string, MCPTool[]>>({});
  const [builtinTools, setBuiltinTools] = useState<BuiltinTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createType, setCreateType] = useState<RuntimeType>("builtin");
  const [createError, setCreateError] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ skill_id: "", name: "", description: "", category: t("健康管理", "Health Management"), keywords: "", trigger_examples: "", mcp_server: "", builtin_tool: "", confirm_required: false, version: "1.0.0" });
  const [showLogs, setShowLogs] = useState<Skill | null>(null);
  const [logs, setLogs] = useState<InvocationLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [invokeResult, setInvokeResult] = useState<unknown>(null);
  const [showInvoke, setShowInvoke] = useState<Skill | MCPService | null>(null);
  const [invokeInput, setInvokeInput] = useState("{}");
  const [bindingSkill, setBindingSkill] = useState<Skill | null>(null);
  const [availableTools, setAvailableTools] = useState<MCPTool[]>([]);
  const [selectedToolIds, setSelectedToolIds] = useState<Set<string>>(new Set());
  const [bindingError, setBindingError] = useState("");
  const [checkingServer, setCheckingServer] = useState("");
  const [healthFeedback, setHealthFeedback] = useState<Record<string, string>>({});

  async function loadData() {
    setLoading(true);
    try {
      const [skillsData, mcpData, builtinData] = await Promise.all([
        api.listSkills(),
        api.listMCPServices(),
        api.listBuiltinTools(),
      ]);
      setSkills(Array.isArray(skillsData) ? skillsData : []);
      const servers = Array.isArray(mcpData) ? mcpData as MCPService[] : [];
      setMcpServices(servers);
      setBuiltinTools(Array.isArray(builtinData) ? builtinData : []);
      const toolEntries = await Promise.all(servers.map(async (server) => {
        try {
          const data = await api.listMCPServerTools(server.server_key);
          return [server.server_key, Array.isArray(data) ? data as MCPTool[] : []] as const;
        } catch { return [server.server_key, []] as const; }
      }));
      setMcpTools(Object.fromEntries(toolEntries));
    } catch {
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!showInvoke) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowInvoke(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [showInvoke]);

  const handleToggle = async (skillId: string, currentStatus: string) => {
    try {
      await api.updateSkillStatus(skillId, currentStatus === "ACTIVE" ? "DISABLED" : "ACTIVE");
      loadData();
    } catch {
      alert(t("操作失败", "Operation failed"));
    }
  };

  const handleDelete = async (skillId: string) => {
    if (!confirm(t("确认删除该技能？", "Delete this skill?"))) return;
    try {
      await api.deleteSkill(skillId);
      loadData();
    } catch {
      alert(t("删除失败", "Delete failed"));
    }
  };

  const handleCreate = async () => {
    if (!form.skill_id.trim() || !form.name.trim()) { setCreateError(t("标识和名称不能为空", "ID and name are required")); return; }
    if (createType === "builtin" && !form.builtin_tool) { setCreateError(t("请选择项目内置执行器", "Select a built-in executor")); return; }
    if (createType === "mcp" && !form.mcp_server.trim()) { setCreateError(t("MCP 服务地址不能为空", "MCP server address is required")); return; }
    setCreating(true);
    setCreateError("");
    try {
      if (createType === "mcp") {
        await api.createMCPServer({ server_key: form.skill_id.trim(), name: form.name.trim(), description: form.description.trim(), url: form.mcp_server.trim(), transport: "http", headers: {}, enabled: true });
      } else {
        await api.createSkill({
          ...form, runtime_type: createType, mcp_server: "",
          builtin_tool: createType === "builtin" ? form.builtin_tool : "",
          keywords: form.keywords.split(",").map((s) => s.trim()).filter(Boolean),
          trigger_examples: form.trigger_examples.split(",").map((s) => s.trim()).filter(Boolean),
        });
      }
      setShowCreate(false);
      setForm({ skill_id: "", name: "", description: "", category: t("健康管理", "Health Management"), keywords: "", trigger_examples: "", mcp_server: "", builtin_tool: "", confirm_required: false, version: "1.0.0" });
      loadData();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : t("创建失败", "Creation failed"));
    } finally {
      setCreating(false);
    }
  };

  const handleShowLogs = async (skill: Skill) => {
    setShowLogs(skill);
    setLogsLoading(true);
    try {
      const data = await api.getSkillLogs(skill.skill_id);
      setLogs(data);
    } catch {
      setLogs([]);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleInvoke = async () => {
    if (!showInvoke) return;
    try {
      let parsed = {};
      try { parsed = JSON.parse(invokeInput); } catch { setInvokeResult({ error: t("JSON 格式错误", "Invalid JSON format") }); return; }
      const data = "server_key" in showInvoke
        ? await api.invokeMCPServerTool(showInvoke.server_key, parsed)
        : await api.invokeSkill(showInvoke.skill_id, parsed);
      setInvokeResult(data);
    } catch (e: unknown) {
      setInvokeResult({ error: e instanceof Error ? e.message : t("调用失败", "Invocation failed") });
    }
  };

  const openBindings = async (skill: Skill) => {
    setBindingSkill(skill);
    setBindingError("");
    try {
      const [all, current] = await Promise.all([api.listTools(), api.listSkillBindings(skill.skill_id)]);
      const allTools = Array.isArray(all) ? all as MCPTool[] : [];
      const currentTools = Array.isArray(current) ? current as MCPTool[] : [];
      setAvailableTools(allTools);
      setSelectedToolIds(new Set(currentTools.map((tool) => tool.id)));
    } catch (error) {
      setAvailableTools([]);
      setBindingError(error instanceof Error ? error.message : t("加载工具失败", "Failed to load tools"));
    }
  };

  const saveBindings = async () => {
    if (!bindingSkill) return;
    try {
      await api.updateSkillBindings(bindingSkill.skill_id, [...selectedToolIds]);
      setBindingSkill(null);
      await loadData();
    } catch (error) {
      setBindingError(error instanceof Error ? error.message : t("保存失败", "Save failed"));
    }
  };

  const checkMCPHealth = async (serverKey: string) => {
    setCheckingServer(serverKey);
    setHealthFeedback((previous) => ({ ...previous, [serverKey]: t("检测中…", "Checking…") }));
    try {
      const result = await api.checkMCPServerHealth(serverKey) as { status?: string; error?: string };
      const healthy = result.status === "healthy";
      setMcpServices((previous) => previous.map((service) => service.server_key === serverKey
        ? { ...service, health_status: healthy ? "healthy" : "unreachable", last_error: result.error ?? "" }
        : service));
      setHealthFeedback((previous) => ({
        ...previous,
        [serverKey]: healthy ? t("连接正常", "Connected") : t("连接失败", "Connection failed"),
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : t("健康检测失败", "Health check failed");
      setMcpServices((previous) => previous.map((service) => service.server_key === serverKey
        ? { ...service, health_status: "unreachable", last_error: message }
        : service));
      setHealthFeedback((previous) => ({ ...previous, [serverKey]: t("检测失败", "Check failed") }));
    } finally {
      setCheckingServer("");
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-5 md:px-6">

      <div className="rounded-2xl border border-outline-variant/10 bg-surface-container-lowest p-4 text-xs text-on-surface-variant shadow-sm">
        <p className="mb-1 flex items-center gap-2 font-semibold text-on-surface"><span className="material-symbols-outlined text-[17px] text-primary">hub</span>{t("技能定义处理流程，MCP 服务提供真实数据工具。", "Skills define workflows; MCP services provide real data tools.")}</p>
      </div>

      {/* Tabs */}
      <div className="flex w-fit gap-1 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-1 shadow-sm">
        <button onClick={() => setTab("skill")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "skill" ? "bg-primary text-on-primary" : "text-on-surface-variant hover:bg-surface-container"}`}>
          {t("技能", "Skills")}
        </button>
        <button onClick={() => setTab("mcp")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "mcp" ? "bg-primary text-on-primary" : "text-on-surface-variant hover:bg-surface-container"}`}>
          {t("MCP 服务", "MCP Services")}
        </button>
      </div>

      {loading ? (
        <p className="text-on-surface-variant text-sm py-12 text-center">{t("加载中...", "Loading...")}</p>
      ) : tab === "skill" ? (
        <div className="space-y-3">
          <div className="flex justify-end mb-2">
            <button onClick={() => { setCreateType("manual"); setShowCreate(true); }} className="px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-medium hover:opacity-90">
              {t("新增 Skill", "Add Skill")}
            </button>
          </div>
          {skills.filter((s) => !s.mcp_server && ["builtin", "manual"].includes(s.source_type)).length === 0 ? (
            <p className="text-on-surface-variant text-sm py-12 text-center">{t("暂无 Skill", "No skills")}</p>
          ) : (
            skills.filter((s) => !s.mcp_server && ["builtin", "manual"].includes(s.source_type)).map((s) => (
              <div key={s.id} className="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-4 transition-all hover:border-primary/20 hover:shadow-sm">
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-semibold text-on-surface mb-1">{skillDisplayName(s)}</h3>
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="px-2 py-0.5 rounded-full bg-secondary/10 text-secondary text-[10px] font-semibold">{t("技能流程", "Workflow")}</span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${s.status === "ACTIVE" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                        {s.status === "ACTIVE" ? t("已启用", "Active") : t("已停用", "Disabled")}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${s.source_type === "builtin" ? "bg-primary/10 text-primary" : "bg-amber-100 text-amber-700"}`}>
                        {s.source_type === "builtin" ? t("内置技能", "Built-in Skill") : t("自定义技能", "Custom Skill")}
                      </span>
                    </div>
                    <p className="text-xs text-on-surface-variant mb-1">{s.description}</p>
                    <p className="text-xs text-on-surface-variant">{t("分类", "Category")}: {s.category} · {t("版本", "Version")}: {s.version}</p>
                    <p className="text-xs text-on-surface-variant mt-1">{t("已绑定工具", "Bound tools")}: {(s.tools ?? []).map((tool) => toolDisplayName(tool.name)).join("、") || t("无", "None")}</p>
                    <p className="text-xs text-primary mt-1">{t("聊天示例", "Chat example")}: {(s.trigger_examples ?? [])[0] || t(`请使用${s.name}帮我处理`, `Use ${s.name} to help me`)}</p>
                  </div>
                  <div className="flex gap-1 ml-3">
                    <button onClick={() => void openBindings(s)} className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors" title={t("绑定工具", "Bind Tools")} aria-label={t("绑定工具", "Bind Tools")}>
                      <span className="material-symbols-outlined text-[18px]">link</span>
                    </button>
                    <button onClick={() => handleToggle(s.skill_id, s.status)} className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors" title={s.status === "ACTIVE" ? t("禁用", "Disable") : t("启用", "Enable")}>
                      <span className="material-symbols-outlined text-[18px]">{s.status === "ACTIVE" ? "toggle_on" : "toggle_off"}</span>
                    </button>
                    {(s.tools ?? []).length > 0 && (
                      <button onClick={() => {
                        setShowInvoke(s);
                        setInvokeResult(null);
                        const tool = preferredSkillTool(s);
                        const toolName = tool?.name ?? "";
                        setInvokeInput(JSON.stringify({ tool: toolName, params: testParamsForTool(toolName, s.skill_id) }, null, 2));
                      }} className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors" title={t("流程测试", "Workflow Test")} aria-label={t("流程测试", "Workflow Test")}>
                        <span className="material-symbols-outlined text-[18px]">play_arrow</span>
                      </button>
                    )}
                    {(s.tools ?? []).length === 0 && (
                      <span className="p-1.5 text-on-surface-variant/50" title={t("未绑定工具", "No bound tool")}>
                        <span className="material-symbols-outlined text-[18px]">link_off</span>
                      </span>
                    )}
                    <button onClick={() => handleShowLogs(s)} className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors" title={t("调用日志", "Invocation Logs")}>
                      <span className="material-symbols-outlined text-[18px]">history</span>
                    </button>
                    <button onClick={() => handleDelete(s.skill_id)} className="p-1.5 rounded-full hover:bg-error/10 text-on-surface-variant hover:text-error transition-colors" title={t("删除", "Delete")}>
                      <span className="material-symbols-outlined text-[18px]">delete</span>
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      ) : tab === "mcp" ? (
        <div className="space-y-3">
          <div className="flex justify-end mb-2">
            <button onClick={() => { setCreateType("mcp"); setShowCreate(true); }} className="px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-medium hover:opacity-90">
              {t("新增 MCP Server", "Add MCP Server")}
            </button>
          </div>
          {mcpServices.length === 0 ? (
            <div className="text-center py-12">
              <span className="material-symbols-outlined text-4xl text-on-surface-variant/30 mb-3 block">cloud_off</span>
              <p className="text-on-surface-variant text-sm mb-4">{t("暂无 MCP 服务", "No MCP services")}</p>
              <p className="text-xs text-on-surface-variant">{t("新增时会真实执行 initialize 与 tools/list。", "Creation performs real initialize and tools/list calls.")}</p>
            </div>
          ) : (
            mcpServices.map((s) => (
              <div key={s.id} className="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-4 transition-all hover:border-primary/20 hover:shadow-sm">
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-semibold text-on-surface">{mcpDisplayName(s)}</h3>
                      <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-[10px] font-semibold">{t("数据工具服务", "Data tool service")}</span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${s.health_status === "healthy" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                        {s.health_status === "healthy" ? t("正常", "Healthy") : s.health_status === "unreachable" ? t("连接异常", "Unreachable") : t("未检测", "Unknown")}
                      </span>
                    </div>
                    <p className="text-xs text-on-surface-variant mb-1">{s.description}</p>
                    <p className="text-xs text-on-surface-variant">MCP: {s.url}</p>
                    {healthFeedback[s.server_key] && <p className={`text-[11px] mt-1 ${s.health_status === "healthy" ? "text-green-700" : "text-error"}`}>{healthFeedback[s.server_key]}</p>}
                    {s.last_error && s.health_status === "unreachable" && <p className="text-[11px] text-error mt-1 break-all">{s.last_error}</p>}
                    {(mcpTools[s.server_key] ?? []).length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {(mcpTools[s.server_key] ?? []).map((tool, i) => (
                          <span key={i} title={tool.name} className="px-2 py-0.5 rounded bg-surface-container text-[10px] text-on-surface-variant">{toolDisplayName(tool.name)}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex gap-1 ml-3">
                    <button onClick={() => setTab("skill")} className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors" title={t("绑定到技能", "Bind to Skill")} aria-label={t("绑定到技能", "Bind to Skill")}>
                      <span className="material-symbols-outlined text-[18px]">link</span>
                    </button>
                    <button disabled={checkingServer === s.server_key} onClick={() => void checkMCPHealth(s.server_key)} className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant disabled:opacity-50" title={t("健康检测", "Health Check")}>
                      <span className={`material-symbols-outlined text-[18px] ${checkingServer === s.server_key ? "animate-pulse" : ""}`}>monitor_heart</span>
                    </button>
                    <button onClick={() => {
                      setShowInvoke(s);
                      setInvokeResult(null);
                      const tool = preferredMCPTool(mcpTools[s.server_key] ?? []);
                      const toolName = tool?.name ?? "";
                      setInvokeInput(JSON.stringify({ tool: toolName, params: testParamsForTool(toolName) }, null, 2));
                    }} className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors" title={t("工具调试", "Tool Debug")} aria-label={t("工具调试", "Tool Debug")}>
                      <span className="material-symbols-outlined text-[18px]">bug_report</span>
                    </button>
                    <button onClick={async () => { if (confirm(t("确认删除该 MCP Server？", "Delete this MCP Server?"))) { await api.deleteMCPServer(s.server_key); await loadData(); } }} className="p-1.5 rounded-full hover:bg-error/10 text-on-surface-variant hover:text-error transition-colors" title={t("删除", "Delete")}>
                      <span className="material-symbols-outlined text-[18px]">delete</span>
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-4 mb-2">
            <p className="text-xs text-on-surface-variant">{t("仅提供提示、触发规则和业务说明，不会执行外部调用。", "Prompt and trigger metadata only; no external execution.")}</p>
            <button onClick={() => { setCreateType("manual"); setShowCreate(true); }} className="shrink-0 px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-medium hover:opacity-90">
              {t("新增手动 Skill", "Add Manual Skill")}
            </button>
          </div>
          {skills.filter((s) => s.source_type === "manual" && !s.mcp_server).length === 0 ? (
            <p className="text-on-surface-variant text-sm py-12 text-center">{t("暂无手动 Skill", "No manual skills")}</p>
          ) : skills.filter((s) => s.source_type === "manual" && !s.mcp_server).map((s) => (
            <div key={s.id} className="p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/15">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-sm font-semibold text-on-surface">{s.name}</h3>
                    <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-semibold">{t("不可执行", "Metadata only")}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${s.status === "ACTIVE" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>{s.status}</span>
                  </div>
                  <p className="text-xs text-on-surface-variant mb-1">{s.description}</p>
                  <p className="text-xs text-on-surface-variant">{t("触发示例", "Trigger examples")}: {s.trigger_examples.join("；") || "—"}</p>
                </div>
                <div className="flex gap-1">
                  <button onClick={() => handleToggle(s.skill_id, s.status)} className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant" title={s.status === "ACTIVE" ? t("禁用", "Disable") : t("启用", "Enable")}>
                    <span className="material-symbols-outlined text-[18px]">{s.status === "ACTIVE" ? "toggle_on" : "toggle_off"}</span>
                  </button>
                  <button onClick={() => handleShowLogs(s)} className="p-1.5 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors" title={t("调用记录", "Invocation Logs")}>
                    <span className="material-symbols-outlined text-[18px]">history</span>
                  </button>
                  <button onClick={() => handleDelete(s.skill_id)} className="p-1.5 rounded-full hover:bg-error/10 text-on-surface-variant hover:text-error" title={t("删除", "Delete")}>
                    <span className="material-symbols-outlined text-[18px]">delete</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 创建技能弹窗 */}
      {bindingSkill && (
        <div onClick={() => setBindingSkill(null)} className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div onClick={(event) => event.stopPropagation()} className="bg-surface-container rounded-2xl w-full max-w-lg p-6 max-h-[calc(100dvh-2rem)] overflow-y-auto">
            <div className="flex items-start justify-between mb-4">
              <div><h2 className="text-lg font-bold text-on-surface">{t("绑定工具", "Bind Tools")}</h2><p className="text-xs text-on-surface-variant mt-1">{bindingSkill.name} · {t("可同时绑定内置工具和 MCP 工具", "Bind built-in and MCP tools")}</p></div>
              <button onClick={() => setBindingSkill(null)} className="p-1.5 rounded-full hover:bg-surface-container-high"><span className="material-symbols-outlined text-lg">close</span></button>
            </div>
            {bindingError && <p className="mb-3 text-sm text-error">{bindingError}</p>}
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {availableTools.length === 0 ? <p className="text-sm text-on-surface-variant py-6 text-center">{t("暂无可绑定工具，请先新增 MCP Server。", "No tools available. Add an MCP Server first.")}</p> : availableTools.map((tool) => (
                <label key={tool.id} className="flex items-start gap-3 rounded-xl bg-surface-container-low p-3 cursor-pointer">
                  <input type="checkbox" className="mt-0.5" checked={selectedToolIds.has(tool.id)} onChange={(event) => setSelectedToolIds((previous) => { const next = new Set(previous); if (event.target.checked) next.add(tool.id); else next.delete(tool.id); return next; })} />
                  <span><span className="block text-sm font-medium text-on-surface" title={tool.name}>{toolDisplayName(tool.name)}</span><span className="block text-xs text-on-surface-variant mt-0.5">{tool.description || "—"}</span><span className="text-[10px] text-primary">{tool.requires_confirmation ? t("写操作 · 需要确认", "Write · confirmation required") : tool.read_only ? t("只读", "Read-only") : t("未声明只读", "Not declared read-only")}</span></span>
                </label>
              ))}
            </div>
            <div className="flex justify-end gap-3 mt-5"><button onClick={() => setBindingSkill(null)} className="px-4 py-2 text-sm text-on-surface-variant">{t("取消", "Cancel")}</button><button onClick={() => void saveBindings()} className="px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-medium">{t("保存绑定", "Save Bindings")}</button></div>
          </div>
        </div>
      )}

      {/* 创建技能弹窗 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-container rounded-2xl w-full max-w-md mx-4 p-6 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-bold text-on-surface mb-1">
              {createType === "mcp" ? t("新增 MCP Server", "Add MCP Server") : t("新增 Skill", "Add Skill")}
            </h2>
            <p className="text-xs text-on-surface-variant mb-4">
              {createType === "builtin" ? t("绑定项目中已经实现的 Python 执行器。", "Bind an existing Python executor in this project.") : createType === "mcp" ? t("连接真实 MCP 服务并自动发现工具。", "Connect to a real MCP server and discover its tools.") : t("仅保存业务说明与触发规则，不具备执行能力。", "Store business guidance and triggers without execution.")}
            </p>
            <div className="space-y-3">
              {createType !== "mcp" && (
                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("Skill 类型 *", "Skill Type *")}</label>
                  <div className="grid grid-cols-2 gap-2 rounded-xl bg-surface-container-low p-1">
                    <button type="button" onClick={() => setCreateType("builtin")} className={`rounded-lg px-3 py-2 text-sm ${createType === "builtin" ? "bg-primary text-on-primary" : "text-on-surface-variant"}`}>
                      {t("内置 Skill", "Built-in Skill")}
                    </button>
                    <button type="button" onClick={() => setCreateType("manual")} className={`rounded-lg px-3 py-2 text-sm ${createType === "manual" ? "bg-primary text-on-primary" : "text-on-surface-variant"}`}>
                      {t("手动 Skill", "Manual Skill")}
                    </button>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1">Skill ID *</label>
                  <input value={form.skill_id} onChange={(e) => setForm({ ...form, skill_id: e.target.value })} placeholder="drug-safety"
                    className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("名称 *", "Name *")}</label>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("药物相互作用", "Drug Interaction")}
                    className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("描述", "Description")}</label>
                <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder={t("查询药物间的相互作用", "Query drug interactions")}
                  className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("分类", "Category")}</label>
                  <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("版本", "Version")}</label>
                  <input value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("关键词（逗号分隔）", "Keywords (comma separated)")}</label>
                <input value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} placeholder={t("药物,相互作用,安全", "drug,interaction,safety")}
                  className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("触发示例（逗号分隔）", "Trigger Examples (comma separated)")}</label>
                <input value={form.trigger_examples} onChange={(e) => setForm({ ...form, trigger_examples: e.target.value })} placeholder={t("这两种药能一起吃吗", "Can these two drugs be taken together?")}
                  className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm" />
              </div>
              {createType === "builtin" && (
                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("项目内置执行器 *", "Built-in Executor *")}</label>
                  <select value={form.builtin_tool} onChange={(e) => setForm({ ...form, builtin_tool: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm">
                    <option value="">{t("请选择执行器", "Select an executor")}</option>
                    {builtinTools.map((tool) => <option key={tool.name} value={tool.name}>{tool.name} — {tool.description}</option>)}
                  </select>
                </div>
              )}
              {createType === "mcp" && (
                <div>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("MCP 服务地址 *", "MCP Server Address *")}</label>
                  <input value={form.mcp_server} onChange={(e) => setForm({ ...form, mcp_server: e.target.value })} placeholder="https://pubmed.caseyjhand.com/mcp"
                    className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm" />
                  <p className="text-[11px] text-on-surface-variant mt-1">{t("创建时会真实连接并读取 tools/list；失败则不会保存。", "Creation performs a real tools/list call and is rejected on failure.")}</p>
                </div>
              )}
              {createError && <p className="text-sm text-error">{createError}</p>}
            </div>
            <div className="flex gap-3 justify-end mt-5">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-xl text-sm text-on-surface-variant hover:bg-surface-container-high">{t("取消", "Cancel")}</button>
              <button onClick={handleCreate} disabled={creating} className="px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-medium hover:opacity-90 disabled:opacity-50">
                {creating ? t("创建中...", "Creating...") : t("创建", "Create")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 调用日志弹窗 */}
      {showLogs && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-container rounded-2xl w-full max-w-lg mx-4 p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-on-surface">{t("调用日志", "Invocation Logs")}: {showLogs.name}</h2>
              <button onClick={() => setShowLogs(null)} className="p-1.5 rounded-full hover:bg-surface-container-high">
                <span className="material-symbols-outlined text-lg text-on-surface-variant">close</span>
              </button>
            </div>
            {logsLoading ? (
              <p className="text-on-surface-variant text-sm py-4 text-center">{t("加载中...", "Loading...")}</p>
            ) : logs.length === 0 ? (
              <p className="text-on-surface-variant text-sm py-4 text-center">{t("暂无调用记录", "No invocation records")}</p>
            ) : (
              <div className="space-y-2">
                {logs.map((l) => (
                  <div key={l.id} className="p-3 rounded-lg bg-surface-container-low text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-on-surface">{l.tool_name}</span>
                      <span className={`px-1.5 py-0.5 rounded ${l.result_status === "success" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                        {l.result_status}
                      </span>
                    </div>
                    <p className="text-on-surface-variant">{t("延迟", "Latency")}: {l.latency_ms}ms · {new Date(l.created_at).toLocaleString("zh-CN")}</p>
                    {l.error_reason && <p className="text-error mt-1">{l.error_reason}</p>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 调用测试弹窗 */}
      {showInvoke && (
        <div onClick={() => setShowInvoke(null)} className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/50 backdrop-blur-sm p-4">
          <div onClick={(event) => event.stopPropagation()} className="bg-surface-container rounded-2xl w-full max-w-md p-6 max-h-[calc(100dvh-2rem)] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-on-surface">{t("调用", "Invoke")}: {showInvoke.name}</h2>
              <button onClick={() => setShowInvoke(null)} className="p-1.5 rounded-full hover:bg-surface-container-high">
                <span className="material-symbols-outlined text-lg text-on-surface-variant">close</span>
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1">{t("输入参数 (JSON)", "Input Parameters (JSON)")}</label>
                <textarea value={invokeInput} onChange={(e) => setInvokeInput(e.target.value)} rows={4}
                  className="w-full px-3 py-2 rounded-lg bg-surface-container-highest text-on-surface border border-outline/30 text-sm font-mono resize-none" />
              </div>
              <button onClick={handleInvoke} className="w-full px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-medium hover:opacity-90">
                {t("执行调用", "Execute")}
              </button>
              {invokeResult != null && (
                <div className="p-3 rounded-lg bg-surface-container-low text-xs overflow-auto max-h-[45dvh]">
                  <pre className="text-on-surface whitespace-pre-wrap break-words">{JSON.stringify(invokeResult, null, 2)}</pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
