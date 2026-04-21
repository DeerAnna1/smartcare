import Link from "next/link";
import TopNavBar from "@/components/layout/TopNavBar";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-surface">
      <TopNavBar platformName="智愈全程健康助手" showSearch={false} />
      <main className="pt-16">
        <div className="max-w-5xl mx-auto px-8 py-16">
          <div className="text-center mb-16">
            <p className="text-xs font-bold text-primary uppercase tracking-widest mb-4">双工作区 Agent 平台</p>
            <h1 className="font-headline font-bold text-5xl text-on-surface leading-tight mb-4">
              智愈全程<span className="text-primary">健康助手</span>平台
            </h1>
            <p className="text-on-surface-variant text-lg max-w-2xl mx-auto leading-relaxed">
              健康问诊到后续执行的一体化闭环。将一次问诊从对话结论升级为结构化事件加后续执行闭环。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-6 mb-12">
            <Link href="/chat/new" className="group bg-surface-container-lowest rounded-2xl p-8 border border-outline-variant/10 shadow-sm hover:shadow-md transition-all block">
              <div className="w-14 h-14 rounded-2xl bg-primary flex items-center justify-center mb-5">
                <span className="material-symbols-outlined text-on-primary text-[28px]">medical_information</span>
              </div>
              <h2 className="font-headline font-bold text-xl text-on-surface mb-2">健康问诊工作区</h2>
              <p className="text-on-surface-variant text-sm leading-relaxed mb-5">主诉采集、症状结构化、风险识别、阶段性结论输出与分诊建议生成。</p>
              <div className="flex items-center gap-2 text-primary font-semibold text-sm">
                新建咨询 <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
              </div>
            </Link>
            <Link href="/execution" className="group bg-surface-container-lowest rounded-2xl p-8 border border-outline-variant/10 shadow-sm hover:shadow-md transition-all block">
              <div className="w-14 h-14 rounded-2xl bg-secondary flex items-center justify-center mb-5">
                <span className="material-symbols-outlined text-on-secondary text-[28px]">assignment_turned_in</span>
              </div>
              <h2 className="font-headline font-bold text-xl text-on-surface mb-2">通用执行工作区</h2>
              <p className="text-on-surface-variant text-sm leading-relaxed mb-5">承接健康问诊结果，通过内置能力与外部 Skill 包完成提醒、建档与信息整理。</p>
              <div className="flex items-center gap-2 text-secondary font-semibold text-sm">
                进入执行台 <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
              </div>
            </Link>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <Link href="/health-records" className="bg-surface-container rounded-xl p-4 flex items-center gap-3 hover:bg-surface-container-high transition-all">
              <span className="material-symbols-outlined text-tertiary">folder_shared</span>
              <span className="font-medium text-on-surface text-sm">健康档案</span>
            </Link>
            <Link href="/skills" className="bg-surface-container rounded-xl p-4 flex items-center gap-3 hover:bg-surface-container-high transition-all">
              <span className="material-symbols-outlined text-primary">extension</span>
              <span className="font-medium text-on-surface text-sm">技能管理</span>
            </Link>
            <Link href="/records" className="bg-surface-container rounded-xl p-4 flex items-center gap-3 hover:bg-surface-container-high transition-all">
              <span className="material-symbols-outlined text-secondary">history</span>
              <span className="font-medium text-on-surface text-sm">历史会话</span>
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
