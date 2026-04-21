import OpenAI from "openai";

let client: OpenAI | null = null;

export function getLLMClient(): OpenAI {
  if (!client) {
    const apiKey = process.env.OPENAI_API_KEY || process.env.LLM_API_KEY;
    const baseURL =
      process.env.OPENAI_BASE_URL ||
      process.env.LLM_BASE_URL ||
      "https://yunwu.ai/v1";

    if (!apiKey) {
      throw new Error(
        "API Key 未配置，请在 .env.local 中设置 OPENAI_API_KEY"
      );
    }

    client = new OpenAI({ baseURL, apiKey });
  }
  return client;
}

export function getModel(): string {
  return process.env.LLM_MODEL || "gpt-4o-mini";
}

export function getTemperature(): number {
  const t = parseFloat(process.env.LLM_TEMPERATURE || "0.1");
  return isNaN(t) ? 0.1 : t;
}

// ===== 健康问诊工作区 System Prompt（PRD §13.1）=====
export const CONSULTATION_SYSTEM_PROMPT = `你是一个专业的健康问诊 AI 助手，遵循以下严格原则：

【工作原则】
1. 使用分阶段问诊流程：主诉采集 → 症状结构化 → 追问补全 → 风险识别 → 结论输出
2. 优先识别高风险红旗症状，再追求信息完整
3. 每轮追问控制在 1-2 个高价值问题，不得堆叠多个问题
4. 只输出阶段性判断，不输出确诊式表达
5. 不输出处方级指令，不生成处方
6. 遇到急重症信号立即提升分诊级别，优先建议紧急就医

【输出规范】
- 使用"可能""疑似""建议关注"等表述，严禁"确诊""已诊断"等表述
- 风险提示用专业但易懂的语言
- 给出建议科室和就医准备建议

【红旗症状】
以下症状出现时立即触发高风险拦截：
- 胸痛放射至左肩/下颌、冷汗
- 突发剧烈头痛（"一生中最严重"）
- 呼吸困难、意识改变
- 大量出血
- 骨折/严重外伤

【重要声明】
本系统为健康管理辅助工具，不替代线下医疗诊断和治疗，不提供确诊意见。`;

// ===== 生成结构化结论的 Prompt =====
export const CONCLUDE_PROMPT = `基于以下问诊对话记录，生成标准化健康事件卡。
必须严格按照以下 JSON 格式输出，不得添加任何额外文字：

{
  "chief_complaint": "主诉",
  "symptom_summary": ["症状1", "症状2"],
  "duration": "持续时间",
  "severity": "严重程度描述",
  "confirmed_points": ["已确认的症状要点1", "已确认的症状要点2"],
  "uncertain_points": ["仍不确定的信息1"],
  "red_flags": ["红旗症状（如有）"],
  "candidate_conditions": [
    {
      "name": "候选方向名称",
      "confidence": 0.7,
      "supporting_points": ["支持点1"],
      "against_points": ["不支持点1"]
    }
  ],
  "triage_level": "observe|outpatient|urgent_visit|emergency",
  "recommended_department": "建议科室",
  "visit_preparation": ["就医前准备1", "就医前准备2"],
  "care_todos": ["护理建议1"],
  "medication_reminder_suggestion": ["用药建议（如有）"],
  "followup_reminder_suggestion": ["复诊建议（如有）"],
  "record_update_suggestion": true,
  "insurance_material_suggestion": []
}

注意：candidate_conditions 是候选方向，不可表述为最终诊断。
triage_level 枚举值：observe（观察）/ outpatient（门诊）/ urgent_visit（急诊）/ emergency（急救）`;
