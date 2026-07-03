"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

type LogItem = {
  ts: string;
  req: Record<string, unknown>;
  res?: unknown;
  err?: string;
};

export default function IotSimulatorPage() {
  const { lang } = useLang();
  const t = (zh: string, en: string) => lang === "zh" ? zh : en;
  const [heartRate, setHeartRate] = useState(70);
  const [intervalSec, setIntervalSec] = useState("5");
  const [sending, setSending] = useState(false);
  const [looping, setLooping] = useState(false);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [latestRisk, setLatestRisk] = useState<string>("-");
  const [latestValue, setLatestValue] = useState<string>("-");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const heartRateRef = useRef(heartRate);
  const sendingRef = useRef(sending);

  const riskText = heartRate >= 120
    ? t("高风险", "High Risk")
    : heartRate >= 100
      ? t("中风险", "Medium Risk")
      : t("正常", "Normal");

  const appendLog = (item: LogItem) => {
    setLogs((prev) => [item, ...prev].slice(0, 30));
  };

  // Keep refs in sync with state so setInterval reads current values
  useEffect(() => { heartRateRef.current = heartRate; }, [heartRate]);
  useEffect(() => { sendingRef.current = sending; }, [sending]);

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
    if (sendingRef.current) return;
    setSending(true);
    sendingRef.current = true;
    const payload = {
      source: "heartbeat-web-simulator",
      metric: "heart_rate",
      value: heartRateRef.current,
      unit: "bpm",
      measured_at: new Date().toISOString(),
      event_id: `web-${Date.now()}`,
    };

    try {
      const res = await api.simulateVitalPush(payload);
      appendLog({ ts: new Date().toLocaleTimeString(), req: payload, res });
      await fetchLatestVitals();
    } catch (error) {
      const msg = error instanceof Error ? error.message : t("推送失败", "Push failed");
      appendLog({ ts: new Date().toLocaleTimeString(), req: payload, err: msg });
      alert(`${t("推送失败", "Push failed")}：${msg}`);
    } finally {
      setSending(false);
      sendingRef.current = false;
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
    // Initial synchronization with the backend device state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchLatestVitals();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const riskTone = heartRate >= 120
    ? { text: "text-error", bg: "bg-error-container/50", ring: "ring-error/20", icon: "emergency" }
    : heartRate >= 100
      ? { text: "text-tertiary", bg: "bg-tertiary-container/45", ring: "ring-tertiary/20", icon: "warning" }
      : { text: "text-secondary", bg: "bg-secondary-container/45", ring: "ring-secondary/20", icon: "favorite" };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
      <section className="sr-only">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-error-container text-error"><span className="material-symbols-outlined text-[21px]" style={{ fontVariationSettings: "'FILL' 1" }}>ecg_heart</span></div>
            <div><h1 className="font-headline text-xl font-bold text-on-surface sm:text-2xl">{t("心率模拟中心", "Heart Rate Simulator")}</h1>
            <p className="mt-1 max-w-2xl text-sm text-on-surface-variant">{t("模拟穿戴设备心率数据，验证风险识别与问诊联动。", "Simulate wearable heart-rate data and verify risk detection and consultation integration.")}</p></div>
          </div>
          <div className={`flex items-center gap-2 rounded-xl px-3 py-2 ring-1 ${riskTone.bg} ${riskTone.ring} ${riskTone.text}`}><span className="material-symbols-outlined text-[19px]">{riskTone.icon}</span><div><p className="text-[9px] font-bold uppercase opacity-65">{t("当前预测", "Prediction")}</p><p className="text-sm font-bold">{riskText}</p></div></div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <section className="overflow-hidden rounded-3xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm lg:col-span-7">
          <div className="flex items-center justify-between border-b border-outline-variant/10 p-5 sm:p-6"><div><h2 className="font-headline text-lg font-bold text-on-surface">{t("心率控制台", "Heart Rate Console")}</h2><p className="mt-1 text-xs text-on-surface-variant">40–180 bpm</p></div><span className={`rounded-full px-3 py-1 text-xs font-bold ${riskTone.bg} ${riskTone.text}`}>{riskText}</span></div>
          <div className="space-y-6 p-5 sm:p-6">
            <div className={`rounded-3xl p-6 text-center ring-1 ${riskTone.bg} ${riskTone.ring}`}><span className={`material-symbols-outlined text-4xl ${riskTone.text}`} style={{ fontVariationSettings: "'FILL' 1" }}>favorite</span><div className={`mt-2 font-headline text-6xl font-bold tracking-tight ${riskTone.text}`}>{heartRate}<span className="ml-2 text-lg font-semibold">bpm</span></div><p className="mt-2 text-xs text-on-surface-variant">{t("模拟设备实时读数", "Simulated live device reading")}</p></div>
            <input type="range" min="40" max="180" value={heartRate} onChange={(event) => setHeartRate(Number(event.target.value))} className="w-full accent-primary" aria-label={t("心率数值", "Heart rate value")} />
            <div className="grid grid-cols-4 gap-2">{[[-5, "-5"], [-1, "-1"], [1, "+1"], [5, "+5"]].map(([delta, label]) => <button key={label} onClick={() => setHeartRate((value) => Math.max(40, Math.min(180, value + Number(delta))))} className="rounded-xl bg-surface-container px-3 py-2 text-sm font-bold text-on-surface transition-all hover:bg-surface-container-high">{label}</button>)}</div>
            <div className="grid grid-cols-3 gap-2">{[[70, t("正常", "Normal")], [105, t("中风险", "Medium")], [128, t("高风险", "High")]].map(([value, label]) => <button key={String(value)} onClick={() => setHeartRate(Number(value))} className={`rounded-2xl border px-3 py-3 text-xs font-bold transition-all ${heartRate === value ? "border-primary bg-primary text-on-primary shadow-sm" : "border-outline-variant/15 bg-surface-container-low text-on-surface hover:border-primary/30"}`}><span className="block text-lg">{value}</span>{label}</button>)}</div>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end"><label><span className="mb-1.5 block text-xs font-semibold text-on-surface-variant">{t("连续推送间隔（秒）", "Push interval (sec)")}</span><input className="w-full rounded-xl bg-surface-container px-4 py-2.5 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/30" value={intervalSec} onChange={(event) => setIntervalSec(event.target.value)} inputMode="numeric" /></label><button onClick={() => void sendOnce()} disabled={sending} className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-on-primary disabled:opacity-50"><span className="material-symbols-outlined text-[17px]">send</span>{sending ? t("推送中...", "Pushing...") : t("单次推送", "Push Once")}</button><button onClick={toggleLoop} className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-4 py-2.5 text-sm font-bold ${looping ? "bg-error-container text-error" : "bg-secondary text-on-secondary"}`}><span className="material-symbols-outlined text-[17px]">{looping ? "stop_circle" : "play_circle"}</span>{looping ? t("停止连续推送", "Stop Loop") : t("连续推送", "Start Loop")}</button></div>
          </div>
        </section>

        <section className="flex min-h-[620px] flex-col overflow-hidden rounded-3xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm lg:col-span-5">
          <div className="border-b border-outline-variant/10 p-5 sm:p-6"><div className="flex items-center justify-between"><div><h2 className="font-headline text-lg font-bold text-on-surface">{t("后端感知", "Backend Status")}</h2><p className="mt-1 text-xs text-on-surface-variant">{t("最近接收的设备数据", "Latest received device data")}</p></div><button onClick={() => void fetchLatestVitals()} className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface-container text-on-surface-variant hover:text-primary"><span className="material-symbols-outlined text-[19px]">refresh</span></button></div><div className="mt-4 grid grid-cols-2 gap-3"><div className="rounded-2xl bg-surface-container p-3"><p className="text-[10px] font-bold uppercase text-on-surface-variant">{t("最近指标", "Latest Metric")}</p><p className="mt-1 truncate text-sm font-bold text-on-surface">{latestValue}</p></div><div className="rounded-2xl bg-surface-container p-3"><p className="text-[10px] font-bold uppercase text-on-surface-variant">{t("最近风险", "Latest Risk")}</p><p className="mt-1 truncate text-sm font-bold text-on-surface">{latestRisk}</p></div></div></div>
          <div className="min-h-0 flex-1 p-5 sm:p-6"><div className="mb-3 flex items-center justify-between"><h3 className="font-bold text-on-surface">{t("推送日志", "Push Logs")}</h3><span className="rounded-full bg-surface-container px-2.5 py-1 text-[10px] font-bold text-on-surface-variant">{logs.length}/30</span></div>{logs.length === 0 ? <div className="flex h-[360px] flex-col items-center justify-center text-center"><span className="material-symbols-outlined text-4xl text-on-surface-variant/35">receipt_long</span><p className="mt-3 text-sm font-semibold text-on-surface">{t("暂无推送日志", "No push logs")}</p><p className="mt-1 text-xs text-on-surface-variant">{t("推送数据后将在这里显示结果", "Results appear here after pushing data")}</p></div> : <div className="max-h-[460px] space-y-2 overflow-auto pr-1">{logs.map((item, index) => <div key={`${item.ts}-${index}`} className={`rounded-2xl border p-3 text-xs ${item.err ? "border-error/15 bg-error-container/15" : "border-secondary/15 bg-secondary-container/10"}`}><div className="mb-2 flex items-center justify-between"><span className="font-bold text-on-surface">{item.ts}</span><span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${item.err ? "bg-error-container text-error" : "bg-secondary-container text-secondary"}`}>{item.err ? t("失败", "FAILED") : t("成功", "SUCCESS")}</span></div><div className="break-all font-mono text-[10px] leading-5 text-on-surface-variant">req: {JSON.stringify(item.req)}</div>{item.res ? <div className="break-all font-mono text-[10px] leading-5 text-secondary">res: {JSON.stringify(item.res)}</div> : null}{item.err ? <div className="break-all font-mono text-[10px] leading-5 text-error">err: {item.err}</div> : null}</div>)}</div>}</div>
        </section>
      </div>
    </div>
  );
}
