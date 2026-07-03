/**
 * FastAPI 后端 API 客户端
 * 所有请求统一走 NEXT_PUBLIC_API_URL
 */

import { getStoredAuthToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function withAuthHeaders(headers: Record<string, string> = {}) {
  const token = getStoredAuthToken();
  return token
    ? { ...headers, Authorization: `Bearer ${token}` }
    : headers;
}

async function readErrorMessage(res: Response, fallback: string) {
  try {
    const data = await res.json();
    return typeof data?.detail === "string" ? data.detail : fallback;
  } catch {
    return fallback;
  }
}

export function toAbsoluteMediaUrl(url: string) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  // Media tags cannot send an Authorization header, so use the API's
  // query-token fallback. Keep the token source consistent with auth.ts.
  const token = getStoredAuthToken();
  const separator = url.includes("?") ? "&" : "?";
  const fullUrl = `${API_BASE}${url}`;
  return token ? `${fullUrl}${separator}token=${encodeURIComponent(token)}` : fullUrl;
}

export const api = {
  base: API_BASE,

  /** 注册 */
  async register(username: string, password: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "注册失败"));
    return res.json();
  },

  /** 登录 */
  async login(username: string, password: string) {
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "登录失败"));
    return res.json();
  },

  /** 当前登录用户 */
  async getCurrentUser() {
    const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取当前用户失败");
    return res.json();
  },

  /** 创建问诊会话 */
  async createSession(): Promise<{ session_id: string; status: string }> {
    const res = await fetch(`${API_BASE}/api/v1/consultations`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error("创建会话失败");
    return res.json();
  },

  /** 发送消息（非流式，支持多模态）*/
  async sendMessage(
    sessionId: string,
    content: string | Array<{ type: string; text?: string; image_url?: { url: string }; video_url?: { url: string } }>,
    lang?: string,
    mediaUrls?: string[]
  ): Promise<{
    status: string;
    assistant_message: string;
    structured_state: Record<string, unknown>;
    red_flag_detected: boolean;
  }> {
    const res = await fetch(
      `${API_BASE}/api/v1/consultations/${sessionId}/messages`,
      {
        method: "POST",
        headers: withAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ role: "user", content, lang, media_urls: mediaUrls }),
      }
    );
    if (!res.ok) throw new Error(`发送消息失败 ${res.status}`);
    return res.json();
  },

  /** 发送消息（SSE 流式，支持多模态）*/
  async sendMessageStream(
    sessionId: string,
    content: string | Array<{ type: string; text?: string; image_url?: { url: string }; video_url?: { url: string } }>,
    lang?: string,
    mediaUrls?: string[],
    clientRequestId?: string
  ): Promise<ReadableStreamDefaultReader<Uint8Array>> {
    const res = await fetch(
      `${API_BASE}/api/v1/consultations/${sessionId}/messages/stream`,
      {
        method: "POST",
        headers: withAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          role: "user", content, lang, media_urls: mediaUrls,
          client_request_id: clientRequestId ?? crypto.randomUUID(),
        }),
      }
    );
    if (!res.ok) throw new Error(`发送消息失败 ${res.status}`);
    if (!res.body) throw new Error("响应体为空");
    return res.body.getReader();
  },

  /** 获取会话详情（含历史消息）*/
  async getSession(sessionId: string): Promise<{
    session_id: string;
    status: string;
    messages: {
      role: string;
      content: string;
      tool_call_id?: string;
      tool_name?: string;
      skill_name?: string;
      tool_status?: string;
      tool_args?: Record<string, unknown>;
      tool_result?: Record<string, unknown>;
      message_id?: string;
      generation_status?: string;
    }[];
    red_flag_detected: boolean;
  }> {
    const res = await fetch(`${API_BASE}/api/v1/consultations/${sessionId}`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取会话失败");
    return res.json();
  },

  /** 获取会话结论摘要 */
  async getSessionSummary(sessionId: string) {
    const res = await fetch(
      `${API_BASE}/api/v1/consultations/${sessionId}/summary`,
      { headers: withAuthHeaders() }
    );
    if (!res.ok) throw new Error("获取摘要失败");
    return res.json();
  },

  /** 生成事件卡 */
  async createEventCard(sessionId: string, eventCard: Record<string, unknown>) {
    const res = await fetch(
      `${API_BASE}/api/v1/consultations/${sessionId}/event-card`,
      {
        method: "POST",
        headers: withAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ event_card: eventCard }),
      }
    );
    if (!res.ok) throw new Error("生成事件卡失败");
    return res.json();
  },

  /** 确认事件卡 */
  async confirmEvent(eventId: string) {
    const res = await fetch(
      `${API_BASE}/api/v1/health-events/${eventId}/confirm`,
      {
        method: "POST",
        headers: withAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({}),
      }
    );
    if (!res.ok) throw new Error("确认事件卡失败");
    return res.json();
  },

  /** 将事件归档到健康档案 */
  async archiveEvent(eventId: string) {
    const res = await fetch(
      `${API_BASE}/api/v1/health-events/${eventId}/archive`,
      {
        method: "POST",
        headers: withAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({}),
      }
    );
    if (!res.ok) throw new Error("归档事件失败");
    return res.json();
  },

  /** 取消事件归档，同时移除关联健康档案/EHR 数据 */
  async unarchiveEvent(eventId: string) {
    const res = await fetch(
      `${API_BASE}/api/v1/health-events/${eventId}/archive`,
      { method: "DELETE", headers: withAuthHeaders() }
    );
    if (!res.ok) throw new Error(await readErrorMessage(res, "取消归档失败"));
    return res.json();
  },

  /** 删除通用执行及其关联健康档案/EHR 数据 */
  async deleteEvent(eventId: string) {
    const res = await fetch(`${API_BASE}/api/v1/health-events/${eventId}`, {
      method: "DELETE",
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "删除通用执行失败"));
    return res.json();
  },

  /** 执行事件卡中的所有任务 */
  async executeEvent(eventId: string) {
    const res = await fetch(
      `${API_BASE}/api/v1/health-events/${eventId}/execute`,
      {
        method: "POST",
        headers: withAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({}),
      }
    );
    if (!res.ok) throw new Error("执行任务失败");
    return res.json();
  },

  /** 标记任务为完成 */
  async completeTask(eventId: string, taskId: string) {
    const res = await fetch(
      `${API_BASE}/api/v1/health-events/${eventId}/tasks/${taskId}/complete`,
      {
        method: "POST",
        headers: withAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({}),
      }
    );
    if (!res.ok) throw new Error("标记任务失败");
    return res.json();
  },

  /** 获取事件卡 */
  async getEvent(eventId: string) {
    const res = await fetch(`${API_BASE}/api/v1/health-events/${eventId}`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取事件卡失败");
    return res.json();
  },

  /** 获取推荐任务 */
  async getEventTasks(eventId: string) {
    const res = await fetch(
      `${API_BASE}/api/v1/health-events/${eventId}/tasks`,
      { headers: withAuthHeaders() }
    );
    if (!res.ok) throw new Error("获取推荐任务失败");
    return res.json();
  },

  /** 健康事件列表 */
  async listEvents() {
    const res = await fetch(`${API_BASE}/api/v1/health-events`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取事件列表失败");
    return res.json();
  },

  /** 提醒列表 */
  async listReminders() {
    const res = await fetch(`${API_BASE}/api/v1/reminders`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取提醒失败");
    return res.json();
  },

  /** 创建提醒 */
  async createReminder(body: Record<string, unknown>) {
    const res = await fetch(`${API_BASE}/api/v1/reminders`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("创建提醒失败");
    return res.json();
  },

  /** 档案列表 */
  async listRecords() {
    const res = await fetch(`${API_BASE}/api/v1/records`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取档案失败");
    return res.json();
  },

  /** 同步单条档案到 EHR */
  async syncRecord(recordId: string) {
    const res = await fetch(`${API_BASE}/api/v1/records/${recordId}/sync`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error("同步档案失败");
    return res.json();
  },

  /** 取消单条档案的 EHR 同步 */
  async unsyncRecord(recordId: string) {
    const res = await fetch(`${API_BASE}/api/v1/records/${recordId}/sync`, {
      method: "DELETE",
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "取消同步失败"));
    return res.json();
  },

  /** 批量同步档案到 EHR */
  async batchSyncRecords() {
    const res = await fetch(`${API_BASE}/api/v1/records/sync`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error("批量同步失败");
    return res.json();
  },

  /** 生成完整 EHR 摘要 */
  async generateEhrSummary(manualHistory: string) {
    const res = await fetch(`${API_BASE}/api/v1/records/ehr-summary`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ manual_history: manualHistory }),
    });
    if (!res.ok) throw new Error("生成 EHR 失败");
    return res.json();
  },

  /** 读取健康档案输入信息（用户级） */
  async getHealthArchiveProfile() {
    const res = await fetch(`${API_BASE}/api/v1/records/profile`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "获取健康档案输入失败"));
    return res.json();
  },

  /** 保存健康档案输入信息（用户级） */
  async updateHealthArchiveProfile(body: {
    name: string;
    gender: string;
    age: string;
    contact: string;
    manual_history: string;
  }) {
    const res = await fetch(`${API_BASE}/api/v1/records/profile`, {
      method: "PUT",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "保存健康档案输入失败"));
    return res.json();
  },

  /** 导出 EHR PDF（后端生成，支持中文） */
  async exportEhrPdf(content: string, filename = "complete-ehr.pdf") {
    const res = await fetch(`${API_BASE}/api/v1/records/export-pdf`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ content, filename }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "导出 PDF 失败"));
    return res.blob();
  },

  /** 上传文档（支持 PDF/Word/TXT） */
  async uploadDocument(file: File): Promise<{
    status: string;
    filename: string;
    url: string;
    size: number;
    type: string;
    extracted_text: string;
    extraction_status: "success" | "unsupported" | "failed" | "empty";
    report_id?: string;
    lab_summary?: string;
    lab_items?: Array<{
      name: string;
      value: string;
      unit?: string;
      reference_range?: string;
      abnormal?: boolean;
      interpretation?: string;
    }>;
  }> {
    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`${API_BASE}/api/v1/upload/document`, {
      method: "POST",
      headers: withAuthHeaders(),
      body: form,
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "文件上传失败"));
    const data = await res.json();
    return {
      ...data,
      url: toAbsoluteMediaUrl(data.url || ""),
    };
  },

  /** 上传音频进行 Whisper 转写 */
  async uploadAudio(file: File): Promise<{
    status: string;
    text: string;
    filename: string;
  }> {
    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`${API_BASE}/api/v1/upload/audio`, {
      method: "POST",
      headers: withAuthHeaders(),
      body: form,
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "语音转写失败"));
    return res.json();
  },

  /** 上传视频用于多模态问诊 */
  async uploadVideo(file: File): Promise<{
    status: string;
    filename: string;
    url: string;
    size: number;
    type: string;
  }> {
    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`${API_BASE}/api/v1/upload/video`, {
      method: "POST",
      headers: withAuthHeaders(),
      body: form,
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "视频上传失败"));
    const data = await res.json();
    return {
      ...data,
      url: toAbsoluteMediaUrl(data.url || ""),
    };
  },

  /** IoT 近期生命体征 */
  async getLatestVitals() {
    const res = await fetch(`${API_BASE}/api/v1/iot/latest`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取生命体征失败");
    return res.json();
  },

  /** IoT 模拟推送（开发联调） */
  async simulateVitalPush(body: {
    source?: string;
    metric?: string;
    value: number;
    unit?: string;
    measured_at: string;
    event_id?: string;
  }) {
    const res = await fetch(`${API_BASE}/api/v1/iot/simulate`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        source: body.source ?? "xiaomi-health",
        metric: body.metric ?? "heart_rate",
        value: body.value,
        unit: body.unit ?? "bpm",
        measured_at: body.measured_at,
        event_id: body.event_id ?? "",
      }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "IoT 模拟推送失败"));
    return res.json();
  },

  /** 人工接管工单 */
  async listHandoffs() {
    const res = await fetch(`${API_BASE}/api/v1/handoffs`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取接管工单失败");
    return res.json();
  },

  /** 创建主动干预规则 */
  async createProactiveRule(body: { condition_value: string; city: string; condition_type?: string; enabled?: boolean }) {
    const res = await fetch(`${API_BASE}/api/v1/proactive/rules`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "创建主动规则失败"));
    return res.json();
  },

  /** 触发一次主动扫描 */
  async runProactiveScan() {
    const res = await fetch(`${API_BASE}/api/v1/proactive/run`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "执行主动扫描失败"));
    return res.json();
  },

  /** 上传头像 */
  async uploadAvatar(file: File) {
    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`${API_BASE}/api/v1/upload/avatar`, {
      method: "POST",
      headers: withAuthHeaders(),
      body: form,
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "头像上传失败"));
    const data = await res.json();
    return {
      ...data,
      url: toAbsoluteMediaUrl(data.url || ""),
    };
  },

  /** 技能列表 */
  async listSkills() {
    const res = await fetch(`${API_BASE}/api/v1/skills`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取技能列表失败");
    return res.json();
  },

  /** 注册技能 */
  async createSkill(body: Record<string, unknown>) {
    const res = await fetch(`${API_BASE}/api/v1/skills`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "注册技能失败"));
    return res.json();
  },

  async listBuiltinTools() {
    const res = await fetch(`${API_BASE}/api/v1/skills/builtin-tools`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "获取内置执行器失败"));
    return res.json();
  },

  /** 调用技能 */
  async invokeSkill(
    skillId: string,
    input: Record<string, unknown>,
    traceId?: string
  ) {
    const res = await fetch(`${API_BASE}/api/v1/skills/${skillId}/invoke`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ input, trace_id: traceId ?? "" }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "调用技能失败"));
    return res.json();
  },

  /** 技能调用日志 */
  async getSkillLogs(skillId: string) {
    const res = await fetch(`${API_BASE}/api/v1/skills/${skillId}/logs`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取日志失败");
    return res.json();
  },

  /** 切换技能状态 */
  async updateSkillStatus(skillId: string, status: "ACTIVE" | "DISABLED") {
    const res = await fetch(`${API_BASE}/api/v1/skills/${skillId}/status?status=${status}`, {
      method: "PATCH",
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("更新技能状态失败");
    return res.json();
  },

  /** 删除技能 */
  async deleteSkill(skillId: string) {
    const res = await fetch(`${API_BASE}/api/v1/skills/${skillId}`, {
      method: "DELETE",
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("删除技能失败");
  },

  /** 删除问诊会话 */
  async deleteSession(sessionId: string) {
    const res = await fetch(`${API_BASE}/api/v1/consultations/${sessionId}`, {
      method: "DELETE",
      headers: withAuthHeaders(),
    });
    if (!res.ok && res.status !== 204) throw new Error("删除会话失败");
  },

  /** 获取历史问诊列表 */
  async listSessions(): Promise<{ session_id: string; status: string; created_at: string; updated_at?: string; chief_complaint: string; triage_level: string }[]> {
    const res = await fetch(`${API_BASE}/api/v1/consultations`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取历史问诊失败");
    return res.json();
  },

  /** 获取患者上下文信息（记忆、检验、穿戴数据） */
  async getPatientContext(): Promise<{
    memory_facts: { id: string; type: string; text: string; confidence: number }[];
    latest_report: { id: string; summary: string; created_at: string | null } | null;
    vitals: { id: string; metric: string; value: string | number; unit: string; risk_level: string; created_at: string | null }[];
  }> {
    const res = await fetch(`${API_BASE}/api/v1/consultations/context/patient`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取患者上下文失败");
    return res.json();
  },

  // ---- 知识图谱 ----

  /** 搜索知识图谱实体 */
  async kgSearch(q: string, type: string = "all", limit: number = 20) {
    const res = await fetch(`${API_BASE}/api/v1/kg/search?q=${encodeURIComponent(q)}&type=${type}&limit=${limit}`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("搜索知识图谱失败");
    return res.json() as Promise<{ results: { type: string; name: string; desc: string }[]; total: number }>;
  },

  /** 获取节点详情 */
  async kgNode(entityType: string, name: string) {
    const res = await fetch(`${API_BASE}/api/v1/kg/node/${entityType}/${encodeURIComponent(name)}`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取节点详情失败");
    return res.json();
  },

  /** 获取节点详情（别名，供 MiniKnowledgeGraph 使用） */
  async kgNodeDetail(entityType: string, name: string) {
    return this.kgNode(entityType, name);
  },

  /** 获取邻居节点 */
  async kgNeighbors(entityType: string, name: string) {
    const res = await fetch(`${API_BASE}/api/v1/kg/neighbors/${entityType}/${encodeURIComponent(name)}`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取邻居节点失败");
    return res.json() as Promise<{ nodes: KGNode[]; edges: KGEdge[] }>;
  },

  /** 获取子图 */
  async kgSubgraph(entityType: string, name: string, depth: number = 1) {
    const res = await fetch(`${API_BASE}/api/v1/kg/subgraph/${entityType}/${encodeURIComponent(name)}?depth=${depth}`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取子图失败");
    return res.json() as Promise<{ nodes: KGNode[]; edges: KGEdge[] }>;
  },

  /** 获取问诊上下文图谱 */
  async kgConsultationContext(symptoms: string, diseases: string = "") {
    const res = await fetch(`${API_BASE}/api/v1/kg/consultation-context?symptoms=${encodeURIComponent(symptoms)}&diseases=${encodeURIComponent(diseases)}`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取问诊图谱失败");
    return res.json() as Promise<{ nodes: KGNode[]; edges: KGEdge[]; symptom_diseases: Record<string, string[]> }>;
  },

  // ─── LLM 配置 ───────────────────────────────────────────────────

  async getLLMConfig() {
    const res = await fetch(`${API_BASE}/api/v1/auth/llm-config`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error("获取 LLM 配置失败");
    return res.json() as Promise<{
      has_config: boolean; api_key_masked: string; base_url: string; model: string;
      asr_model: string; asr_base_url: string; tts_model: string; tts_base_url: string;
      omni_model: string; omni_base_url: string;
    }>;
  },

  async updateLLMConfig(body: {
    api_key?: string; base_url: string; model: string;
    asr_model?: string; asr_base_url?: string;
    tts_model?: string; tts_base_url?: string;
    omni_model?: string; omni_base_url?: string;
  }) {
    const res = await fetch(`${API_BASE}/api/v1/auth/llm-config`, {
      method: "PUT",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "保存 LLM 配置失败"));
    return res.json();
  },

  // ─── 飞书 Webhook 配置 ──────────────────────────────────────────

  async getFeishuConfig() {
    const res = await fetch(`${API_BASE}/api/v1/auth/feishu-config`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error("获取飞书配置失败");
    return res.json();
  },

  async updateFeishuConfig(body: { webhook_url: string; enabled: boolean; webhook_secret?: string }) {
    const res = await fetch(`${API_BASE}/api/v1/auth/feishu-config`, {
      method: "PUT",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "保存飞书配置失败"));
    return res.json();
  },

  async testFeishuConfig() {
    const res = await fetch(`${API_BASE}/api/v1/auth/feishu-config/test`, {
      method: "POST",
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "飞书测试告警发送失败"));
    return res.json() as Promise<{ status: string }>;
  },

  // ─── 长期记忆 ───────────────────────────────────────────────────

  async listMemoryFacts(factType?: string, status?: string) {
    const params = new URLSearchParams();
    if (factType) params.set("fact_type", factType);
    if (status) params.set("status", status);
    const qs = params.toString();
    const res = await fetch(`${API_BASE}/api/v1/memory/facts${qs ? `?${qs}` : ""}`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error("获取记忆列表失败");
    return res.json();
  },

  async createDirectMemory(body: { fact_type: string; text: string }) {
    const res = await fetch(`${API_BASE}/api/v1/memory/facts/direct`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "创建记忆失败"));
    return res.json();
  },

  async confirmMemoryFact(factId: string) {
    const res = await fetch(`${API_BASE}/api/v1/memory/facts/${factId}/confirm`, {
      method: "PUT", headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("确认记忆失败");
    return res.json();
  },

  async rejectMemoryFact(factId: string) {
    const res = await fetch(`${API_BASE}/api/v1/memory/facts/${factId}/reject`, {
      method: "PUT", headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("拒绝记忆失败");
    return res.json();
  },

  async deleteMemoryFact(factId: string) {
    const res = await fetch(`${API_BASE}/api/v1/memory/facts/${factId}`, {
      method: "DELETE", headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("删除记忆失败");
    return res.json();
  },

  // ─── 定时科普任务 ───────────────────────────────────────────────

  async listScheduledTasks() {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error("获取定时任务失败");
    return res.json();
  },

  async createScheduledTask(body: Record<string, unknown>) {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "创建任务失败"));
    return res.json();
  },

  async updateScheduledTask(taskId: string, body: Record<string, unknown>) {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks/${taskId}`, {
      method: "PUT",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("更新任务失败");
    return res.json();
  },

  async deleteScheduledTask(taskId: string) {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks/${taskId}`, {
      method: "DELETE", headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("删除任务失败");
    return;
  },

  async toggleScheduledTask(taskId: string) {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks/${taskId}/toggle`, {
      method: "POST", headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("切换状态失败");
    return res.json();
  },

  async parseSchedule(text: string) {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks/parse`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error("解析时间失败");
    return res.json() as Promise<{ cron: string; topic: string; description: string }>;
  },

  /** 获取定时任务执行日志 */
  async getScheduledTaskLogs(taskId: string) {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks/${taskId}/logs`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取任务日志失败");
    return res.json() as Promise<Array<{
      id: string;
      task_id: string;
      content: string;
      status: string;
      error_message: string;
      executed_at: string;
    }>>;
  },

  /** 手动执行定时任务 */
  async executeScheduledTask(taskId: string) {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks/${taskId}/execute`, {
      method: "POST",
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("执行任务失败");
    return res.json() as Promise<{ status: string; content?: string; error?: string }>;
  },

  /** 获取定时任务未读计数 */
  async getScheduledTaskUnread() {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks/unread`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取未读计数失败");
    return res.json() as Promise<{ total_unread: number; task_unreads: Record<string, number> }>;
  },

  /** 标记单个任务为已读 */
  async markScheduledTaskRead(taskId: string) {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks/${taskId}/read`, {
      method: "POST",
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("标记已读失败");
    return res.json();
  },

  /** 标记所有定时任务为已读 */
  async markAllScheduledTasksRead() {
    const res = await fetch(`${API_BASE}/api/v1/scheduled-tasks/read-all`, {
      method: "POST",
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("标记全部已读失败");
    return res.json();
  },

  // ─── 知识库检索 ─────────────────────────────────────────────────

  async listKnowledgeDocuments(limit = 50, offset = 0) {
    const res = await fetch(`${API_BASE}/api/v1/rag/documents?limit=${limit}&offset=${offset}`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error("获取文档列表失败");
    return res.json();
  },

  async deleteKnowledgeDocument(docId: string) {
    const res = await fetch(`${API_BASE}/api/v1/rag/documents/${docId}`, {
      method: "DELETE", headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("删除文档失败");
    return res.json();
  },

  async ingestKnowledgeFile(file: File) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/api/v1/rag/ingest-file`, {
      method: "POST", headers: withAuthHeaders(), body: form,
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "文件入库失败"));
    return res.json();
  },

  async searchKnowledge(query: string, topK = 5): Promise<{
    query: string;
    result: Array<{ content: string; metadata: Record<string, unknown>; score: number }>;
    params: { top_k: number; score_threshold: number; use_mmr: boolean };
  }> {
    const res = await fetch(`${API_BASE}/api/v1/rag/search?q=${encodeURIComponent(query)}&top_k=${topK}`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error(await readErrorMessage(res, "检索失败"));
    return res.json();
  },

  // ─── 工具/MCP 管理 ─────────────────────────────────────────────

  async checkSkillHealth(skillId: string) {
    const res = await fetch(`${API_BASE}/api/v1/skills/${skillId}/health`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error("健康检查失败");
    return res.json();
  },

  async testSkill(skillId: string, input: Record<string, unknown>) {
    const res = await fetch(`${API_BASE}/api/v1/skills/${skillId}/test`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(input),
    });
    if (!res.ok) throw new Error("测试调用失败");
    return res.json();
  },

  async testBuiltinTool(tool: string, params: Record<string, unknown>) {
    const res = await fetch(`${API_BASE}/api/v1/skills/builtin/tools/test`, {
      method: "POST",
      headers: withAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ tool, params }),
    });
    if (!res.ok) throw new Error("内置工具调用失败");
    return res.json();
  },

  async listMCPServices() {
    const res = await fetch(`${API_BASE}/api/v1/mcp-servers`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error("获取 MCP 服务失败");
    return res.json();
  },

  async createMCPServer(body: Record<string, unknown>) {
    const res = await fetch(`${API_BASE}/api/v1/mcp-servers`, {
      method: "POST", headers: withAuthHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "MCP 服务连接失败"));
    return res.json();
  },

  async discoverMCPServer(serverKey: string) {
    const res = await fetch(`${API_BASE}/api/v1/mcp-servers/${encodeURIComponent(serverKey)}/discover`, {
      method: "POST", headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "MCP 工具发现失败"));
    return res.json();
  },

  async checkMCPServerHealth(serverKey: string) {
    const res = await fetch(`${API_BASE}/api/v1/mcp-servers/${encodeURIComponent(serverKey)}/health`, {
      method: "POST", headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "MCP 健康检测失败"));
    return res.json();
  },

  async listMCPServerTools(serverKey: string) {
    const res = await fetch(`${API_BASE}/api/v1/mcp-servers/${encodeURIComponent(serverKey)}/tools`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error(await readErrorMessage(res, "获取 MCP 工具失败"));
    return res.json();
  },

  async invokeMCPServerTool(serverKey: string, body: Record<string, unknown>) {
    const res = await fetch(`${API_BASE}/api/v1/mcp-servers/${encodeURIComponent(serverKey)}/invoke`, {
      method: "POST", headers: withAuthHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "MCP 工具调用失败"));
    return res.json();
  },

  async deleteMCPServer(serverKey: string) {
    const res = await fetch(`${API_BASE}/api/v1/mcp-servers/${encodeURIComponent(serverKey)}`, { method: "DELETE", headers: withAuthHeaders() });
    if (!res.ok && res.status !== 204) throw new Error(await readErrorMessage(res, "删除 MCP 服务失败"));
  },

  async listTools() {
    const res = await fetch(`${API_BASE}/api/v1/mcp-servers/tools/all`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error(await readErrorMessage(res, "获取工具列表失败"));
    return res.json();
  },

  async updateSkillBindings(skillId: string, toolIds: string[]) {
    const res = await fetch(`${API_BASE}/api/v1/skills/${encodeURIComponent(skillId)}/bindings`, {
      method: "PUT", headers: withAuthHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ tool_ids: toolIds }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, "更新 Skill 工具绑定失败"));
    return res.json();
  },

  async listSkillBindings(skillId: string) {
    const res = await fetch(`${API_BASE}/api/v1/skills/${encodeURIComponent(skillId)}/bindings`, { headers: withAuthHeaders() });
    if (!res.ok) throw new Error(await readErrorMessage(res, "获取 Skill 工具绑定失败"));
    return res.json();
  },

  async installSkillPackage(file: File) {
    const form = new FormData(); form.append("file", file);
    const res = await fetch(`${API_BASE}/api/v1/skills/packages/install`, { method: "POST", headers: withAuthHeaders(), body: form });
    if (!res.ok) throw new Error(await readErrorMessage(res, "安装 Skill 包失败"));
    return res.json();
  },
};

export interface KGNode {
  id: string;
  type: string;
  label: string;
  data: Record<string, unknown>;
}

export interface KGEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: string;
}
