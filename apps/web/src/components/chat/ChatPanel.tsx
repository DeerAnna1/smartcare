"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { ImgHTMLAttributes } from "react";
import { useRouter } from "next/navigation";
import { api, toAbsoluteMediaUrl } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";
import { useTheme } from "@/lib/theme-context";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MiniKnowledgeGraph from "@/components/kg/MiniKnowledgeGraph";
import LLMConfigModal from "@/components/settings/LLMConfigModal";
import { useMobileSidebar } from "@/lib/mobile-sidebar-context";

// ReactMarkdown 自定义组件：图片 URL 自动加 auth token
const markdownComponents = {
  img: ({ src, alt, ...props }: ImgHTMLAttributes<HTMLImageElement>) => {
    const finalSrc = typeof src === "string" ? toAbsoluteMediaUrl(src) : src;
    return <img src={finalSrc} alt={alt || ""} {...props} className="max-w-full rounded-lg my-2" loading="lazy" />;
  },
};

// 去除上下文注入标签（这些信息已在右侧面板展示）
function stripContextTags(content: string): string {
  return content
    .replace(/\n?\[文档上下文(?::[^\]]*)?\][\s\S]*?\[\/文档上下文\]/gi, "")
    .replace(/\n?\[已查看附件:\s*[^\]]+\]/gi, "")
    .replace(/\n?\[用户长期记忆\][\s\S]*?(?=\n\[|$)/g, "")
    .replace(/\n?\[最近检验摘要\].*/g, "")
    .replace(/\n?\[最近穿戴设备数据\].*/g, "")
    .trim();
}

function extractViewedAttachments(content: string): string[] {
  return [...content.matchAll(/\[已查看附件:\s*([^\]]+)\]/gi)].map((match) => match[1].trim());
}

// Web Speech API 类型声明
interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}

interface Message {
  role: "user" | "assistant" | "tool";
  content: string;
  tags?: string[];
  followUpCards?: { title: string; question: string; borderColor: string }[];
  riskAlert?: { title: string; content: string };
  isThinking?: boolean;
  images?: string[]; // 用户上传的图片 base64 data URLs
  toolCallId?: string;
  toolName?: string;
  skillName?: string;
  toolStatus?: "running" | "success" | "failed";
  toolArgs?: Record<string, unknown>;
  messageId?: string;
  generationStatus?: "pending" | "streaming" | "completed" | "failed";
}

interface ToolEventData {
  call_id?: string;
  name?: string;
  skill_name?: string;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
}

interface Attachment {
  id: string;
  filename: string;
  url: string;
  size: number;
  type: string;
  extracted_text: string;
  extraction_status: "success" | "unsupported" | "failed" | "empty";
  report_id?: string;
  lab_summary?: string;
  uploading?: boolean;
  error?: string;
  imageDataUrl?: string; // base64 data URL for image attachments (for LLM vision)
}

interface ChatPanelProps {
  sessionId: string | null;
  showBackButton?: boolean;
  onMessageSent?: () => void;
}

export default function ChatPanel({ sessionId: initialSessionId, showBackButton = true, onMessageSent }: ChatPanelProps) {
  const router = useRouter();
  const { lang, toggleLang, t } = useLang();
  const { theme, toggleTheme } = useTheme();
  const { openMobile } = useMobileSidebar();
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);
  const [creatingSession, setCreatingSession] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [hasRedFlags, setHasRedFlags] = useState(false);
  const [showVoiceInput, setShowVoiceInput] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [sessionStatus, setSessionStatus] = useState<string>("");
  const [latestVitalHint, setLatestVitalHint] = useState<string>("");
  const [liveRiskLevel, setLiveRiskLevel] = useState<"normal" | "medium" | "high" | null>(null);
  const [iotHandoffDetected, setIotHandoffDetected] = useState(false);
  const [textRiskDetected, setTextRiskDetected] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 语音识别状态
  const [isRecording, setIsRecording] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const inputBeforeRecordingRef = useRef("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 图片预览状态
  const [previewImage, setPreviewImage] = useState<string | null>(null);

  // 知识图谱状态
  const [showKG, setShowKG] = useState(false);
  const [kgSymptoms, setKgSymptoms] = useState<string[]>([]);
  const [kgDiseases, setKgDiseases] = useState<string[]>([]);
  const [showLLMConfig, setShowLLMConfig] = useState(false);
  const [llmConfigChecked, setLlmConfigChecked] = useState(false);
  const [hasLLMConfig, setHasLLMConfig] = useState(false);

  const showToolStart = (data: ToolEventData) => {
    const callId = data.call_id || `${data.name || "tool"}-${Date.now()}`;
    setMessages((prev) => {
      const updated = [...prev];
      const activity: Message = {
        role: "tool",
        content: "",
        toolCallId: callId,
        toolName: data.name || "tool",
        skillName: data.skill_name || data.name || "Tool",
        toolStatus: "running",
        toolArgs: data.args || {},
      };
      const assistantIndex = updated.length - 1;
      if (assistantIndex >= 0 && updated[assistantIndex].role === "assistant") updated.splice(assistantIndex, 0, activity);
      else updated.push(activity);
      return updated;
    });
  };

  const showToolEnd = (data: ToolEventData) => {
    const failed = data.result?.success === false || data.result?.status === "failed" || Boolean(data.result?.error);
    setMessages((prev) => prev.map((message) =>
      message.role === "tool" && message.toolCallId === data.call_id
        ? { ...message, toolStatus: failed ? "failed" : "success" }
        : message
    ));
  };

  const isStreamingRef = useRef(false);
  const pollPausedUntilRef = useRef(0);
  const welcomeAddedRef = useRef(false);
  const [isNewSession, setIsNewSession] = useState(true);

  const WELCOME_TEXT_ZH = "你好，我是智愈健康助手。你可以描述症状或健康问题、上传检验报告和健康资料，也可以让我查询医学文献、药品安全、药物相互作用及挂号信息。我会优先识别紧急风险，并通过必要的追问提供分诊和下一步建议。回答仅供健康管理参考，不能替代医生诊断。";
  const WELCOME_TEXT_EN = "Hello, I’m the SmartCare health assistant. You can describe symptoms or health concerns, upload reports and health records, or ask me to search medical literature, drug safety, drug interactions, and appointment information. I’ll prioritize urgent-risk screening and ask focused follow-up questions before suggesting triage and next steps. This guidance supports health management and does not replace a clinician’s diagnosis.";
  const WELCOME_TEXT = lang === "en" ? WELCOME_TEXT_EN : WELCOME_TEXT_ZH;

  // 切换知识图谱显示
  const toggleKG = useCallback(() => {
    if (showKG) {
      setShowKG(false);
      return;
    }
    // 将完整对话交给后端知识图谱做实体解析，避免前端硬编码词表漏掉近义词。
    const userTexts = messages
      .filter((m) => m.role === "user" && m.content)
      .map((m) => stripContextTags(m.content))
      .join(" ");
    setKgSymptoms(userTexts.trim() ? [userTexts] : []);
    setKgDiseases([]);
    setShowKG(true);
  }, [showKG, messages]);

  // Create session if needed (for /chat/new)
  useEffect(() => {
    if (initialSessionId !== null) return;
    if (creatingSession) return;
    setCreatingSession(true);
    api.createSession().then(({ session_id }) => {
      setSessionId(session_id);
      // Update URL without navigation so sidebar highlight stays on "新建咨询"
      window.history.replaceState(null, "", `/chat/new`);
    }).catch(() => {
      setCreatingSession(false);
    });
  }, [initialSessionId, creatingSession]);

  // Check LLM config on mount
  useEffect(() => {
    if (llmConfigChecked) return;
    const cached = localStorage.getItem("llm_config_done");
    if (cached === "true") { setLlmConfigChecked(true); setHasLLMConfig(true); return; }
    api.getLLMConfig().then(({ has_config }) => {
      if (has_config) {
        localStorage.setItem("llm_config_done", "true");
        setHasLLMConfig(true);
        setLlmConfigChecked(true);
      } else {
        setShowLLMConfig(true);
        setLlmConfigChecked(true);
      }
    }).catch(() => setLlmConfigChecked(true));
  }, [llmConfigChecked]);

  // Load messages
  useEffect(() => {
    if (!sessionId) return;

    const pending = sessionStorage.getItem(`pending_msg_${sessionId}`);
    if (pending) sessionStorage.removeItem(`pending_msg_${sessionId}`);

    api.getSession(sessionId).then((data) => {
      setSessionStatus(data.status);
      const latestCompleted = [...data.messages].reverse().find((m) => m.role === "assistant" && m.generation_status === "completed" && m.message_id);
      if (latestCompleted?.message_id) localStorage.setItem(`read_message_${latestCompleted.message_id}`, "1");
      if (data.messages.length === 0) {
        setMessages([{ role: "assistant", content: WELCOME_TEXT }]);
        welcomeAddedRef.current = true;
        setIsNewSession(true);
      } else {
        setMessages(data.messages.map((m) => ({
          role: m.role as "user" | "assistant" | "tool",
          content: m.content,
          toolCallId: m.tool_call_id,
          toolName: m.tool_name,
          skillName: m.skill_name,
          toolStatus: m.tool_status as "running" | "success" | "failed" | undefined,
          toolArgs: m.tool_args,
          messageId: m.message_id,
          generationStatus: m.generation_status as Message["generationStatus"],
          isThinking: (m.generation_status === "pending" || m.generation_status === "streaming") && !m.content,
        })));
        welcomeAddedRef.current = false;
        setIsNewSession(false);
      }
      if (data.red_flag_detected) setHasRedFlags(true);

      if (pending) {
        setTimeout(() => sendMessageWithText(pending), 0);
      }
    }).catch(() => {
      setMessages([{ role: "assistant", content: WELCOME_TEXT }]);
      welcomeAddedRef.current = true;
      if (pending) setTimeout(() => sendMessageWithText(pending), 0);
    });

    api.getLatestVitals()
      .then((items) => {
        if (!Array.isArray(items) || items.length === 0) return;
        const latest = items[0];
        if (latest?.risk_level === "high") {
          setLatestVitalHint(
            `${latest.metric}=${latest.value}${latest.unit}（${latest.source}，${latest.measured_at}）`
          );
        }
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  // Update welcome message when language changes (only for new sessions with just the welcome)
  useEffect(() => {
    if (isNewSession && messages.length === 1 && messages[0].role === "assistant") {
      const welcomeText = lang === "en" ? WELCOME_TEXT_EN : WELCOME_TEXT_ZH;
      setMessages([{ role: "assistant", content: welcomeText }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang]);

  // Polling sync
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    const poll = async () => {
      // SSE is authoritative while a response is streaming. Avoid redundant
      // session/vitals polling and the associated database load.
      if (isStreamingRef.current) return;
      const now = Date.now();
      const pollPaused = now < pollPausedUntilRef.current;

      try {
        const fresh = await api.getSession(sessionId);
        if (cancelled) return;
        setSessionStatus(fresh.status);
        if (fresh.red_flag_detected) setHasRedFlags(true);
        if (fresh.status === "HUMAN_HANDOFF_PENDING") {
          // Check message content to distinguish IoT vs text-based risk
          const lastMsg = fresh.messages[fresh.messages.length - 1]?.content || "";
          if (lastMsg.includes("穿戴设备") || lastMsg.includes("高风险生命体征") || lastMsg.includes("自动触发")) {
            setIotHandoffDetected(true);
          } else {
            setTextRiskDetected(true);
          }
        }

        if (!isStreamingRef.current && !pollPaused) {
          const serverMsgs: Message[] = fresh.messages.map((m) => ({
            role: m.role as "user" | "assistant" | "tool",
            content: m.content,
            toolCallId: m.tool_call_id,
            toolName: m.tool_name,
            skillName: m.skill_name,
            toolStatus: m.tool_status as Message["toolStatus"],
            toolArgs: m.tool_args,
            messageId: m.message_id,
            generationStatus: m.generation_status as Message["generationStatus"],
            isThinking: (m.generation_status === "pending" || m.generation_status === "streaming") && !m.content,
          }));
          setMessages((prev) => {
            if (serverMsgs.length === 0) return prev;
            const withoutThinking = prev.filter((p) => !p.isThinking);
            const localNonWelcome = welcomeAddedRef.current
              ? withoutThinking.filter((p) => p.content !== WELCOME_TEXT_ZH && p.content !== WELCOME_TEXT_EN)
              : withoutThinking;
            if (serverMsgs.length < localNonWelcome.length) return prev;
            const same =
              localNonWelcome.length === serverMsgs.length &&
              localNonWelcome.every(
                (p, i) => p.role === serverMsgs[i]?.role
                  && p.content === serverMsgs[i]?.content
                  && p.generationStatus === serverMsgs[i]?.generationStatus
                  && p.toolStatus === serverMsgs[i]?.toolStatus
              );
            if (same) return prev;
            const currentWelcome = lang === "en" ? WELCOME_TEXT_EN : WELCOME_TEXT_ZH;
            const result = welcomeAddedRef.current
              ? [{ role: "assistant" as const, content: currentWelcome }, ...serverMsgs]
              : serverMsgs;
            return result;
          });
        }
      } catch {
        // ignore
      }

      try {
        const items = await api.getLatestVitals();
        if (cancelled || !Array.isArray(items) || items.length === 0) return;
        const latest = items[0] as {
          metric?: string;
          value?: number;
          unit?: string;
          source?: string;
          measured_at?: string;
          risk_level?: string;
        };
        const rl = latest?.risk_level;
        if (rl === "high") {
          setLiveRiskLevel("high");
          setLatestVitalHint(
            `${latest.metric}=${latest.value}${latest.unit}（${latest.source ?? "device"}，${latest.measured_at ?? ""}）`
          );
        } else if (rl === "medium") {
          setLiveRiskLevel("medium");
          setLatestVitalHint(
            `${latest.metric}=${latest.value}${latest.unit}（${latest.source ?? "device"}，${latest.measured_at ?? ""}）`
          );
        } else {
          setLiveRiskLevel("normal");
          setLatestVitalHint("");
        }
      } catch {
        // ignore
      }
    };

    const id = setInterval(() => void poll(), 2500);
    void poll();
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 语音识别 - 使用 Web Speech API 实现实时转写
  const lastTranscriptRef = useRef("");

  const toggleVoiceRecording = useCallback(() => {
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) {
      setVoiceError(lang === "en" ? "Speech recognition is not supported in this browser" : "当前浏览器不支持语音识别");
      return;
    }

    if (isRecording) {
      // 停止录音 - 先保留当前输入内容
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        recognitionRef.current = null;
      }
      setIsRecording(false);
      return;
    }

    // 开始录音
    setVoiceError(null);
    inputBeforeRecordingRef.current = input;
    lastTranscriptRef.current = "";

    const recognition = new SpeechRecognitionAPI();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = lang === "en" ? "en-US" : "zh-CN";

    recognition.onstart = () => {
      setIsRecording(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = "";
      let interimTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      // 累积已确认的转写文本
      if (finalTranscript) {
        lastTranscriptRef.current += finalTranscript;
      }

      // 实时更新输入框：保留录音前的文本 + 已确认的转写 + 临时转写
      const baseText = inputBeforeRecordingRef.current;
      const currentTranscript = lastTranscriptRef.current + interimTranscript;
      const newInput = baseText
        ? `${baseText}${currentTranscript}`
        : currentTranscript;
      setInput(newInput);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.error("Speech recognition error:", event.error);
      if (event.error === "not-allowed") {
        setVoiceError(lang === "en" ? "Microphone access denied" : "麦克风访问被拒绝，请检查浏览器权限");
      } else if (event.error !== "aborted") {
        setVoiceError(lang === "en" ? "Voice recognition error" : "语音识别出错，请重试");
      }
      // 出错时也要保留已识别的内容
      setIsRecording(false);
    };

    recognition.onend = () => {
      // 结束时确保保留所有已识别的内容
      setIsRecording(false);
    };

    try {
      recognition.start();
      recognitionRef.current = recognition;
    } catch {
      setVoiceError(lang === "en" ? "Failed to start voice recognition" : "启动语音识别失败");
      setIsRecording(false);
    }
  }, [isRecording, input, lang]);

  // 组件卸载时停止语音识别
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        recognitionRef.current = null;
      }
    };
  }, []);

  // Send multimodal message (text + images) to LLM
  const sendMessageWithContent = async (content: Array<{ type: string; text?: string; image_url?: { url: string } }>, imageDataUrls?: string[]) => {
    if (!sessionId || isStreaming) return;

    // Extract text for display in chat bubble (without OCR text for images)
    let displayText = content.find((p) => p.type === "text")?.text || "";
    // Clean up display text - remove OCR text references for cleaner UI
    displayText = displayText.replace(/图片中识别到的文字内容：[\s\S]*?(?=\n\n|\n\[|$)/g, "").trim();

    setMessages((prev) => [
      ...prev,
      { role: "user", content: displayText, images: imageDataUrls },
      { role: "assistant", content: "", isThinking: true },
    ]);
    setIsStreaming(true);

    let displayContent = "";
    let doneEventData: Record<string, unknown> | null = null;
    let streamError: string | null = null;

    try {
      const reader = await api.sendMessageStream(sessionId, content, lang, undefined, crypto.randomUUID());
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const rawData = line.slice(6);
            try {
              const data = JSON.parse(rawData);

              if (currentEvent === "token") {
                displayContent += data.content || "";
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = { role: "assistant", content: displayContent, isThinking: false };
                  return updated;
                });
              } else if (currentEvent === "tool_start") {
                showToolStart(data as ToolEventData);
              } else if (currentEvent === "tool_end") {
                showToolEnd(data as ToolEventData);
              } else if (currentEvent === "done") {
                doneEventData = data;
              } else if (currentEvent === "error") {
                streamError = data.message || "未知错误";
              } else if (currentEvent === "incomplete") {
                streamError = data.message || "回答超出输出上限，内容不完整";
              }
            } catch {
              // Ignore parse errors
            }
          }
        }
      }

      if (streamError) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: `错误：${streamError}`, isThinking: false };
          return updated;
        });
      } else if (doneEventData) {
        const finalContent = (doneEventData.assistant_message as string) || displayContent;
        const completedMessageId = doneEventData.message_id as string;
        if (completedMessageId) localStorage.setItem(`read_message_${completedMessageId}`, "1");
        const contentToShow = finalContent.trim();
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: contentToShow, isThinking: false, messageId: completedMessageId, generationStatus: "completed" };
          return updated;
        });
      } else if (displayContent) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: displayContent, isThinking: false };
          return updated;
        });
      } else {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: "AI 响应意外中断，请重试本条消息。", isThinking: false };
          return updated;
        });
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "发送失败";
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: `错误：${errorMsg}`, isThinking: false };
        return updated;
      });
    } finally {
      setIsStreaming(false);
      onMessageSent?.();
      if (sessionId) {
        try {
          const data = await api.getSession(sessionId);
          setSessionStatus(data.status);
        } catch {
          // Ignore
        }
      }
    }
  };

  const sendMessageWithText = async (userMessage: string) => {
    if (!sessionId || isStreaming) return;
    setMessages((prev) => [
      ...prev,
      { role: "user", content: userMessage },
      { role: "assistant", content: "", isThinking: true },
    ]);
    setIsStreaming(true);

    let displayContent = "";
    let doneEventData: Record<string, unknown> | null = null;
    let streamError: string | null = null;

    try {
      const reader = await api.sendMessageStream(sessionId, userMessage, lang, undefined, crypto.randomUUID());
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const rawData = line.slice(6);
            try {
              const data = JSON.parse(rawData);

              if (currentEvent === "token") {
                displayContent += data.content || "";
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = { role: "assistant", content: displayContent, isThinking: false };
                  return updated;
                });
              } else if (currentEvent === "tool_start") {
                showToolStart(data as ToolEventData);
              } else if (currentEvent === "tool_end") {
                showToolEnd(data as ToolEventData);
              } else if (currentEvent === "done") {
                doneEventData = data;
              } else if (currentEvent === "error") {
                streamError = data.message || "未知错误";
              } else if (currentEvent === "incomplete") {
                streamError = data.message || "回答超出输出上限，内容不完整";
              }
            } catch {
              // ignore non-JSON data
            }
          }
        }
      }

      if (streamError) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: `抱歉，请求出现问题：${streamError}`, isThinking: false };
          return updated;
        });
      } else if (doneEventData) {
        const finalMsg = doneEventData.assistant_message as string;
        const completedMessageId = doneEventData.message_id as string;
        if (completedMessageId) localStorage.setItem(`read_message_${completedMessageId}`, "1");
        if (finalMsg && finalMsg.trim()) {
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: finalMsg, isThinking: false, messageId: completedMessageId, generationStatus: "completed" };
            return updated;
          });
        }
        if (doneEventData.status) setSessionStatus(doneEventData.status as string);
        if (doneEventData.red_flag_detected) setHasRedFlags(true);
        if (
          doneEventData.status === "HUMAN_HANDOFF_PENDING" ||
          (finalMsg && (
            finalMsg.includes("自动触发人工接管") ||
            finalMsg.includes("高风险生命体征")
          ))
        ) {
          if (finalMsg && (finalMsg.includes("穿戴设备") || finalMsg.includes("高风险生命体征") || finalMsg.includes("自动触发"))) {
            setIotHandoffDetected(true);
          } else {
            setTextRiskDetected(true);
          }
        }
      } else if (displayContent) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: displayContent, isThinking: false };
          return updated;
        });
      } else {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: "AI 响应意外中断，请重试本条消息。", isThinking: false };
          return updated;
        });
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "请求失败";
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: msg, isThinking: false };
        return updated;
      });
    } finally {
      setIsStreaming(false);
      onMessageSent?.();
      pollPausedUntilRef.current = Date.now() + 3000;
    }
  };

  const getFileIcon = (filename: string): string => {
    const ext = filename.split(".").pop()?.toLowerCase() ?? "";
    if (["jpg", "jpeg", "png", "webp"].includes(ext)) return "image";
    if (ext === "pdf") return "picture_as_pdf";
    if (["doc", "docx"].includes(ext)) return "description";
    if (["xlsx", "xls"].includes(ext)) return "table_chart";
    return "draft";
  };

  // Read file as base64 data URL for image attachments
  const readFileAsDataUrl = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    for (const file of Array.from(files)) {
      const tempId = crypto.randomUUID();
      const isImage = file.type.startsWith("image/");

      // Read image as base64 for LLM vision analysis
      let imageDataUrl: string | undefined;
      if (isImage) {
        try {
          imageDataUrl = await readFileAsDataUrl(file);
        } catch {
          // Ignore read error, will use OCR fallback
        }
      }

      setAttachments((prev) => [
        ...prev,
        {
          id: tempId,
          filename: file.name,
          url: "",
          size: file.size,
          type: file.type,
          extracted_text: "",
          extraction_status: "empty",
          uploading: true,
          imageDataUrl,
        },
      ]);

      try {
        const result = await api.uploadDocument(file);
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === tempId ? { ...a, ...result, id: tempId, uploading: false, imageDataUrl } : a
          )
        );
      } catch (err) {
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === tempId
              ? { ...a, uploading: false, error: err instanceof Error ? err.message : "上传失败" }
              : a
          )
        );
      }
    }

    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const sendMessage = async () => {
    const hasText = input.trim().length > 0;
    const readyAttachments = attachments.filter((a) => !a.uploading && !a.error);
    if ((!hasText && readyAttachments.length === 0) || isStreaming) return;

    // 自动检测并保存记忆意图
    if (hasText) {
      const memoryKeywords = ["记住", "记一下", "帮我记", "remember"];
      const isMemoryIntent = memoryKeywords.some((kw) => input.trim().startsWith(kw)) && input.trim().length > 4;
      if (isMemoryIntent) {
        const memoryContent = input.trim().replace(/^(记住|记一下|帮我记|remember)\s*[:：]?\s*/i, "").trim();
        if (memoryContent) {
          try {
            await api.createDirectMemory({ text: memoryContent, fact_type: "preference" });
            console.log("Memory saved:", memoryContent);
          } catch (e) {
            console.error("Failed to save memory:", e);
          }
        }
      }
    }

    // 定时科普属于明确命令，创建任务后不再进入普通问诊链路。
    if (hasText && readyAttachments.length === 0) {
      const requestText = input.trim();
      const cadenceKeywords = ["定时", "每天", "每日", "每周", "每月", "工作日"];
      const educationKeywords = ["科普", "健康知识", "医学知识", "推送", "讲讲", "讲解"];
      const isScheduleIntent = cadenceKeywords.some((keyword) => requestText.includes(keyword))
        && educationKeywords.some((keyword) => requestText.includes(keyword))
        && requestText.length > 6;

      if (isScheduleIntent) {
        setInput("");
        if (textareaRef.current) textareaRef.current.style.height = "auto";
        setIsStreaming(true);
        setMessages((prev) => [
          ...prev,
          { role: "user", content: requestText },
          { role: "assistant", content: "", isThinking: true },
        ]);

        try {
          const parsed = await api.parseSchedule(requestText);
          const topic = parsed.topic || "健康科普";
          const task = await api.createScheduledTask({
            title: `${topic}定时科普`,
            topic,
            schedule_cron: parsed.cron,
            schedule_natural: requestText,
            description: parsed.description,
            task_type: "education",
          });
          const nextRun = task.next_run_at
            ? new Date(task.next_run_at).toLocaleString(lang === "en" ? "en-US" : "zh-CN", { hour12: false })
            : t("等待调度器计算", "Pending scheduler calculation");
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              content: `${t("已创建定时科普任务", "Scheduled education task created")}「**${task.title}**」。\n\n- ${parsed.description || parsed.cron}\n- ${t("下次执行", "Next run")}：${nextRun}\n- ${t("可在「知识 → 定时科普」查看、暂停或快速测试。", "Manage, pause, or quick-test it under Knowledge → Scheduled Tasks.")}`,
            };
            return updated;
          });
          onMessageSent?.();
        } catch (error) {
          const message = error instanceof Error ? error.message : t("创建失败，请重试", "Creation failed. Please try again.");
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: `${t("定时科普任务创建失败", "Failed to create scheduled education task")}：${message}` };
            return updated;
          });
        } finally {
          setIsStreaming(false);
        }
        return;
      }
    }

    // Check if we have image attachments that should be sent as multimodal content
    const imageAttachments = readyAttachments.filter((a) => a.imageDataUrl && a.type.startsWith("image/"));
    const hasImages = imageAttachments.length > 0;

    if (hasImages) {
      // Build multimodal content array for LLM vision analysis
      const multimodalParts: Array<{ type: string; text?: string; image_url?: { url: string } }> = [];

      // Add text content
      const textParts: string[] = [];
      if (hasText) textParts.push(input.trim());

      for (const att of readyAttachments) {
        if (att.imageDataUrl && att.type.startsWith("image/")) {
          // Add image to multimodal content for LLM to "see"
          multimodalParts.push({
            type: "image_url",
            image_url: { url: att.imageDataUrl },
          });
          textParts.push(`[已上传图片: ${att.filename}]`);
          // Also include OCR text if available
          if (att.extraction_status === "success" && att.extracted_text.trim()) {
            textParts.push(`图片中识别到的文字内容：${att.extracted_text.trim()}`);
          }
        } else {
          // Non-image attachments: include extracted text only
          textParts.push(att.extraction_status === "success" ? `[已查看附件: ${att.filename}]` : `[已上传文件: ${att.filename}]`);
          if (att.extraction_status === "success" && att.extracted_text.trim()) {
            textParts.push(`[文档上下文: ${att.filename}]\n以下内容来自用户上传的 EHR/文档，仅作为背景资料，不代表用户当前正在陈述这些症状：\n${att.extracted_text.trim()}\n[/文档上下文]`);
            if (att.lab_summary) textParts.push(`化验单结构化摘要：${att.lab_summary}`);
          } else if (att.extraction_status === "empty") {
            textParts.push("提示：文件上传成功，但未提取到可读文本。请手动补充关键信息。");
          } else if (att.extraction_status === "unsupported") {
            textParts.push("提示：该格式当前不支持自动提取文本，请手动补充关键信息。");
          } else if (att.extraction_status === "failed") {
            textParts.push("提示：文件上传成功，但文本提取失败。请手动补充关键信息。");
          }
        }
      }

      // Add text part to multimodal content
      multimodalParts.unshift({ type: "text", text: textParts.join("\n") });

      // Extract image data URLs for display
      const imageDataUrls = imageAttachments.map((a) => a.imageDataUrl!).filter(Boolean);

      setInput("");
      setAttachments([]);
      if (textareaRef.current) textareaRef.current.style.height = "auto";
      await sendMessageWithContent(multimodalParts, imageDataUrls);
    } else {
      // Text-only message (original behavior)
      const parts: string[] = [];
      if (hasText) parts.push(input.trim());

      for (const att of readyAttachments) {
        parts.push(att.extraction_status === "success" ? `[已查看附件: ${att.filename}]` : `[已上传文件: ${att.filename}]`);
        if (att.extraction_status === "success" && att.extracted_text.trim()) {
          parts.push(`[文档上下文: ${att.filename}]\n以下内容来自用户上传的 EHR/文档，仅作为背景资料，不代表用户当前正在陈述这些症状：\n${att.extracted_text.trim()}\n[/文档上下文]`);
          if (att.lab_summary) parts.push(`化验单结构化摘要：${att.lab_summary}`);
        } else if (att.extraction_status === "empty") {
          parts.push("提示：文件上传成功，但未提取到可读文本。请手动补充关键信息。");
        } else if (att.extraction_status === "unsupported") {
          parts.push("提示：该格式当前不支持自动提取文本，请手动补充关键信息。");
        } else if (att.extraction_status === "failed") {
          parts.push("提示：文件上传成功，但文本提取失败。请手动补充关键信息。");
        }
      }

      const userMessage = parts.join("\n");
      setInput("");
      setAttachments([]);
      if (textareaRef.current) textareaRef.current.style.height = "auto";
      await sendMessageWithText(userMessage);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  };

  const [isSummarizing, setIsSummarizing] = useState(false);
  const canSummarize = messages.filter((m) => m.role === "user").length >= 2;

  const goToConclusion = async (userTriggered = false) => {
    if (!sessionId || !userTriggered) return;
    if (isSummarizing || isStreaming) return;
    setIsSummarizing(true);

    setMessages((prev) => [
      ...prev,
      { role: "user", content: "请根据我们的对话生成阶段性结论" },
      { role: "assistant", content: "", isThinking: true },
    ]);

    try {
      const data = await api.sendMessage(sessionId, "请根据我们的对话生成阶段性结论", lang);
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: data.assistant_message, isThinking: false };
        return updated;
      });
      if (data.status) setSessionStatus(data.status);
      // Navigate to conclusion page if summary is ready
      // Also check if assistant_message contains a JSON summary block as fallback
      const hasSummaryJson = data.status === "SUMMARY_READY" ||
        (data.assistant_message && data.assistant_message.includes('"chief_complaint"'));
      if (hasSummaryJson) {
        setTimeout(() => router.push(`/conclusion/${sessionId}`), 1500);
      } else {
        setIsSummarizing(false);
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: "生成结论时出错，请重试。", isThinking: false };
        return updated;
      });
      setIsSummarizing(false);
    }
  };

  // Show loading while creating session
  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex items-center gap-2 text-on-surface-variant/60 text-sm">
          <span className="w-2 h-2 rounded-full bg-on-surface-variant/40 animate-pulse"></span>
          {lang === "en" ? "Creating session..." : "正在创建会话..."}
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex flex-col h-full bg-surface overflow-hidden">
      {/* Header */}
      <div className="px-4 md:px-6 py-3 bg-surface-container-lowest/60 backdrop-blur-sm flex items-center justify-between z-10 shrink-0 border-b border-outline-variant/15">
        <div className="flex items-center gap-3">
          {/* 移动端菜单按钮 */}
          <button
            onClick={openMobile}
            className="p-1.5 rounded-md text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container transition-colors md:hidden"
            title="菜单"
          >
            <span className="material-symbols-outlined text-[20px] leading-none">menu</span>
          </button>
          {showBackButton && (
            <button
              onClick={() => router.push("/chat")}
              className="flex items-center gap-1.5 text-on-surface-variant hover:text-on-surface transition-colors"
            >
              <span className="material-symbols-outlined text-[20px]">arrow_back</span>
              <span className="text-sm font-medium">{lang === "en" ? "Back to list" : "返回列表"}</span>
            </button>
          )}
        </div>
        <div className="flex items-center gap-3">
          {hasRedFlags && (
            <span className="flex items-center gap-1.5 text-error text-xs font-semibold bg-error/10 px-2.5 py-1 rounded-full">
              <span className="material-symbols-outlined text-[14px]">warning</span>
              {lang === "en" ? "Risk Alert" : "风险信号"}
            </span>
          )}
          <span className="flex items-center gap-1.5 text-xs text-on-surface-variant/60">
            <span className="flex h-1.5 w-1.5 rounded-full bg-green-500"></span>
            {lang === "en" ? "System Ready" : "系统就绪"}
          </span>
          <button
            onClick={toggleTheme}
            className="p-1.5 rounded-md text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container transition-colors"
            title={theme === "light" ? (lang === "en" ? "Switch to dark mode" : "切换深色模式") : (lang === "en" ? "Switch to light mode" : "切换浅色模式")}
          >
            <span className="material-symbols-outlined text-[18px] leading-none">{theme === "light" ? "dark_mode" : "light_mode"}</span>
          </button>
          <button
            onClick={toggleLang}
            className="px-2 py-1 rounded-md text-xs font-medium text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container transition-colors"
            title={lang === "zh" ? "Switch to English" : "切换到中文"}
          >
            {lang === "zh" ? "EN" : "中"}
          </button>
        </div>
      </div>

      {/* Risk banners */}
      {liveRiskLevel === "medium" &&
        sessionStatus !== "HUMAN_HANDOFF_PENDING" &&
        !iotHandoffDetected &&
        latestVitalHint && (
          <div className="mx-8 mt-3 rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-amber-950">
            <div className="flex items-start gap-2">
              <span className="material-symbols-outlined text-[18px] text-amber-700">monitor_heart</span>
              <div className="text-sm">
                <p className="font-semibold text-amber-900">{lang === "en" ? "Vital signs elevated (Medium Risk)" : "监测到生命体征偏高（中风险）"}</p>
                <p className="text-xs opacity-90 mt-0.5">{lang === "en" ? "Latest reading:" : "最近上报："}{latestVitalHint}</p>
              </div>
            </div>
          </div>
        )}

      {/* IoT 高风险接管横幅（仅穿戴设备触发） */}
      {iotHandoffDetected && (
        <div className="mx-8 mt-3 rounded-xl border border-error/30 bg-error/10 px-4 py-3">
          <div className="flex items-start gap-2 text-error">
            <span className="material-symbols-outlined text-[18px]">emergency</span>
            <div className="text-sm">
              <p className="font-semibold">{lang === "en" ? "IoT High-Risk Handoff" : "IoT 高风险接管中"}</p>
              <p className="text-xs opacity-90">
                {lang === "en"
                  ? `System triggered human handoff. Please seek in-person care.${latestVitalHint ? ` Latest risk indicator: ${latestVitalHint}` : ""}`
                  : `系统已触发人工接管，请优先线下就医。${latestVitalHint ? `最近风险指标：${latestVitalHint}` : ""}`}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 文本高风险症状横幅（文本风险检测触发） */}
      {textRiskDetected && !iotHandoffDetected && (
        <div className="mx-8 mt-3 rounded-xl border border-error/30 bg-error/10 px-4 py-3">
          <div className="flex items-start gap-2 text-error">
            <span className="material-symbols-outlined text-[18px]">warning</span>
            <div className="text-sm">
              <p className="font-semibold">{lang === "en" ? "High-Risk Symptoms Detected" : "检测到高风险症状信号"}</p>
              <p className="text-xs opacity-90">
                {lang === "en"
                  ? "Based on your symptoms, immediate medical attention is recommended. Please seek in-person care as soon as possible."
                  : "根据您描述的症状，建议立即就医。请尽快前往线下医疗机构就诊。"}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 高风险症状横幅（问诊Agent检测触发） */}
      {hasRedFlags && (sessionStatus === "RISK_ESCALATED" || sessionStatus === "HUMAN_HANDOFF_PENDING") && !iotHandoffDetected && !textRiskDetected && (
        <div className="mx-8 mt-3 rounded-xl border border-error/30 bg-error/10 px-4 py-3">
          <div className="flex items-start gap-2 text-error">
            <span className="material-symbols-outlined text-[18px]">warning</span>
            <div className="text-sm">
              <p className="font-semibold">{lang === "en" ? "High-Risk Symptoms Detected" : "检测到高风险症状信号"}</p>
              <p className="text-xs opacity-90">
                {lang === "en"
                  ? "Based on your symptoms, immediate medical attention is recommended. Please seek in-person care as soon as possible."
                  : "根据您描述的症状，建议立即就医。请尽快前往线下医疗机构就诊。"}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 md:px-6 pb-48 pt-4 no-scrollbar">
        <div className="max-w-3xl mx-auto space-y-3">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex items-end gap-2 ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {message.role === "assistant" && (
                <div className="w-7 h-7 rounded-lg bg-surface-container flex items-center justify-center flex-shrink-0 mb-0.5">
                  <span className="material-symbols-outlined text-[16px] text-primary">smart_toy</span>
                </div>
              )}
              <div className={`max-w-[80%] ${message.role === "user" ? "order-first" : ""}`}>
                {message.role === "tool" ? (
                  <div className={`rounded-xl border px-3 py-2 text-xs ${message.toolStatus === "failed" ? "border-error/30 bg-error/10" : "border-primary/25 bg-primary/5"}`}>
                    <div className="flex items-center gap-2">
                      <span className={`material-symbols-outlined text-[17px] ${message.toolStatus === "running" ? "text-primary animate-pulse" : message.toolStatus === "failed" ? "text-error" : "text-green-700"}`}>
                        {message.toolStatus === "running" ? "progress_activity" : message.toolStatus === "failed" ? "error" : "check_circle"}
                      </span>
                      <span className="font-semibold text-on-surface">
                        {message.toolStatus === "running"
                          ? t(`正在调用「${message.skillName}」技能`, `Calling “${message.skillName}” skill`)
                          : message.toolStatus === "failed"
                            ? t(`「${message.skillName}」技能调用失败`, `“${message.skillName}” skill failed`)
                            : t(`「${message.skillName}」技能调用完成`, `“${message.skillName}” skill completed`)}
                      </span>
                    </div>
                    <p className="mt-1 text-on-surface-variant">{t("执行工具", "Tool")}: <code>{message.toolName}</code></p>
                    {message.toolArgs && Object.keys(message.toolArgs).length > 0 && (
                      <details className="mt-1 text-on-surface-variant">
                        <summary className="cursor-pointer select-none">{t("查看调用参数", "View arguments")}</summary>
                        <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-surface-container p-2">{JSON.stringify(message.toolArgs, null, 2)}</pre>
                      </details>
                    )}
                  </div>
                ) : message.isThinking ? (
                  <div className="inline-flex items-center gap-1.5 py-3 px-4 bg-surface-container-lowest rounded-2xl rounded-bl-md border border-outline-variant/15">
                    <span className="w-1.5 h-1.5 rounded-full bg-on-surface-variant/40 animate-bounce [animation-delay:0ms]"></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-on-surface-variant/40 animate-bounce [animation-delay:150ms]"></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-on-surface-variant/40 animate-bounce [animation-delay:300ms]"></span>
                  </div>
                ) : message.role === "user" ? (
                  <div className="space-y-2">
                    {extractViewedAttachments(message.content).length > 0 && (
                      <div className="flex flex-wrap justify-end gap-1.5">
                        {extractViewedAttachments(message.content).map((filename, index) => (
                          <span key={`${filename}-${index}`} className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-xs text-primary">
                            <span className="material-symbols-outlined text-[14px]">verified</span>
                            {filename} · {t("AI 已查看", "Reviewed by AI")}
                          </span>
                        ))}
                      </div>
                    )}
                    {/* 图片缩略图 */}
                    {message.images && message.images.length > 0 && (
                      <div className="flex flex-wrap gap-2 justify-end">
                        {message.images.map((imgUrl, imgIdx) => (
                          <div
                            key={imgIdx}
                            className="relative group cursor-pointer"
                            onClick={() => setPreviewImage(imgUrl)}
                          >
                            <img
                              src={imgUrl}
                              alt={`上传的图片 ${imgIdx + 1}`}
                              className="w-20 h-20 object-cover rounded-lg border-2 border-primary/30 hover:border-primary transition-colors"
                            />
                            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 rounded-lg transition-colors flex items-center justify-center">
                              <span className="material-symbols-outlined text-white opacity-0 group-hover:opacity-100 text-[20px] transition-opacity">zoom_in</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {/* 文本内容 */}
                    {stripContextTags(message.content) && (
                      <div className="bg-primary text-on-primary px-4 py-2.5 rounded-2xl rounded-br-md text-sm leading-relaxed whitespace-pre-wrap">
                        {stripContextTags(message.content)}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="relative bg-surface-container-lowest text-on-surface px-4 py-3 rounded-2xl rounded-bl-md border border-outline-variant/15 text-sm leading-relaxed chat-markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{message.content}</ReactMarkdown>
                    {(message.generationStatus === "pending" || message.generationStatus === "streaming") && message.content && (
                      <div className="mt-2 flex items-center gap-1.5 text-[11px] text-primary">
                        <span className="material-symbols-outlined animate-spin text-[14px]">progress_activity</span>
                        {t("正在继续生成…", "Continuing generation…")}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />

          {/* 知识图谱 */}
          {showKG && (
            <div className="mt-4">
              <MiniKnowledgeGraph
                symptoms={kgSymptoms}
                diseases={kgDiseases}
              />
            </div>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="absolute bottom-0 left-0 w-full px-3 md:px-6 pb-4 pt-16 bg-gradient-to-t from-surface via-surface/95 to-transparent pointer-events-none">
        <div className="max-w-3xl mx-auto space-y-2 pointer-events-auto">
          {/* 语音识别错误提示 */}
          {voiceError && (
            <div className="bg-error/10 border border-error/20 rounded-xl px-3 py-2 flex items-center gap-2">
              <span className="material-symbols-outlined text-error text-[16px]">error</span>
              <span className="text-xs text-error">{voiceError}</span>
              <button onClick={() => setVoiceError(null)} className="ml-auto p-1 hover:bg-error/10 rounded-full transition-colors">
                <span className="material-symbols-outlined text-error text-[14px]">close</span>
              </button>
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png,.webp,.xlsx,.xls"
            className="hidden"
            onChange={handleFileSelect}
          />

          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 px-1">
              {attachments.map((att) => (
                <div
                  key={att.id}
                  className="relative group"
                >
                  {att.imageDataUrl ? (
                    /* 图片附件：显示缩略图 */
                    <div
                      className="relative w-20 h-20 rounded-lg overflow-hidden border-2 border-primary/30 cursor-pointer hover:border-primary transition-colors"
                      onClick={() => !att.uploading && setPreviewImage(att.imageDataUrl!)}
                    >
                      <img
                        src={att.imageDataUrl}
                        alt={att.filename}
                        className="w-full h-full object-cover"
                      />
                      {att.uploading && (
                        <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                          <span className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        </div>
                      )}
                      {att.error && (
                        <div className="absolute inset-0 bg-error/20 flex items-center justify-center">
                          <span className="material-symbols-outlined text-white text-[20px]">error</span>
                        </div>
                      )}
                      {!att.uploading && !att.error && (
                        <button
                          onClick={(e) => { e.stopPropagation(); removeAttachment(att.id); }}
                          className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/50 hover:bg-black/70 transition-colors flex items-center justify-center"
                        >
                          <span className="material-symbols-outlined text-white text-[14px]">close</span>
                        </button>
                      )}
                    </div>
                  ) : (
                    /* 非图片附件：原来的样式 */
                    <div className="flex items-center gap-1.5 pl-2.5 pr-1 py-1.5 rounded-lg bg-surface-container border border-outline-variant/15 max-w-[220px]">
                      <span className="material-symbols-outlined text-[16px] text-primary flex-shrink-0">
                        {getFileIcon(att.filename)}
                      </span>
                      <span className="truncate text-on-surface text-xs font-medium">
                        {att.filename}
                      </span>
                      {att.uploading && (
                        <span className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin flex-shrink-0" />
                      )}
                      {att.error && (
                        <span className="material-symbols-outlined text-[14px] text-error flex-shrink-0">error</span>
                      )}
                      {!att.uploading && !att.error && (
                        <button
                          onClick={() => removeAttachment(att.id)}
                          className="p-0.5 rounded-full hover:bg-surface-container-highest transition-colors flex-shrink-0"
                        >
                          <span className="material-symbols-outlined text-[14px] text-on-surface-variant">close</span>
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="bg-surface-container-lowest border border-outline-variant/20 rounded-2xl shadow-sm flex items-end">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              className="flex-1 bg-transparent border-none focus:outline-none focus:ring-0 px-4 py-3 text-on-surface placeholder:text-on-surface-variant/50 resize-none text-sm leading-relaxed"
              placeholder={!hasLLMConfig ? (lang === "en" ? "Please configure AI model first..." : "请先配置 AI 模型...") : (lang === "en" ? "Describe your symptoms or answer questions..." : "描述您的症状或回答问题...")}
              rows={1}
              disabled={!hasLLMConfig || isStreaming}
            />
            <div className="flex items-center gap-0.5 px-2 py-2">
              <button
                onClick={() => void goToConclusion(true)}
                disabled={isStreaming || isSummarizing || !canSummarize}
                className="p-1.5 rounded-md text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                title={canSummarize ? (lang === "en" ? "Generate summary" : "生成阶段结论") : (lang === "en" ? "Send at least 2 messages first" : "至少发送2条用户消息后可生成")}
              >
                <span className="material-symbols-outlined text-[18px]">summarize</span>
              </button>
              <button
                onClick={toggleKG}
                className={`p-1.5 rounded-md transition-all ${
                  showKG
                    ? "text-primary bg-primary/10"
                    : "text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container"
                }`}
                title={lang === "en" ? "Knowledge Graph" : "知识图谱"}
              >
                <span className="material-symbols-outlined text-[18px]">account_tree</span>
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="p-1.5 rounded-md text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container transition-all"
              >
                <span className="material-symbols-outlined text-[18px]">attach_file</span>
              </button>
              <button
                onClick={toggleVoiceRecording}
                className={`p-1.5 rounded-md transition-all ${
                  isRecording
                    ? "text-error bg-error/10 animate-pulse"
                    : "text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container"
                }`}
                title={isRecording ? (lang === "en" ? "Stop recording" : "停止录音") : (lang === "en" ? "Start voice input" : "开始语音输入")}
              >
                <span className="material-symbols-outlined text-[18px]">
                  {isRecording ? "stop_circle" : "mic"}
                </span>
              </button>
              <div className="w-px h-5 bg-outline-variant/30 mx-0.5" />
              <button
                onClick={sendMessage}
                disabled={!hasLLMConfig || isStreaming || (!input.trim() && attachments.filter(a => !a.uploading && !a.error).length === 0)}
                className="p-1.5 bg-primary text-on-primary rounded-md hover:opacity-90 active:scale-95 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <span className="material-symbols-outlined text-[18px]">send</span>
              </button>
            </div>
          </div>

          <p className="text-center text-[11px] text-on-surface-variant/30 mt-1">
            {lang === "en" ? "For reference only, not a medical diagnosis" : "仅作健康参考，不替代医疗诊断"}
          </p>
        </div>
      </div>

      {/* 图片预览模态框 */}
      {previewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setPreviewImage(null)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh]">
            <img
              src={previewImage}
              alt="预览图片"
              className="max-w-full max-h-[90vh] object-contain rounded-lg"
              onClick={(e) => e.stopPropagation()}
            />
            <button
              onClick={() => setPreviewImage(null)}
              className="absolute top-3 right-3 w-10 h-10 rounded-full bg-black/50 hover:bg-black/70 text-white transition-colors flex items-center justify-center"
            >
              <span className="material-symbols-outlined text-[28px]">close</span>
            </button>
          </div>
        </div>
      )}

      {/* LLM 配置弹窗 */}
      {showLLMConfig && (
        <LLMConfigModal
          onClose={() => hasLLMConfig && setShowLLMConfig(false)}
          onSaved={() => {
            setShowLLMConfig(false);
            setHasLLMConfig(true);
            localStorage.setItem("llm_config_done", "true");
          }}
          required={!hasLLMConfig}
        />
      )}
    </div>
  );
}
