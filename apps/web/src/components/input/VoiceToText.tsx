"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

interface VoiceToTextProps {
  onTextReceived?: (text: string) => void;
  onStateChange?: (state: "idle" | "recording" | "processing" | "error") => void;
}

export default function VoiceToText({
  onTextReceived,
  onStateChange,
}: VoiceToTextProps) {
  const { t } = useLang();
  const [state, setState] = useState<"idle" | "recording" | "processing" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    return () => {
      cancelAnimationFrame(animFrameRef.current);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, []);

  const drawWaveform = () => {
    const canvas = canvasRef.current;
    const analyser = analyserRef.current;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const style = getComputedStyle(document.documentElement);
    const primary = style.getPropertyValue("--color-primary").trim() || "#b45309";

    const draw = () => {
      animFrameRef.current = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);

      const { width, height } = canvas;
      ctx.clearRect(0, 0, width, height);

      const barCount = 32;
      const barWidth = width / barCount - 2;
      const step = Math.floor(bufferLength / barCount);

      for (let i = 0; i < barCount; i++) {
        const value = dataArray[i * step] / 255;
        const barHeight = Math.max(2, value * height * 0.8);
        const x = i * (barWidth + 2);
        const y = (height - barHeight) / 2;

        ctx.fillStyle = primary;
        ctx.globalAlpha = 0.3 + value * 0.7;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };

    draw();
  };

  // Convert audio blob to WAV format (MiMo ASR only supports wav/mp3/mpeg)
  const convertToWav = async (blob: Blob): Promise<Blob> => {
    const audioContext = new AudioContext();
    const arrayBuffer = await blob.arrayBuffer();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

    const numChannels = audioBuffer.numberOfChannels;
    const sampleRate = audioBuffer.sampleRate;
    const format = 1; // PCM
    const bitsPerSample = 16;

    const bytesPerSample = bitsPerSample / 8;
    const blockAlign = numChannels * bytesPerSample;
    const dataLength = audioBuffer.length * blockAlign;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);

    // WAV header
    const writeString = (offset: number, str: string) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };

    writeString(0, "RIFF");
    view.setUint32(4, 36 + dataLength, true);
    writeString(8, "WAVE");
    writeString(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, format, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * blockAlign, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    writeString(36, "data");
    view.setUint32(40, dataLength, true);

    // Interleave audio channels
    const channels: Float32Array[] = [];
    for (let i = 0; i < numChannels; i++) {
      channels.push(audioBuffer.getChannelData(i));
    }

    let offset = 44;
    for (let i = 0; i < audioBuffer.length; i++) {
      for (let ch = 0; ch < numChannels; ch++) {
        const sample = Math.max(-1, Math.min(1, channels[ch][i]));
        const val = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
        view.setInt16(offset, val, true);
        offset += 2;
      }
    }

    await audioContext.close();
    return new Blob([buffer], { type: "audio/wav" });
  };

  const startRecording = async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      audioContextRef.current = audioContext;
      analyserRef.current = analyser;

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        stream.getTracks().forEach((t) => t.stop());

        setState("processing");
        onStateChange?.("processing");

        try {
          // Convert webm to wav for MiMo ASR compatibility
          const wavBlob = await convertToWav(blob);
          const file = new File([wavBlob], `recording_${Date.now()}.wav`, { type: "audio/wav" });
          const result = await api.uploadAudio(file);
          onTextReceived?.(result.text);
          setState("idle");
          onStateChange?.("idle");
        } catch (err) {
          setError(err instanceof Error ? err.message : t("语音转写失败", "Voice transcription failed"));
          setState("error");
          onStateChange?.("error");
        }
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setState("recording");
      onStateChange?.("recording");
      drawWaveform();
    } catch {
      setError(t("无法访问麦克风，请检查浏览器权限设置", "Cannot access microphone, please check browser permission settings"));
      setState("error");
      onStateChange?.("error");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    cancelAnimationFrame(animFrameRef.current);
  };

  const handleToggle = () => {
    if (state === "recording") {
      stopRecording();
    } else if (state === "idle" || state === "error") {
      startRecording();
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleToggle}
        className={`p-3 rounded-full transition-all ${
          state === "recording"
            ? "bg-error text-on-error"
            : state === "processing"
            ? "bg-primary/60 text-on-primary cursor-wait"
            : "bg-primary text-on-primary hover:opacity-90"
        }`}
        disabled={state === "processing"}
      >
        <span className="material-symbols-outlined">
          {state === "recording" ? "stop" : "mic"}
        </span>
      </button>

      {state === "recording" && (
        <canvas
          ref={canvasRef}
          width={200}
          height={40}
          className="flex-1 h-10"
        />
      )}

      {state !== "recording" && (
        <div className="flex-1">
          <p className="text-sm font-medium text-on-surface">
            {state === "idle" && t("点击麦克风开始录音", "Click microphone to start recording")}
            {state === "processing" && t("正在转写...", "Transcribing...")}
            {state === "error" && (error || t("录音出错，请重试", "Recording error, please retry"))}
          </p>
        </div>
      )}

      {state === "processing" && (
        <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin flex-shrink-0" />
      )}
    </div>
  );
}
