"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getStoredAuth } from "@/lib/auth";

const features = [
  {
    icon: "stethoscope",
    title: "智能分诊问诊",
    desc: "多轮对话采集症状，AI 自动分诊、识别风险信号，生成结构化健康事件卡片。",
  },
  {
    icon: "event_available",
    title: "一站式执行工作区",
    desc: "从问诊结论自动派发用药提醒、挂号预约、档案更新等任务，闭环管理。",
  },
  {
    icon: "monitor_heart",
    title: "IoT 生命体征监测",
    desc: "接入穿戴设备实时监测心率等指标，异常数据自动触发风险评估与人工接管。",
  },
  {
    icon: "local_pharmacy",
    title: "药物安全查询",
    desc: "一键查询药物相互作用，避免联合用药风险，获取专业用药建议。",
  },
];

export default function LandingPage() {
  const router = useRouter();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    const auth = getStoredAuth();
    if (auth?.token) {
      setAuthed(true);
      router.replace("/chat/new");
    }
  }, [router]);

  if (authed) return null;

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(238,190,120,0.18),_transparent_45%),linear-gradient(180deg,#fbf7ef_0%,#f4efe5_100%)] text-on-surface">
      {/* ── Header ── */}
      <header className="mx-auto flex max-w-6xl items-center px-6 py-5 md:px-8">
        <div className="flex items-center gap-2.5">
          <span className="material-symbols-outlined text-[28px] text-primary">
            local_hospital
          </span>
          <span className="font-headline text-lg font-bold tracking-tight text-on-surface">
            智愈
          </span>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="mx-auto max-w-6xl px-6 pb-12 pt-16 md:px-8 md:pt-24">
        <div className="grid items-center gap-12 md:grid-cols-[1.15fr_0.85fr]">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.3em] text-primary">
              AI 家庭健康助手
            </p>
            <h1 className="mt-5 font-headline text-4xl font-extrabold leading-tight tracking-tight text-on-surface md:text-[3.25rem] md:leading-[1.15]">
              从问诊到执行
              <br />
              <span className="text-primary">一站式健康管理</span>
            </h1>
            <p className="mt-6 max-w-lg text-base leading-7 text-on-surface-variant md:text-lg">
              智愈是一个 AI 驱动的家庭健康平台。通过多轮智能问诊采集症状、自动分诊评估风险，并将问诊结论转化为可执行的健康任务——用药提醒、挂号预约、档案更新，一站完成。
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <Link
                href="/auth?mode=register"
                className="rounded-2xl bg-primary px-8 py-3.5 text-sm font-semibold text-on-primary shadow-lg shadow-primary/20 transition hover:opacity-90"
              >
                免费注册
              </Link>
              <Link
                href="/auth"
                className="rounded-2xl border border-outline-variant/30 bg-white/60 px-8 py-3.5 text-sm font-semibold text-on-surface transition hover:bg-white/80"
              >
                已有账户？登录
              </Link>
            </div>
          </div>

          {/* Hero visual card */}
          <div className="relative">
            <div className="rounded-[28px] border border-outline-variant/10 bg-white/70 p-6 shadow-[0_24px_80px_rgba(77,57,32,0.10)] backdrop-blur">
              <div className="mb-4 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                  <span className="material-symbols-outlined text-[20px] text-primary">
                    chat
                  </span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-on-surface">
                    健康问诊
                  </p>
                  <p className="text-xs text-on-surface-variant">AI 助手在线</p>
                </div>
              </div>
              <div className="space-y-3">
                <div className="flex justify-end">
                  <div className="max-w-[75%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-on-primary">
                    我最近头疼，还有点发烧，已经两天了。
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="max-w-[80%] rounded-2xl rounded-bl-md bg-surface-container-low px-4 py-2.5 text-sm text-on-surface">
                    了解了。请问头疼的具体位置在哪里？体温大概多少度？有没有伴随恶心或其他不适？
                  </div>
                </div>
                <div className="flex justify-end">
                  <div className="max-w-[75%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-on-primary">
                    整个头都疼，体温 38.2°C，有点乏力。
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="max-w-[80%] rounded-2xl rounded-bl-md bg-surface-container-low px-4 py-2.5 text-sm text-on-surface">
                    根据您的症状，建议先观察休息，多饮水。如果体温持续超过 38.5°C 或出现其他加重信号，建议到内科门诊就诊。
                  </div>
                </div>
              </div>
            </div>
            {/* Decorative glow */}
            <div className="pointer-events-none absolute -right-8 -top-8 h-40 w-40 rounded-full bg-primary/8 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-6 -left-6 h-32 w-32 rounded-full bg-secondary/10 blur-3xl" />
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section className="mx-auto max-w-6xl px-6 py-16 md:px-8 md:py-24">
        <div className="text-center">
          <p className="text-sm font-medium uppercase tracking-[0.3em] text-primary">
            核心能力
          </p>
          <h2 className="mt-4 font-headline text-2xl font-bold tracking-tight text-on-surface md:text-3xl">
            覆盖健康管理全流程
          </h2>
        </div>
        <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => (
            <div
              key={f.icon}
              className="group rounded-[24px] border border-outline-variant/10 bg-white/60 p-6 backdrop-blur transition hover:border-primary/20 hover:shadow-lg hover:shadow-primary/5"
            >
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 transition group-hover:bg-primary/15">
                <span className="material-symbols-outlined text-[24px] text-primary">
                  {f.icon}
                </span>
              </div>
              <h3 className="font-headline text-base font-bold text-on-surface">
                {f.title}
              </h3>
              <p className="mt-2 text-sm leading-6 text-on-surface-variant">
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="mx-auto max-w-6xl px-6 py-16 md:px-8 md:py-24">
        <div className="rounded-[28px] border border-outline-variant/10 bg-white/50 p-8 backdrop-blur md:p-12">
          <h2 className="text-center font-headline text-2xl font-bold tracking-tight text-on-surface md:text-3xl">
            三步完成健康管理
          </h2>
          <div className="mt-12 grid gap-8 md:grid-cols-3">
            {[
              {
                step: "01",
                title: "描述症状",
                desc: "与 AI 助手对话，描述您的健康状况。系统会智能追问，逐步采集完整信息。",
              },
              {
                step: "02",
                title: "获取评估",
                desc: "AI 自动分析症状、评估风险等级、推荐就诊科室，生成结构化健康事件卡片。",
              },
              {
                step: "03",
                title: "执行任务",
                desc: "从事件卡片自动派发用药提醒、挂号预约、档案更新等可执行任务，跟踪完成。",
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 font-headline text-lg font-extrabold text-primary">
                  {item.step}
                </div>
                <h3 className="font-headline text-lg font-bold text-on-surface">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm leading-6 text-on-surface-variant">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="mx-auto max-w-6xl px-6 pb-20 pt-8 md:px-8 md:pb-28">
        <div className="rounded-[28px] bg-[linear-gradient(160deg,rgba(74,107,87,0.96),rgba(42,63,53,0.96))] p-10 text-center text-white md:p-14">
          <h2 className="font-headline text-2xl font-bold tracking-tight md:text-3xl">
            开始管理您的家庭健康
          </h2>
          <p className="mx-auto mt-4 max-w-md text-sm leading-7 text-white/75 md:text-base">
            注册即可免费使用智能问诊、健康档案、任务管理等全部功能。
          </p>
          <Link
            href="/auth?mode=register"
            className="mt-8 inline-block rounded-full bg-white px-10 py-3.5 text-sm font-semibold text-[#2a3f35] shadow-lg transition hover:bg-white/90"
          >
            立即注册
          </Link>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-outline-variant/10 bg-white/30 py-6 text-center text-xs text-on-surface-variant">
        <p>智愈 SmartCare &copy; 2026 &middot; AI 家庭健康助手平台</p>
      </footer>
    </div>
  );
}
