"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import VoiceToText from "@/components/input/VoiceToText";
import FileUpload from "@/components/input/FileUpload";
import { useLang } from "@/lib/lang-context";
import { useTheme } from "@/lib/theme-context";

interface Message {
  role: "user" | "assistant";
  content: string;
  tags?: string[];
  followUpCards?: { title: string; question: string; borderColor: string }[];
  riskAlert?: { title: string; content: string };
  isThinking?: boolean;
}

interface ChatPanelProps {
  sessionId: string | null;
  showBackButton?: boolean;
}

export default function ChatPanel({ sessionId: initialSessionId, showBackButton = true }: ChatPanelProps) {
  const router = useRouter();
  const { lang, toggleLang } = useLang();
  const { theme, toggleTheme } = useTheme();
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);
  const [creatingSession, setCreatingSession] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [hasRedFlags, setHasRedFlags] = useState(false);
  const [showFileUpload, setShowFileUpload] = useState(false);
  const [showVoiceInput, setShowVoiceInput] = useState(false);
  const [sessionStatus, setSessionStatus] = useState<string>("");
  const [latestVitalHint, setLatestVitalHint] = useState<string>("");
  const [liveRiskLevel, setLiveRiskLevel] = useState<"normal" | "medium" | "high" | null>(null);
  const [iotHandoffDetected, setIotHandoffDetected] = useState(false);
  const [textRiskDetected, setTextRiskDetected] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isStreamingRef = useRef(false);
  const pollPausedUntilRef = useRef(0);
  const welcomeAddedRef = useRef(false);
  const [isNewSession, setIsNewSession] = useState(true);

  const WELCOME_TEXT_ZH = "我已启动健康问诊程序。请描述您的主要症状或健康问题，我将通过几个问题帮助您完成问诊评估。";
  const WELCOME_TEXT_EN = "Health consultation started. Please describe your main symptoms or health concerns, and I will help you complete a triage assessment through a few questions.";
  const WELCOME_TEXT = lang === "en" ? WELCOME_TEXT_EN : WELCOME_TEXT_ZH;

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

  // Load messages
  useEffect(() => {
    if (!sessionId) return;

    const pending = sessionStorage.getItem(`pending_msg_${sessionId}`);
    if (pending) sessionStorage.removeItem(`pending_msg_${sessionId}`);

    api.getSession(sessionId).then((data) => {
      setSessionStatus(data.status);
      if (data.messages.length === 0) {
        setMessages([{ role: "assistant", content: WELCOME_TEXT }]);
        welcomeAddedRef.current = true;
        setIsNewSession(true);
      } else {
        setMessages(data.messages.map((m) => ({ role: m.role as "user" | "assistant", content: m.content })));
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
          const serverMsgs = fresh.messages.map((m) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
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
                (p, i) => p.role === serverMsgs[i]?.role && p.content === serverMsgs[i]?.content
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

  const sendMessageWithText = async (userMessage: string) => {
    if (!sessionId || isStreaming) return;
    setMessages((prev) => [
      ...prev,
      { role: "user", content: userMessage },
      { role: "assistant", content: "", isThinking: true },
    ]);
    setIsStreaming(true);

    const charQueue: string[] = [];
    let displayContent = "";
    let typewriterTimer: ReturnType<typeof setInterval> | null = null;
    let doneEventData: Record<string, unknown> | null = null;
    let streamError: string | null = null;

    const startTypewriter = () => {
      if (typewriterTimer) return;
      typewriterTimer = setInterval(() => {
        if (charQueue.length > 0) {
          const batch = charQueue.splice(0, 2).join("");
          displayContent += batch;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: displayContent, isThinking: false };
            return updated;
          });
        }
      }, 16);
    };

    const stopTypewriter = (): Promise<void> => {
      return new Promise((resolve) => {
        if (!typewriterTimer) { resolve(); return; }
        clearInterval(typewriterTimer);
        typewriterTimer = null;
        if (charQueue.length > 0) {
          displayContent += charQueue.join("");
          charQueue.length = 0;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: displayContent, isThinking: false };
            return updated;
          });
        }
        requestAnimationFrame(() => resolve());
      });
    };

    try {
      const reader = await api.sendMessageStream(sessionId, userMessage, lang);
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const rawData = line.slice(6);
            try {
              const data = JSON.parse(rawData);

              if (currentEvent === "token") {
                for (const ch of data.content) {
                  charQueue.push(ch);
                }
                startTypewriter();
              } else if (currentEvent === "done") {
                doneEventData = data;
              } else if (currentEvent === "error") {
                streamError = data.message || "未知错误";
              }
            } catch {
              // ignore non-JSON data
            }
          }
        }
      }

      await stopTypewriter();

      if (streamError) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: `抱歉，请求出现问题：${streamError}`, isThinking: false };
          return updated;
        });
      } else if (doneEventData) {
        const finalMsg = doneEventData.assistant_message as string;
        if (finalMsg) {
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: "assistant", content: finalMsg, isThinking: false };
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
      }
    } catch (error: unknown) {
      if (typewriterTimer) { clearInterval(typewriterTimer); typewriterTimer = null; }
      const msg = error instanceof Error && error.message.includes("504")
        ? "AI 响应超时，请稍后重试。"
        : "抱歉，请求出现问题，请重试。";
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: msg, isThinking: false };
        return updated;
      });
    } finally {
      setIsStreaming(false);
      pollPausedUntilRef.current = Date.now() + 3000;
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || isStreaming) return;
    const userMessage = input.trim();
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await sendMessageWithText(userMessage);
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
        <div className="flex items-center gap-2 text-on-surface-variant text-sm">
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
          {lang === "en" ? "Creating session..." : "正在创建会话..."}
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex flex-col h-full bg-surface overflow-hidden">
      {/* Header */}
      <div className="px-8 py-4 bg-surface-container-lowest/80 backdrop-blur-sm flex items-center justify-between z-10 shrink-0 border-b border-outline-variant/20">
        <div className="flex items-center gap-3">
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
          <span className="flex items-center gap-1.5 text-xs text-secondary font-medium">
            <span className="flex h-1.5 w-1.5 rounded-full bg-secondary"></span>
            {lang === "en" ? "System Ready" : "系统就绪"}
          </span>
          <button
            onClick={toggleTheme}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-surface-container-low text-on-surface-variant hover:bg-surface-container transition-colors"
            title={theme === "light" ? (lang === "en" ? "Switch to dark mode" : "切换深色模式") : (lang === "en" ? "Switch to light mode" : "切换浅色模式")}
          >
            <span className="material-symbols-outlined text-[16px] leading-none">{theme === "light" ? "dark_mode" : "light_mode"}</span>
            {theme === "light" ? (lang === "en" ? "Dark" : "深色") : (lang === "en" ? "Light" : "浅色")}
          </button>
          <button
            onClick={toggleLang}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-surface-container-low text-on-surface-variant hover:bg-surface-container transition-colors"
            title={lang === "zh" ? "Switch to English" : "切换到中文"}
          >
            <span className="material-symbols-outlined text-[16px] leading-none">translate</span>
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
      <div className="flex-1 overflow-y-auto px-6 pb-48 pt-4 no-scrollbar">
        <div className="max-w-3xl mx-auto space-y-3">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex items-end gap-2 ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {message.role === "assistant" && (
                <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center flex-shrink-0 mb-0.5">
                  <span className="text-[10px] font-bold text-white" style={{ fontFamily: "Manrope, system-ui" }}>AI</span>
                </div>
              )}
              <div className={`max-w-[80%] ${message.role === "user" ? "order-first" : ""}`}>
                {message.isThinking ? (
                  <div className="inline-flex items-center gap-1.5 py-3 px-4 bg-surface-container-lowest rounded-2xl rounded-bl-md shadow-sm border border-outline-variant/20">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce [animation-delay:0ms]"></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce [animation-delay:150ms]"></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce [animation-delay:300ms]"></span>
                  </div>
                ) : message.role === "user" ? (
                  <div className="bg-primary text-white px-4 py-2.5 rounded-2xl rounded-br-md text-sm leading-relaxed whitespace-pre-wrap shadow-sm">
                    {message.content}
                  </div>
                ) : (
                  <div className="bg-surface-container-lowest text-on-surface px-4 py-3 rounded-2xl rounded-bl-md shadow-sm border border-outline-variant/20 text-sm leading-relaxed">
                    {message.content.includes("✅") || message.content.includes("【") ? (
                      <div className="space-y-2">
                        {message.content.split(/(---[\s\S]*?---)/g).map((part, i) => {
                          const isSkillBlock = /^---[\s\S]*?---$/.test(part.trim());
                          if (isSkillBlock) {
                            const inner = part.replace(/^---\s*/m, "").replace(/\s*---$/m, "").trim();
                            return (
                              <div key={i} className="mt-2 bg-secondary-container/30 border border-secondary/20 rounded-xl p-3">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="material-symbols-outlined text-secondary text-[16px]" style={{ fontVariationSettings: "'FILL' 1" }}>bolt</span>
                                  <span className="text-xs font-bold text-secondary uppercase tracking-wide">{lang === "en" ? "Skill Result" : "技能调用结果"}</span>
                                </div>
                                <p className="text-sm text-on-surface leading-relaxed whitespace-pre-wrap">{inner}</p>
                              </div>
                            );
                          }
                          return part.trim() ? (
                            <p key={i} className="whitespace-pre-wrap">{part.trim()}</p>
                          ) : null;
                        })}
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      <div className="absolute bottom-0 left-0 w-full px-6 pb-6 pt-12 bg-gradient-to-t from-surface via-surface to-surface/0 pointer-events-none">
        <div className="max-w-3xl mx-auto space-y-3 pointer-events-auto">
          {showFileUpload && (
            <div className="bg-surface-container-lowest border border-outline-variant/20 rounded-2xl p-3 shadow-lg">
              <FileUpload
                onFileUploaded={(result) => {
                  setInput((prev) => {
                    const lines: string[] = [];
                    if (prev.trim()) lines.push(prev.trim());
                    lines.push(`[已上传文件: ${result.filename}]`);
                    if (result.extraction_status === "success" && result.extracted_text.trim()) {
                      lines.push("\n以下是上传文档中提取的内容，请结合这些信息继续问诊分析：");
                      lines.push(result.extracted_text.trim());
                      if (result.lab_summary) lines.push(`\n化验单结构化摘要：${result.lab_summary}`);
                    } else if (result.extraction_status === "empty") {
                      lines.push("\n提示：文件上传成功，但未提取到可读文本。请手动补充关键信息。");
                    } else if (result.extraction_status === "unsupported") {
                      lines.push("\n提示：该格式当前不支持自动提取文本（如 .doc），请手动补充关键信息。");
                    } else if (result.extraction_status === "failed") {
                      lines.push("\n提示：文件上传成功，但文本提取失败。请手动补充关键信息。");
                    }
                    return lines.join("\n").trim();
                  });
                  setShowFileUpload(false);
                  if (textareaRef.current) {
                    textareaRef.current.style.height = "auto";
                    textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + "px";
                  }
                }}
                onError={(message) => alert(message)}
              />
            </div>
          )}

          {showVoiceInput && (
            <div className="bg-surface-container-lowest border border-outline-variant/20 rounded-2xl p-3 shadow-lg">
              <VoiceToText
                onTextReceived={(text) => {
                  setInput((prev) => (prev ? `${prev}\n${text}` : text));
                  setShowVoiceInput(false);
                  if (textareaRef.current) {
                    textareaRef.current.style.height = "auto";
                    textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + "px";
                  }
                }}
              />
            </div>
          )}

          <div className="bg-surface-container-lowest border border-outline-variant/20 rounded-2xl shadow-lg flex items-end">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              className="flex-1 bg-transparent border-none focus:outline-none focus:ring-0 px-4 py-3.5 text-on-surface placeholder:text-on-surface-variant/40 resize-none text-sm"
              placeholder={lang === "en" ? "Describe your symptoms or answer questions..." : "描述您的症状或回答问题..."}
              rows={1}
              disabled={isStreaming}
            />
            <div className="flex items-center gap-1 px-2 pb-2.5">
              <button
                onClick={() => void goToConclusion(true)}
                disabled={isStreaming || isSummarizing || !canSummarize}
                className="p-2 rounded-lg text-on-surface-variant hover:text-primary hover:bg-primary/5 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                title={canSummarize ? (lang === "en" ? "Generate summary" : "生成阶段结论") : (lang === "en" ? "Send at least 2 messages first" : "至少发送2条用户消息后可生成")}
              >
                <span className="material-symbols-outlined text-[20px]">summarize</span>
              </button>
              <button
                onClick={() => { setShowFileUpload((p) => !p); setShowVoiceInput(false); }}
                className={`p-2 rounded-lg transition-all ${showFileUpload ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-primary hover:bg-primary/5"}`}
              >
                <span className="material-symbols-outlined text-[20px]">attach_file</span>
              </button>
              <button
                onClick={() => { setShowVoiceInput((p) => !p); setShowFileUpload(false); }}
                className={`p-2 rounded-lg transition-all ${showVoiceInput ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-primary hover:bg-primary/5"}`}
              >
                <span className="material-symbols-outlined text-[20px]">mic</span>
              </button>
              <button
                onClick={sendMessage}
                disabled={isStreaming || !input.trim()}
                className="p-2 bg-primary text-white rounded-lg hover:bg-primary/90 active:scale-95 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <span className="material-symbols-outlined text-[20px]">send</span>
              </button>
            </div>
          </div>

          <p className="text-center text-[11px] text-on-surface-variant/40">
            {lang === "en" ? "For reference only, not a medical diagnosis" : "仅作健康参考，不替代医疗诊断"}
          </p>
        </div>
      </div>
    </div>
  );
}
