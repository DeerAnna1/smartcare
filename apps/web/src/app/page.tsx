"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { getStoredAuth } from "@/lib/auth";
import { useLang } from "@/lib/lang-context";

export default function LandingPage() {
  const router = useRouter();
  const { t } = useLang();
  const [authed, setAuthed] = useState(false);

  const features = useMemo(
    () => [
      {
        icon: "stethoscope",
        title: t("智能分诊问诊", "Smart Triage Consultation"),
        desc: t(
          "多轮对话采集症状，AI 自动分诊、识别风险信号，生成结构化健康事件卡片。",
          "Multi-turn dialogue to collect symptoms, AI auto-triage, risk signal detection, and structured health event cards."
        ),
      },
      {
        icon: "event_available",
        title: t("一站式执行", "One-Stop Execution"),
        desc: t(
          "从问诊结论自动派发用药提醒、挂号预约、档案更新等任务。",
          "Auto-dispatch medication reminders, appointment bookings, record updates and more from consultation conclusions."
        ),
      },
      {
        icon: "monitor_heart",
        title: t("IoT 体征监测", "IoT Vital Monitoring"),
        desc: t(
          "接入穿戴设备实时监测心率等指标，异常数据自动触发风险评估。",
          "Connect wearable devices for real-time heart rate monitoring; abnormal data auto-triggers risk assessment."
        ),
      },
      {
        icon: "local_pharmacy",
        title: t("药物安全查询", "Drug Safety Lookup"),
        desc: t(
          "一键查询药物相互作用，避免联合用药风险，获取专业建议。",
          "One-click drug interaction lookup, avoid combination risks, get professional advice."
        ),
      },
    ],
    [t]
  );

  useEffect(() => {
    const auth = getStoredAuth();
    if (auth?.token) {
      setAuthed(true);
      router.replace("/chat/new");
    }
  }, [router]);

  if (authed) return null;

  return (
    <div className="min-h-screen bg-surface text-on-surface">
      {/* Header */}
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4 md:px-8">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[22px] text-primary">
            local_hospital
          </span>
          <span className="font-semibold text-base text-on-surface tracking-tight">
            {t("智愈", "SmartCare")}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/auth"
            className="text-sm text-on-surface-variant hover:text-on-surface transition-colors"
          >
            {t("登录", "Sign In")}
          </Link>
          <Link
            href="/auth?mode=register"
            className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-on-primary transition hover:opacity-90"
          >
            {t("注册", "Sign Up")}
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-5xl px-6 pt-20 pb-16 md:px-8 md:pt-32 md:pb-24">
        <div className="max-w-2xl">
          <h1 className="text-4xl font-bold leading-tight tracking-tight text-on-surface md:text-5xl">
            {t("AI 驱动的", "AI-Powered")}
            <br />
            <span className="text-primary">
              {t("家庭健康管理平台", "Family Health Management Platform")}
            </span>
          </h1>
          <p className="mt-5 text-base leading-7 text-on-surface-variant md:text-lg">
            {t(
              "通过智能问诊采集症状、自动分诊评估风险，将问诊结论转化为可执行的健康任务——用药提醒、挂号预约、档案更新，一站完成。",
              "Collect symptoms through smart consultations, auto-triage and assess risks, convert consultation results into actionable health tasks — medication reminders, appointment bookings, record updates — all in one place."
            )}
          </p>
          <div className="mt-8 flex items-center gap-4">
            <Link
              href="/auth?mode=register"
              className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-on-primary transition hover:opacity-90"
            >
              {t("开始使用", "Get Started")}
            </Link>
            <Link
              href="/auth"
              className="rounded-lg border border-outline-variant/30 px-6 py-2.5 text-sm font-medium text-on-surface transition hover:bg-surface-container-low"
            >
              {t("登录", "Sign In")}
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-5xl px-6 py-16 md:px-8">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => (
            <div
              key={f.icon}
              className="rounded-xl border border-outline-variant/15 bg-surface-container-lowest p-5 transition hover:border-outline-variant/30"
            >
              <span className="material-symbols-outlined text-[20px] text-primary mb-3 block">
                {f.icon}
              </span>
              <h3 className="text-sm font-semibold text-on-surface">
                {f.title}
              </h3>
              <p className="mt-1.5 text-xs leading-5 text-on-surface-variant">
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Chat Demo */}
      <section className="mx-auto max-w-5xl px-6 py-16 md:px-8">
        <div className="rounded-xl border border-outline-variant/15 bg-surface-container-lowest p-6">
          <div className="mb-4 flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-container">
              <span className="material-symbols-outlined text-[16px] text-primary">smart_toy</span>
            </div>
            <div>
              <p className="text-sm font-medium text-on-surface">{t("健康问诊", "Health Consultation")}</p>
              <p className="text-xs text-on-surface-variant/60">{t("AI 助手在线", "AI Assistant Online")}</p>
            </div>
          </div>
          <div className="space-y-3 max-w-lg">
            <div className="flex justify-end">
              <div className="max-w-[75%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-on-primary">
                {t("我最近头疼，还有点发烧，已经两天了。", "I've had a headache and slight fever for two days.")}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-2xl rounded-bl-md bg-surface-container-low px-4 py-2.5 text-sm text-on-surface">
                {t("了解了。请问头疼的具体位置在哪里？体温大概多少度？", "I see. Where exactly is the headache? What's your approximate temperature?")}
              </div>
            </div>
            <div className="flex justify-end">
              <div className="max-w-[75%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-on-primary">
                {t("整个头都疼，体温 38.2°C，有点乏力。", "My whole head hurts, temperature is 38.2°C, feeling a bit weak.")}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-2xl rounded-bl-md bg-surface-container-low px-4 py-2.5 text-sm text-on-surface">
                {t("根据您的症状，建议先观察休息，多饮水。如果体温持续超过 38.5°C，建议到内科门诊就诊。", "Based on your symptoms, rest and hydrate first. If your temperature stays above 38.5°C, please visit the internal medicine clinic.")}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-5xl px-6 py-16 md:px-8">
        <div className="rounded-xl bg-inverse-surface px-8 py-10 text-center text-inverse-on-surface md:py-12">
          <h2 className="text-xl font-semibold tracking-tight md:text-2xl">
            {t("开始管理您的家庭健康", "Start Managing Your Family's Health")}
          </h2>
          <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-inverse-on-surface/70">
            {t(
              "注册即可免费使用智能问诊、健康档案、任务管理等全部功能。",
              "Sign up to access all features for free: smart consultations, health records, task management, and more."
            )}
          </p>
          <Link
            href="/auth?mode=register"
            className="mt-6 inline-block rounded-lg bg-primary px-8 py-2.5 text-sm font-medium text-on-primary transition hover:opacity-90"
          >
            {t("免费注册", "Sign Up Free")}
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-outline-variant/15 py-6 text-center text-xs text-on-surface-variant/60">
        <p>智愈 SmartCare &copy; 2026</p>
      </footer>
    </div>
  );
}
