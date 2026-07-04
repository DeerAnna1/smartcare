"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { getStoredAuth } from "@/lib/auth";
import { useLang } from "@/lib/lang-context";

export default function LandingPage() {
  const router = useRouter();
  const { t } = useLang();
  const features = useMemo(
    () => [
      {
        icon: "clinical_notes",
        title: t("问诊归档全流程", "Consultation to Archive"),
        desc: t(
          "从多轮问诊、风险分诊到事件执行与健康档案归档，形成完整闭环。",
          "A complete loop from consultation and triage to event execution and health record archiving."
        ),
      },
      {
        icon: "monitor_heart",
        title: t("心率模拟", "Heart Rate Simulation"),
        desc: t(
          "模拟生命体征推送，联调风险识别、真人接管与告警链路。",
          "Simulate vital data to validate risk detection, human handoff, and alerts."
        ),
      },
      {
        icon: "account_tree",
        title: t("知识图谱", "Knowledge Graph"),
        desc: t(
          "探索疾病、症状与药物关系，为问诊补充结构化医学知识。",
          "Explore medical relationships and enrich consultations with structured knowledge."
        ),
      },
      {
        icon: "library_books",
        title: t("知识库管理", "Knowledge Base"),
        desc: t(
          "导入并检索医学资料，通过 RAG 为回答提供相关知识依据。",
          "Import and retrieve medical documents to ground answers with RAG."
        ),
      },
      {
        icon: "psychology",
        title: t("长期记忆", "Long-term Memory"),
        desc: t(
          "保存经确认的病史、过敏史与偏好，让后续问诊更连贯。",
          "Retain confirmed history, allergies, and preferences for continuous care."
        ),
      },
      {
        icon: "schedule",
        title: t("定时科普", "Scheduled Education"),
        desc: t(
          "用自然语言创建健康科普计划，支持启停、测试与日志查看。",
          "Create health education schedules in natural language and track each run."
        ),
      },
      {
        icon: "handyman",
        title: t("工具管理", "Tool Management"),
        desc: t(
          "统一管理内置工具、Skill 与 MCP 服务，按需绑定和调用。",
          "Manage built-in tools, Skills, and MCP services in one place."
        ),
      },
    ],
    [t]
  );

  const flow = useMemo(
    () => [
      { icon: "forum", label: t("多轮问诊", "Consult") },
      { icon: "summarize", label: t("阶段结论", "Summarize") },
      { icon: "fact_check", label: t("确认事件", "Confirm") },
      { icon: "task_alt", label: t("执行任务", "Execute") },
      { icon: "folder_managed", label: t("归档记录", "Archive") },
    ],
    [t]
  );

  useEffect(() => {
    const auth = getStoredAuth();
    if (auth?.token) {
      router.replace("/chat/new");
    }
  }, [router]);

  return (
    <div className="min-h-screen bg-surface text-on-surface">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3 md:px-8">
        <div className="flex items-center gap-2.5">
          <span className="material-symbols-outlined text-[22px] text-primary">local_hospital</span>
          <span className="text-base font-semibold tracking-tight text-on-surface">
            {t("智愈", "SmartCare")}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/auth"
            className="text-sm text-on-surface-variant transition-colors hover:text-on-surface"
          >
            {t("登录", "Sign In")}
          </Link>
          <Link
            href="/auth?mode=register"
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-on-primary transition hover:opacity-90"
          >
            {t("免费注册", "Sign Up")}
          </Link>
        </div>
      </header>

      <main>
        <section className="relative mx-auto grid max-w-6xl gap-8 overflow-hidden px-6 py-8 md:grid-cols-[1.35fr_0.65fr] md:items-center md:px-8 md:py-10">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-lowest px-3 py-1.5 text-xs font-medium text-on-surface-variant">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              {t("面向家庭场景的 AI 健康助手", "AI health assistant for families")}
            </div>
            <h1 className="text-4xl font-bold leading-[1.15] tracking-tight text-on-surface md:text-5xl">
              {t("从一次问诊，到持续的", "From one consultation to")}
              <br />
              <span className="text-primary">{t("健康管理闭环", "continuous health management")}</span>
            </h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-on-surface-variant">
              {t(
                "智愈连接智能问诊、任务执行、健康档案与医学知识，让健康信息不止停留在回答，而是转化为清晰、可追踪的下一步。",
                "SmartCare connects consultation, task execution, health records, and medical knowledge—turning answers into clear, trackable next steps."
              )}
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Link
                href="/auth?mode=register"
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-medium text-on-primary transition hover:opacity-90"
              >
                {t("开始问诊", "Start Consultation")}
                <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
              </Link>
              <Link
                href="/auth"
                className="rounded-lg border border-outline-variant/30 px-6 py-3 text-sm font-medium text-on-surface transition hover:bg-surface-container-low"
              >
                {t("已有账号，登录", "Sign in")}
              </Link>
            </div>
          </div>
          <div className="hidden rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-4 shadow-[0_16px_45px_rgba(68,64,60,0.06)] md:block">
            <div className="flex items-center justify-between border-b border-outline-variant/15 pb-4">
              <div>
                <p className="text-xs text-on-surface-variant">{t("双工作区", "Dual workspace")}</p>
                <p className="mt-1 text-sm font-semibold">{t("问诊与执行持续联动", "Consult and act together")}</p>
              </div>
              <span className="material-symbols-outlined rounded-lg bg-primary-container p-2 text-[20px] text-on-primary-container">hub</span>
            </div>
            <div className="mt-4 space-y-2.5">
              {[
                ["stethoscope", t("智能问诊与风险分诊", "Consultation and triage")],
                ["assignment_turned_in", t("健康任务自动承接", "Actionable health tasks")],
                ["folder_managed", t("档案与记忆持续沉淀", "Records and memory")],
              ].map(([icon, label]) => (
                <div key={icon} className="flex items-center gap-3 rounded-lg bg-surface-container-low px-3 py-2.5">
                  <span className="material-symbols-outlined text-[18px] text-primary">{icon}</span>
                  <span className="text-sm text-on-surface">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-y border-outline-variant/15 bg-surface-container-low/60">
          <div className="mx-auto max-w-6xl px-6 py-5 md:px-8 md:py-6">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                  {t("核心流程", "Core workflow")}
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight md:text-2xl">
                  {t("问诊结果，真正进入健康档案", "Turn consultation results into lasting records")}
                </h2>
              </div>
              <p className="text-xs text-on-surface-variant">{t("完整闭环，可追踪、可管理", "A complete, trackable loop")}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-5">
              {flow.map((step, index) => (
                <div
                  key={step.icon}
                  className="flex items-center gap-3 rounded-xl border border-outline-variant/15 bg-surface-container-lowest px-3.5 py-3"
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-container text-on-primary-container">
                    <span className="material-symbols-outlined text-[18px]">{step.icon}</span>
                  </div>
                  <div>
                    <p className="text-[10px] text-on-surface-variant/60">0{index + 1}</p>
                    <p className="text-sm font-medium leading-5 text-on-surface">{step.label}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-6 md:px-8 md:py-7">
          <div className="mb-4 max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
              {t("功能模块", "Capabilities")}
            </p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight md:text-2xl">
              {t("覆盖健康管理的关键环节", "The essentials for connected health management")}
            </h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((feature, index) => (
              <article
                key={feature.icon}
                className={`rounded-xl border border-outline-variant/15 bg-surface-container-lowest p-4 transition hover:-translate-y-0.5 hover:border-outline-variant/35 hover:shadow-[0_10px_28px_rgba(68,64,60,0.06)] ${
                  index === 0 ? "sm:col-span-2" : ""
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-container text-on-primary-container">
                    <span className="material-symbols-outlined text-[20px]">{feature.icon}</span>
                  </div>
                  <h3 className="text-sm font-semibold text-on-surface">{feature.title}</h3>
                </div>
                <p className="mt-3 text-xs leading-5 text-on-surface-variant">{feature.desc}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 pb-6 md:px-8 md:pb-7">
          <div className="flex flex-col items-center justify-between gap-4 rounded-2xl bg-inverse-surface px-6 py-5 text-center text-inverse-on-surface md:flex-row md:px-8 md:text-left">
            <div>
              <h2 className="text-lg font-semibold tracking-tight md:text-xl">
                {t("从现在开始，建立连续的健康记录", "Start building a continuous health record")}
              </h2>
              <p className="mt-1.5 text-sm leading-6 text-inverse-on-surface/70">
                {t("智能问诊、档案、知识与任务管理，一站完成。", "Consultation, records, knowledge, and tasks in one place.")}
              </p>
            </div>
            <Link
              href="/auth?mode=register"
              className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-on-primary transition hover:opacity-90"
            >
              {t("免费开始", "Get Started")}
              <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-outline-variant/15 py-3 text-center text-xs text-on-surface-variant/60">
        <p>{t("智愈 SmartCare · 健康信息辅助，不替代专业诊疗", "SmartCare · Health guidance, not a substitute for medical care")}</p>
      </footer>
    </div>
  );
}
