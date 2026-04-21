"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import VoiceToText from "@/components/input/VoiceToText";
import FileUpload from "@/components/input/FileUpload";

interface Message {
  role: "user" | "assistant";
  content: string;
  isThinking?: boolean;
}

export default function NewChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "我已启动健康问诊程序。请描述您的主要症状或健康问题，我将通过几个问题帮助您完成问诊评估。",
    },
  ]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [showFileUpload, setShowFileUpload] = useState(false);
  const [showVoiceInput, setShowVoiceInput] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const sendMessage = async () => {
    if (!input.trim() || isStreaming) return;
    const userMessage = input.trim();
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    setIsStreaming(true);

    try {
      // 仅在发送第一条消息时创建会话，避免空会话出现在历史列表
      const { session_id } = await api.createSession();
      // 将第一条消息暂存，由 [sessionId]/page.tsx 接收后发送，避免 router.replace 卸载组件导致消息丢失
      sessionStorage.setItem(`pending_msg_${session_id}`, userMessage);
      // 将 URL 切换到真实会话页（不留 /chat/new 历史记录）
      router.replace(`/chat/${session_id}`);
    } catch {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
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
          <span className="text-on-surface font-semibold text-sm">新建问诊</span>
        </div>
        <div className="flex items-center gap-2">
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
                      <p className="text-on-surface leading-relaxed whitespace-pre-wrap">
                        {message.content}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex gap-6 items-start flex-row-reverse">
                <div className="w-10 h-10 rounded-full bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline-variant/20 shadow-sm">
                  <span className="material-symbols-outlined text-on-surface-variant">person</span>
                </div>
                <div className="flex-1 flex justify-end">
                  <div className="bg-primary text-on-primary p-6 rounded-2xl rounded-tr-none shadow-lg max-w-[80%]">
                    <p className="leading-relaxed whitespace-pre-wrap">{message.content}</p>
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
                disabled
                className="px-3 py-2.5 bg-surface-container-high text-on-surface rounded-xl font-medium text-sm flex items-center gap-1.5 opacity-50 cursor-not-allowed"
                title="发送消息进入会话后可生成阶段结论"
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
                onClick={() => void sendMessage()}
                disabled={isStreaming || !input.trim()}
                className="bg-primary text-on-primary p-3 rounded-xl shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <span className="material-symbols-outlined">send</span>
              </button>
            </div>
          </div>
          <div className="flex justify-center">
            <div className="flex items-center gap-2 text-[0.6875rem] text-on-surface-variant/60 font-medium">
              <span className="material-symbols-outlined text-xs">verified_user</span>
              仅作健康参考，不替代医疗诊断
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
