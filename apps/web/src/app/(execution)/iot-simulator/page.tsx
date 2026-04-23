"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api-client";

type LogItem = {
  ts: string;
  req: Record<string, unknown>;
  res?: unknown;
  err?: string;
};

export default function IotSimulatorPage() {
  const [heartRate, setHeartRate] = useState(70);
  const [intervalSec, setIntervalSec] = useState("5");
  const [sending, setSending] = useState(false);
  const [looping, setLooping] = useState(false);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [latestRisk, setLatestRisk] = useState<string>("-");
  const [latestValue, setLatestValue] = useState<string>("-");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const riskText = useMemo(() => {
    if (heartRate >= 120) return "高风险";
    if (heartRate >= 100) return "中风险";
    return "正常";
  }, [heartRate]);

  const appendLog = (item: LogItem) => {
    setLogs((prev) => [item, ...prev].slice(0, 30));
  };

  const fetchLatestVitals = async () => {
    try {
      const items = await api.getLatestVitals();
      if (!Array.isArray(items) || items.length === 0) return;
      const latest = items[0];
      setLatestRisk(latest?.risk_level ?? "-");
      setLatestValue(`${latest?.metric ?? "heart_rate"}=${latest?.value ?? "-"}${latest?.unit ?? ""}`);
    } catch {
      // ignore
    }
  };

  const sendOnce = async () => {
    if (sending) return;
    setSending(true);
    const payload = {
      source: "heartbeat-web-simulator",
      metric: "heart_rate",
      value: heartRate,
      unit: "bpm",
      measured_at: new Date().toISOString(),
      event_id: `web-${Date.now()}`,
    };

    try {
      const res = await api.simulateVitalPush(payload);
      appendLog({ ts: new Date().toLocaleTimeString(), req: payload, res });
      await fetchLatestVitals();
    } catch (error) {
      const msg = error instanceof Error ? error.message : "推送失败";
      appendLog({ ts: new Date().toLocaleTimeString(), req: payload, err: msg });
      alert(`推送失败：${msg}`);
    } finally {
      setSending(false);
    }
  };

  const toggleLoop = () => {
    if (looping) {
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
      setLooping(false);
      return;
    }

    const sec = Math.max(1, Number.parseInt(intervalSec, 10) || 5);
    timerRef.current = setInterval(() => {
      void sendOnce();
    }, sec * 1000);
    setLooping(true);
  };

  useEffect(() => {
    void fetchLatestVitals();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  return (
    <div className="max-w-5xl mx-auto px-8 py-8 space-y-6">
      <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 p-6">
        <h1 className="text-2xl font-bold text-on-surface">Web 心率模拟器（替代手机 App）</h1>
        <p className="text-sm text-on-surface-variant mt-2">
          直接在浏览器操作，不依赖 Expo/原生打包/ADB。登录同一账号后，点击推送即可让问诊链路实时感知。
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 p-6 space-y-4">
          <h2 className="font-semibold text-on-surface">心率控制</h2>
          <div className="text-4xl font-bold text-error">{heartRate} bpm</div>
          <div className="text-sm text-on-surface">预测风险：<span className="font-semibold">{riskText}</span></div>

          <div className="flex gap-2 flex-wrap">
            <button className="px-4 py-2 rounded-lg bg-surface-container" onClick={() => setHeartRate((v) => Math.max(40, v - 1))}>-1</button>
            <button className="px-4 py-2 rounded-lg bg-surface-container" onClick={() => setHeartRate((v) => Math.min(180, v + 1))}>+1</button>
            <button className="px-4 py-2 rounded-lg bg-surface-container" onClick={() => setHeartRate((v) => Math.max(40, v - 5))}>-5</button>
            <button className="px-4 py-2 rounded-lg bg-surface-container" onClick={() => setHeartRate((v) => Math.min(180, v + 5))}>+5</button>
          </div>

          <div className="flex gap-2 flex-wrap">
            <button className="px-4 py-2 rounded-lg bg-primary-fixed text-primary" onClick={() => setHeartRate(70)}>正常 70</button>
            <button className="px-4 py-2 rounded-lg bg-primary-fixed text-primary" onClick={() => setHeartRate(105)}>中风险 105</button>
            <button className="px-4 py-2 rounded-lg bg-primary-fixed text-primary" onClick={() => setHeartRate(128)}>高风险 128</button>
          </div>

          <div>
            <label className="block text-xs text-on-surface-variant mb-1">连续推送间隔（秒）</label>
            <input
              className="w-full bg-surface-container rounded-lg px-3 py-2"
              value={intervalSec}
              onChange={(e) => setIntervalSec(e.target.value)}
              inputMode="numeric"
            />
          </div>

          <div className="flex gap-3">
            <button
              className="px-4 py-2 rounded-lg bg-primary text-on-primary font-semibold disabled:opacity-50"
              onClick={() => void sendOnce()}
              disabled={sending}
            >
              {sending ? "推送中..." : "单次推送"}
            </button>
            <button
              className="px-4 py-2 rounded-lg bg-secondary text-on-secondary font-semibold"
              onClick={toggleLoop}
            >
              {looping ? "停止连续推送" : "开始连续推送"}
            </button>
          </div>
        </div>

        <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 p-6 space-y-4">
          <h2 className="font-semibold text-on-surface">后端最新感知</h2>
          <div className="text-sm text-on-surface">最近指标：<span className="font-semibold">{latestValue}</span></div>
          <div className="text-sm text-on-surface">最近风险：<span className="font-semibold">{latestRisk}</span></div>
          <button className="px-4 py-2 rounded-lg bg-surface-container" onClick={() => void fetchLatestVitals()}>
            刷新后端状态
          </button>

          <div className="pt-3 border-t border-outline-variant/15">
            <h3 className="font-semibold text-on-surface mb-2">最近日志</h3>
            {logs.length === 0 ? (
              <div className="text-xs text-on-surface-variant">暂无日志</div>
            ) : (
              <div className="space-y-2 max-h-[420px] overflow-auto pr-1">
                {logs.map((item, idx) => (
                  <div key={`${item.ts}-${idx}`} className="text-xs bg-surface-container rounded-lg p-2">
                    <div className="text-on-surface-variant">{item.ts}</div>
                    <div className="break-all">req: {JSON.stringify(item.req)}</div>
                    {item.res ? <div className="break-all">res: {JSON.stringify(item.res)}</div> : null}
                    {item.err ? <div className="text-error break-all">err: {item.err}</div> : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
