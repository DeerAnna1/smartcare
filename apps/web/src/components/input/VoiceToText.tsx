"use client";

import { useEffect, useRef, useState } from "react";

interface VoiceToTextProps {
  onTextReceived?: (text: string) => void;
  onStateChange?: (state: "idle" | "listening" | "processing" | "error") => void;
  placeholder?: string;
}

export default function VoiceToText({
  onTextReceived,
  onStateChange,
  placeholder = "点击麦克风开始录音...",
}: VoiceToTextProps) {
  const [state, setState] = useState<"idle" | "listening" | "processing" | "error">("idle");
  const [transcript, setTranscript] = useState("");
  const recognitionRef = useRef<any>(null);
  const finalTextRef = useRef("");
  const [isSupported, setIsSupported] = useState(false);

  useEffect(() => {
    // Check browser support for Web Speech API
    const win = window as any;
    const SpeechRecognition = win.SpeechRecognition || win.webkitSpeechRecognition;
    if (SpeechRecognition) {
      setIsSupported(true);
      recognitionRef.current = new SpeechRecognition();
      
      recognitionRef.current.continuous = false;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.lang = "zh-CN";

      recognitionRef.current.onstart = () => {
        setState("listening");
        onStateChange?.("listening");
      };

      recognitionRef.current.onresult = (event: any) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const chunkText = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTextRef.current += chunkText;
            setTranscript(finalTextRef.current);
          } else {
            interim += chunkText;
          }
        }
      };

      recognitionRef.current.onerror = (event: any) => {
        setState("error");
        onStateChange?.("error");
        console.error("Speech recognition error:", event.error);
      };

      recognitionRef.current.onend = () => {
        setState("idle");
        onStateChange?.("idle");
        const finalText = finalTextRef.current.trim();
        if (finalText) {
          onTextReceived?.(finalText);
        }
      };
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
    };
  }, [onTextReceived, onStateChange]);

  const handleToggleListening = () => {
    if (!recognitionRef.current) return;

    if (state === "listening") {
      recognitionRef.current.stop();
      setState("processing");
      onStateChange?.("processing");
    } else {
      finalTextRef.current = "";
      setTranscript("");
      recognitionRef.current.start();
    }
  };

  const handleClear = () => {
    finalTextRef.current = "";
    setTranscript("");
    setState("idle");
  };

  if (!isSupported) {
    return (
      <div className="p-4 rounded-xl bg-error-container/20 text-error text-sm">
        Your browser does not support voice input. Please use Chrome, Safari, or Edge.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <button
          onClick={handleToggleListening}
          className={`p-3 rounded-full transition-all ${
            state === "listening"
              ? "bg-error text-on-error animate-pulse"
              : state === "processing"
              ? "bg-primary/60 text-on-primary"
              : "bg-primary text-on-primary hover:opacity-90"
          }`}
        >
          <span className="material-symbols-outlined">{state === "listening" ? "mic" : "mic_none"}</span>
        </button>
        <div className="flex-1">
          <p className="text-sm font-medium text-on-surface">
            {state === "idle" && "点击麦克风开始录音"}
            {state === "listening" && "正在录音... 说话完毕后自动停止"}
            {state === "processing" && "处理中..."}
            {state === "error" && "录音出错，请重试"}
          </p>
        </div>
        {transcript && (
          <button
            onClick={handleClear}
            className="p-2 text-on-surface-variant hover:bg-surface-container rounded-full transition-all"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        )}
      </div>

      {transcript && (
        <div className="rounded-xl bg-surface-container p-3">
          <p className="text-sm text-on-surface">{transcript}</p>
        </div>
      )}
    </div>
  );
}
