"use client";

import { useState, useRef, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import VoiceToText from "@/components/input/VoiceToText";
import FileUpload from "@/components/input/FileUpload";

interface Message {
  role: "user" | "assistant";
  content: string;
  tags?: string[];
  followUpCards?: { title: string; question: string; borderColor: string }[];
  riskAlert?: { title: string; content: string };
  isThinking?: boolean;
}

interface ChatPageProps {
  params: Promise<{ sessionId: string }>;
}

export default function ChatPage({ params }: ChatPageProps) {
  const { sessionId } = use(params);
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [hasRedFlags, setHasRedFlags] = useState(false);
  const [showFileUpload, setShowFileUpload] = useState(false);
  const [showVoiceInput, setShowVoiceInput] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 加载历史消息，并处理从 /chat/new 跳转时携带的第一条待发消息
  useEffect(() => {
    const pending = sessionStorage.getItem(`pending_msg_${sessionId}`);
    if (pending) sessionStorage.removeItem(`pending_msg_${sessionId}`);

    const welcomeMsg: Message = {
      role: "assistant",
      content: "我已启动健康问诊程序。请描述您的主要症状或健康问题，我将通过几个问题帮助您完成问诊评估。",
    };

    api.getSession(sessionId).then((data) => {
      if (data.messages.length === 0) {
        setMessages([welcomeMsg]);
      } else {
        setMessages(data.messages.map((m) => ({ role: m.role as "user" | "assistant", content: m.content })));
      }
      if (data.red_flag_detected) setHasRedFlags(true);

      if (pending) {
        // 等待 React 渲染完欢迎消息后再触发发送
        setTimeout(() => sendMessageWithText(pending), 0);
      }
    }).catch(() => {
      setMessages([welcomeMsg]);
      if (pending) setTimeout(() => sendMessageWithText(pending), 0);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const sendMessageWithText = async (userMessage: string) => {
    if (isStreaming) return;
    setMessages((prev) => [
      ...prev,
      { role: "user", content: userMessage },
      { role: "assistant", content: "", isThinking: true },
    ]);
    setIsStreaming(true);
    try {
      const data = await api.sendMessage(sessionId, userMessage);
      if (data.red_flag_detected) setHasRedFlags(true);
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: data.assistant_message, isThinking: false };
        return updated;
      });
    } catch (error: unknown) {
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
    if (!userTriggered) return;
    if (isSummarizing || isStreaming) return;
    setIsSummarizing(true);

    // 先发触发消息，让 AI 输出结构化结论 JSON
    setMessages((prev) => [
      ...prev,
      { role: "user", content: "请根据我们的对话生成阶段性结论" },
      { role: "assistant", content: "", isThinking: true },
    ]);

    try {
      const data = await api.sendMessage(sessionId, "请根据我们的对话生成阶段性结论");
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: data.assistant_message, isThinking: false };
        return updated;
      });
      // 无论 AI 是否返回 SUMMARY_READY，都跳转结论页
      setTimeout(() => router.push(`/conclusion/${sessionId}`), 1500);
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: "生成结论时出错，请重试。", isThinking: false };
        return updated;
      });
      setIsSummarizing(false);
    }
  };

  return (
    <div className="relative flex flex-col h-full bg-surface overflow-hidden">
      {/* 面包屑 */}
      <div className="px-8 py-4 bg-surface flex items-center justify-between z-10 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/chat")}
            className="flex items-center gap-1 text-on-surface-variant hover:text-on-surface transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">arrow_back</span>
            <span className="text-sm font-medium">返回</span>
          </button>
          <span className="text-on-surface-variant text-sm">/</span>
          <span className="text-on-surface font-semibold text-sm">健康问诊</span>
        </div>
        <div className="flex items-center gap-3">
          {hasRedFlags && (
            <span className="flex items-center gap-1.5 text-error text-xs font-semibold">
              <span className="material-symbols-outlined text-[16px]">warning</span>
              检测到风险信号
            </span>
          )}
          <span className="flex h-2 w-2 rounded-full bg-secondary"></span>
          <span className="text-xs font-medium text-secondary">系统已就绪</span>
        </div>
      </div>

      {/* 聊天区域 */}
      <div className="flex-1 overflow-y-auto px-8 pb-52 space-y-8 max-w-4xl mx-auto w-full pt-4 no-scrollbar">
        {messages.map((message, index) => (
          <div key={index}>
            {message.role === "assistant" ? (
              <div className="flex gap-6 items-start">
                <div className="w-10 h-10 rounded-full bg-primary-fixed flex items-center justify-center shrink-0 border border-primary/10 shadow-sm">
                  <span
                    className="material-symbols-outlined text-primary"
                    style={{ fontVariationSettings: "'FILL' 1" }}
                  >
                    smart_toy
                  </span>
                </div>
                <div className="flex-1 space-y-4">
                  {message.isThinking ? (
                    <div className="flex items-center gap-2 py-4 opacity-70">
                      <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
                      <div className="w-2 h-2 rounded-full bg-primary animate-pulse delay-75"></div>
                      <div className="w-2 h-2 rounded-full bg-primary animate-pulse delay-150"></div>
                      <span className="text-xs font-semibold text-primary ml-2 uppercase tracking-widest">
                        智能体正在分析...
                      </span>
                    </div>
                  ) : (
                    <div className="bg-surface-container-lowest p-6 rounded-2xl rounded-tl-none border border-outline-variant/10 shadow-sm">
                      <p className="font-headline font-bold text-primary text-sm mb-2 uppercase tracking-wide">
                        诊断助手
                      </p>
                      {message.content.includes("\u2705") || message.content.includes("【") ? (
                        <div className="space-y-2">
                          {message.content.split(/(---[\s\S]*?---)/g).map((part, i) => {
                            const isSkillBlock = /^---[\s\S]*?---$/.test(part.trim());
                            if (isSkillBlock) {
                              const inner = part.replace(/^---\s*/m, "").replace(/\s*---$/m, "").trim();
                              return (
                                <div key={i} className="mt-3 bg-secondary-container/30 border border-secondary/20 rounded-xl p-4">
                                  <div className="flex items-center gap-2 mb-2">
                                    <span className="material-symbols-outlined text-secondary text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>bolt</span>
                                    <span className="text-xs font-bold text-secondary uppercase tracking-wide">技能调用结果</span>
                                  </div>
                                  <p className="text-sm text-on-surface leading-relaxed whitespace-pre-wrap">{inner}</p>
                                </div>
                              );
                            }
                            return part.trim() ? (
                              <p key={i} className="text-on-surface leading-relaxed whitespace-pre-wrap">{part.trim()}</p>
                            ) : null;
                          })}
                        </div>
                      ) : (
                        <p className="text-on-surface leading-relaxed whitespace-pre-wrap">
                          {message.content}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex gap-6 items-start flex-row-reverse">
                <div className="w-10 h-10 rounded-full bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline-variant/20 shadow-sm">
                  <span className="material-symbols-outlined text-on-surface-variant">
                    person
                  </span>
                </div>
                <div className="flex-1 flex justify-end">
                  <div className="bg-primary text-on-primary p-6 rounded-2xl rounded-tr-none shadow-lg max-w-[80%]">
                    <p className="leading-relaxed whitespace-pre-wrap">
                      {message.content}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* 底部输入区 */}
      <div className="absolute bottom-0 left-0 w-full p-8 bg-gradient-to-t from-surface via-surface/90 to-transparent">
        <div className="max-w-4xl mx-auto space-y-4">
          {/* 输入框 */}
          {showFileUpload ? (
            <div className="glass-panel border border-outline-variant/20 rounded-2xl p-3 shadow-lg">
              <FileUpload
                onFileUploaded={(result) => {
                  setInput((prev) => {
                    const lines: string[] = [];
                    if (prev.trim()) {
                      lines.push(prev.trim());
                    }

                    lines.push(`[已上传文件: ${result.filename}]`);

                    if (result.extraction_status === "success" && result.extracted_text.trim()) {
                      lines.push("\n以下是上传文档中提取的内容，请结合这些信息继续问诊分析：");
                      lines.push(result.extracted_text.trim());
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
          ) : null}

          {showVoiceInput ? (
            <div className="glass-panel border border-outline-variant/20 rounded-2xl p-3 shadow-lg">
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
          ) : null}

          <div className="glass-panel border border-outline-variant/20 rounded-[1.5rem] p-2 flex items-end gap-2 shadow-2xl">
            <div className="flex-1">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleTextareaChange}
                onKeyDown={handleKeyDown}
                className="w-full bg-transparent border-none focus:outline-none focus:ring-0 px-4 py-4 text-on-surface placeholder:text-on-surface-variant/50 resize-none font-body"
                placeholder="描述您的症状或回答问题..."
                rows={1}
                disabled={isStreaming}
              />
            </div>
            <div className="flex items-center gap-2 pb-2 pr-2">
              <button
                onClick={() => void goToConclusion(true)}
                disabled={isStreaming || isSummarizing || !canSummarize}
                className="px-3 py-2.5 bg-surface-container-high text-on-surface rounded-xl font-medium text-sm flex items-center gap-1.5 hover:bg-surface-container-highest transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                title={canSummarize ? "生成阶段结论" : "至少发送2条用户消息后可生成"}
              >
                <span className="material-symbols-outlined text-[18px]">summarize</span>
                <span className="hidden md:inline">阶段结论</span>
              </button>
              <button
                onClick={() => {
                  setShowFileUpload((prev) => !prev);
                  setShowVoiceInput(false);
                }}
                className={`p-3 rounded-xl transition-all ${showFileUpload ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-primary hover:bg-primary/5"}`}
              >
                <span className="material-symbols-outlined">attach_file</span>
              </button>
              <button
                onClick={() => {
                  setShowVoiceInput((prev) => !prev);
                  setShowFileUpload(false);
                }}
                className={`p-3 rounded-xl transition-all ${showVoiceInput ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-primary hover:bg-primary/5"}`}
              >
                <span className="material-symbols-outlined">mic</span>
              </button>
              <button
                onClick={sendMessage}
                disabled={isStreaming || !input.trim()}
                className="bg-primary text-on-primary p-3 rounded-xl shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <span className="material-symbols-outlined">send</span>
              </button>
            </div>
          </div>

          <div className="flex justify-center gap-6">
            <div className="flex items-center gap-2 text-[0.6875rem] text-on-surface-variant/60 font-medium">
              <span className="material-symbols-outlined text-xs">verified_user</span>
              仅作健康参考，不替代医疗诊断
            </div>
          </div>
        </div>
      </div>

      {/* 快捷参考按钮 */}
      <button className="fixed right-8 bottom-32 w-14 h-14 bg-surface-container-lowest border border-outline-variant/20 rounded-2xl shadow-xl flex items-center justify-center text-primary hover:bg-primary-fixed transition-all z-50">
        <span className="material-symbols-outlined">auto_stories</span>
      </button>
    </div>
  );
}
