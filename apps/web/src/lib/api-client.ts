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
  return `${API_BASE}${url}`;
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

  /** 发送消息（非流式）*/
  async sendMessage(
    sessionId: string,
    content: string
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
        body: JSON.stringify({ role: "user", content }),
      }
    );
    if (!res.ok) throw new Error(`发送消息失败 ${res.status}`);
    return res.json();
  },

  /** 获取会话详情（含历史消息）*/
  async getSession(sessionId: string): Promise<{
    session_id: string;
    status: string;
    messages: { role: string; content: string }[];
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
    if (!res.ok) throw new Error("注册技能失败");
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
    if (!res.ok) throw new Error("调用技能失败");
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
  async listSessions(): Promise<{ session_id: string; status: string; created_at: string; chief_complaint: string; triage_level: string }[]> {
    const res = await fetch(`${API_BASE}/api/v1/consultations`, {
      headers: withAuthHeaders(),
    });
    if (!res.ok) throw new Error("获取历史问诊失败");
    return res.json();
  },
};
