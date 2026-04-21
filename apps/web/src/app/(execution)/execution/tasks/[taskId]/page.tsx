import Link from "next/link";

interface TaskDetailPageProps {
  params: Promise<{ taskId: string }>;
}

export default async function TaskDetailPage({ params }: TaskDetailPageProps) {
  const { taskId } = await params;

  const task = {
    id: taskId,
    title: "用药提醒：阿莫西林",
    status: "执行中",
    badge: `ID: CP-TASK-8829`,
    dose: "500mg（1片）",
    frequency: "每日 3 次",
    duration: "7 天（第3天）",
    relatedEvent: {
      title: "门诊诊断：急性扁桃体炎",
      description: "由王医师于 2023-10-24 签署。伴随发热、咽痛、咳嗽，建议本次抗生素介入。",
    },
    timeline: [
      {
        type: "upcoming",
        label: "下次提醒",
        time: "18:00（晚餐后）",
        countdown: "03:45:12",
        note: "预计送达方式：APP 推送 + 智能音箱语音提醒",
      },
      {
        type: "today",
        label: "今日记录",
        records: [
          { time: "12:30", note: "患者已确认服药（APP 反馈）", done: true },
          { time: "08:15", note: "患者已确认服药（Agent 电话回访确认）", done: true },
        ],
      },
      {
        type: "yesterday",
        label: "昨日记录 (10-25)",
        compliance: "100% 依从",
      },
    ],
    docs: [
      { name: "阿莫西林胶囊使用说明书.pdf", type: "pdf", date: "2023-01-12", size: "2.4 MB" },
      { name: "抗生素合理使用指南（2023版）", type: "html", date: "在线文档", size: "HTML" },
    ],
    agentLogic: [
      `从医师医嘱中解析出"阿莫西林 500mg"`,
      "匹配本地药房库存，确认可配药",
      "用药周期设定为 7 天，当前第 3 天",
    ],
  };

  return (
    <div className="p-8">
      {/* 面包屑 + 操作 */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2 text-sm">
          <Link href="/execution" className="text-on-surface-variant hover:text-primary transition-colors">
            常规执行
          </Link>
          <span className="text-on-surface-variant">/</span>
          <span className="text-on-surface font-semibold">任务详情</span>
        </div>
        <div className="flex gap-3">
          <button className="px-4 py-2 bg-surface-container text-on-surface rounded-xl text-sm font-medium hover:bg-surface-container-high transition-all flex items-center gap-2">
            <span className="material-symbols-outlined text-[16px]">pause</span>
            暂停执行
          </button>
          <button className="px-4 py-2 bg-primary text-on-primary rounded-xl text-sm font-semibold hover:opacity-90 transition-all flex items-center gap-2">
            <span className="material-symbols-outlined text-[16px]">notifications</span>
            立即提醒
          </button>
        </div>
      </div>

      {/* 头部 */}
      <div className="grid grid-cols-12 gap-6 mb-6">
        <div className="col-span-8 bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
          <div className="flex items-center gap-3 mb-3">
            <span className="px-3 py-1 bg-secondary-container/40 text-secondary rounded-full text-[0.6875rem] font-bold">执行中</span>
            <span className="text-xs text-on-surface-variant">{task.badge}</span>
          </div>
          <h1 className="font-headline font-bold text-2xl text-on-surface mb-4">{task.title}</h1>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-on-surface-variant">单次剂量</p>
              <p className="font-headline font-bold text-xl text-on-surface mt-1">{task.dose}</p>
            </div>
            <div>
              <p className="text-xs text-on-surface-variant">服药次数</p>
              <p className="font-headline font-bold text-xl text-on-surface mt-1">{task.frequency}</p>
            </div>
            <div>
              <p className="text-xs text-on-surface-variant">用药周期</p>
              <p className="font-headline font-bold text-xl text-on-surface mt-1">{task.duration}</p>
            </div>
          </div>
        </div>
        <div className="col-span-4 bg-primary-fixed/30 rounded-2xl p-5 border border-primary/10">
          <p className="text-xs font-bold text-primary uppercase tracking-widest mb-2">关联健康事件</p>
          <p className="font-semibold text-on-surface text-sm">{task.relatedEvent.title}</p>
          <p className="text-xs text-on-surface-variant mt-2 leading-relaxed">{task.relatedEvent.description}</p>
          <button className="mt-3 text-xs text-primary font-semibold flex items-center gap-1 hover:underline">
            查看完整诊录 <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* 左侧：时间轴 */}
        <div className="col-span-7 space-y-6">
          <div className="bg-surface-container-lowest rounded-2xl p-6 border border-outline-variant/10 shadow-sm">
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-headline font-bold text-on-surface">执行时间轴</h2>
              <span className="flex h-2 w-2 rounded-full bg-secondary"></span>
            </div>
            <div className="space-y-6">
              {/* 下次提醒 */}
              <div className="relative pl-6">
                <div className="absolute left-0 top-1 h-3 w-3 rounded-full bg-primary border-2 border-on-primary"></div>
                <div className="absolute left-1.5 top-4 h-full w-0.5 bg-outline-variant/30"></div>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-xs font-bold text-primary uppercase tracking-widest">下次提醒</p>
                  <span className="font-mono text-sm font-bold text-primary bg-primary-fixed/30 px-2 py-0.5 rounded">
                    {task.timeline[0].countdown}
                  </span>
                </div>
                <p className="font-semibold text-on-surface">{task.timeline[0].time}</p>
                <p className="text-xs text-on-surface-variant mt-0.5">{task.timeline[0].note}</p>
              </div>
              {/* 今日记录 */}
              <div className="relative pl-6">
                <div className="absolute left-0 top-1 h-3 w-3 rounded-full bg-secondary border-2 border-on-primary"></div>
                <div className="absolute left-1.5 top-4 h-full w-0.5 bg-outline-variant/30"></div>
                <p className="text-xs font-bold text-secondary uppercase tracking-widest mb-2">今日记录</p>
                <div className="space-y-2">
                  {task.timeline[1].records?.map((rec, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <span className="text-xs text-on-surface-variant w-10">{rec.time}</span>
                      <span className="flex-1 text-sm text-on-surface">{rec.note}</span>
                      <span className="text-xs text-secondary font-medium">已脱环</span>
                    </div>
                  ))}
                </div>
              </div>
              {/* 昨日依从性 */}
              <div className="relative pl-6">
                <div className="absolute left-0 top-1 h-3 w-3 rounded-full bg-surface-container-high border-2 border-outline-variant"></div>
                <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-1">昨日记录 (10-25)</p>
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex-1 h-1.5 bg-secondary rounded-full"></div>
                  <span className="text-xs font-semibold text-secondary">100% 依从</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 右侧：参考文档 + Agent 逻辑 */}
        <div className="col-span-5 space-y-4">
          {/* 临床参考文档 */}
          <div className="bg-surface-container-lowest rounded-2xl p-5 border border-outline-variant/10 shadow-sm">
            <p className="font-headline font-bold text-sm text-on-surface mb-3">临床参考文档</p>
            <div className="space-y-2">
              {task.docs.map((doc, i) => (
                <div key={i} className="flex items-center gap-3 p-3 bg-surface-container rounded-xl hover:bg-surface-container-high transition-all cursor-pointer">
                  <span className={`material-symbols-outlined text-[20px] ${doc.type === "pdf" ? "text-error" : "text-primary"}`}>
                    {doc.type === "pdf" ? "picture_as_pdf" : "open_in_new"}
                  </span>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-on-surface leading-tight">{doc.name}</p>
                    <p className="text-xs text-on-surface-variant mt-0.5">{doc.date} · {doc.size}</p>
                  </div>
                  <span className="material-symbols-outlined text-on-surface-variant text-[18px]">download</span>
                </div>
              ))}
            </div>
          </div>

          {/* Agent 自动化逻辑（深色） */}
          <div className="bg-inverse-surface rounded-2xl p-5">
            <p className="font-headline font-bold text-sm text-inverse-on-surface mb-3">Agent 决策逻辑</p>
            <div className="space-y-2">
              {task.agentLogic.map((logic, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-primary-fixed font-bold text-xs mt-0.5">0{i + 1}</span>
                  <p className="text-sm text-inverse-on-surface/90">{logic}</p>
                </div>
              ))}
            </div>
          </div>

          {/* 实时监控Pill */}
          <div className="bg-surface-container-lowest rounded-2xl p-4 border border-outline-variant/10 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-on-surface">实时监控</p>
              <span className="text-xs text-on-surface-variant">居家/静息</span>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-on-surface-variant mb-0.5">用药依从率</p>
                <p className="font-headline font-bold text-2xl text-secondary">94.2%</p>
              </div>
              <button className="px-4 py-2 bg-primary text-on-primary rounded-xl text-xs font-semibold hover:opacity-90 transition-all">
                生成执行报告
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 不良反应提示 */}
      <div className="mt-6 bg-tertiary-fixed/30 border border-tertiary/20 rounded-2xl p-4 flex items-start gap-3">
        <span className="material-symbols-outlined text-tertiary text-[20px]" style={{ fontVariationSettings: "'FILL' 1" }}>info</span>
        <div>
          <p className="text-sm font-semibold text-tertiary">不良反应提示</p>
          <p className="text-xs text-on-surface-variant mt-1 leading-relaxed">
            阿莫西林偶率副作用包括皮疹、恶心。若出现呼吸困难等严重过敏反应，Agent 将立即触发外部求助流程。
          </p>
        </div>
      </div>
    </div>
  );
}
