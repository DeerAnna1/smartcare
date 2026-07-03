"use client";

import { useLang } from "@/lib/lang-context";

interface NodeDetailPanelProps {
  nodeType: string;
  nodeName: string;
  data: Record<string, unknown> | null;
  onClose: () => void;
  onNavigate?: (type: string, name: string) => void;
}

const TYPE_ICONS: Record<string, string> = {
  disease: "local_hospital",
  symptom: "sick",
  drug: "medication",
  food: "restaurant",
  check: "biotech",
  department: "business",
};

export default function NodeDetailPanel({ nodeType, nodeName, data, onClose, onNavigate }: NodeDetailPanelProps) {
  const { t } = useLang();

  const TYPE_LABELS: Record<string, string> = {
    disease: t("疾病", "Disease"),
    symptom: t("症状", "Symptom"),
    drug: t("药物", "Drug"),
    food: t("食物", "Food"),
    check: t("检查", "Check"),
    department: t("科室", "Department"),
  };

  if (!data) return null;

  const isDisease = nodeType === "disease";

  return (
    <div className="h-full flex flex-col bg-surface-container-low border-l border-outline/20">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-outline/20 bg-surface-container">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary">{TYPE_ICONS[nodeType] || "info"}</span>
          <div>
            <span className="text-xs text-on-surface-variant">{TYPE_LABELS[nodeType] || nodeType}</span>
            <h3 className="text-base font-semibold text-on-surface leading-tight">{nodeName}</h3>
          </div>
        </div>
        <button
          onClick={onClose}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-container-high transition-colors"
        >
          <span className="material-symbols-outlined text-lg text-on-surface-variant">close</span>
        </button>
      </div>

      {/* 内容 */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {isDisease ? (
          <DiseaseDetail data={data} onNavigate={onNavigate} />
        ) : (
          <EntityDetail nodeType={nodeName} data={data} onNavigate={onNavigate} />
        )}
      </div>
    </div>
  );
}

function DiseaseDetail({ data, onNavigate }: { data: Record<string, unknown>; onNavigate?: (type: string, name: string) => void }) {
  const { t } = useLang();

  const sections = [
    { label: t("简介", "Description"), value: data.desc as string, icon: "description" },
    { label: t("病因", "Cause"), value: data.cause as string, icon: "biotech" },
    { label: t("预防", "Prevention"), value: data.prevent as string, icon: "health_and_safety" },
  ].filter((s) => s.value);

  const stats = [
    { label: t("治疗周期", "Treatment Duration"), value: data.cure_lasttime as string, icon: "schedule" },
    { label: t("治愈率", "Cure Rate"), value: data.cured_prob as string, icon: "trending_up" },
    { label: t("费用", "Cost"), value: data.cost_money as string, icon: "payments" },
    { label: t("发病率", "Incidence"), value: data.get_prob as string, icon: "analytics" },
    { label: t("传染性", "Contagiousness"), value: data.get_way as string, icon: "warning" },
    { label: t("易感人群", "Susceptible Groups"), value: data.easy_get as string, icon: "groups" },
    { label: t("医保", "Insurance"), value: data.yibao_status as string, icon: "verified" },
  ].filter((s) => s.value);

  const lists = [
    { label: t("典型症状", "Typical Symptoms"), items: data.symptom as string[], type: "symptom" },
    { label: t("推荐药物", "Recommended Drugs"), items: data.recommand_drug as string[], type: "drug" },
    { label: t("建议检查", "Suggested Checks"), items: data.check as string[], type: "check" },
    { label: t("就诊科室", "Department"), items: data.cure_department as string[], type: "department" },
    { label: t("治疗方法", "Treatment"), items: data.cure_way as string[], type: "" },
    { label: t("宜吃", "Recommended Food"), items: data.do_eat as string[], type: "food" },
    { label: t("忌吃", "Avoid Food"), items: data.not_eat as string[], type: "food" },
  ].filter((l) => l.items && l.items.length > 0);

  return (
    <>
      {sections.map((s) => (
        <div key={s.label}>
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className="material-symbols-outlined text-sm text-primary">{s.icon}</span>
            <h4 className="text-sm font-semibold text-on-surface">{s.label}</h4>
          </div>
          <p className="text-sm text-on-surface-variant leading-relaxed whitespace-pre-wrap">{s.value}</p>
        </div>
      ))}

      {stats.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-on-surface mb-2">{t("基本信息", "Basic Info")}</h4>
          <div className="grid grid-cols-2 gap-2">
            {stats.map((s) => (
              <div key={s.label} className="flex items-start gap-1.5 p-2 rounded-lg bg-surface-container">
                <span className="material-symbols-outlined text-xs text-primary mt-0.5">{s.icon}</span>
                <div>
                  <span className="text-[11px] text-on-surface-variant">{s.label}</span>
                  <p className="text-xs font-medium text-on-surface">{s.value}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {lists.map((l) => (
        <div key={l.label}>
          <h4 className="text-sm font-semibold text-on-surface mb-1.5">{l.label}</h4>
          <div className="flex flex-wrap gap-1.5">
            {l.items!.slice(0, 20).map((item) => (
              <button
                key={item}
                onClick={() => l.type && onNavigate?.(l.type, item)}
                className={`px-2 py-0.5 rounded-full text-xs transition-colors ${
                  l.type
                    ? "bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer"
                    : "bg-surface-container-high text-on-surface-variant"
                }`}
              >
                {item}
              </button>
            ))}
            {l.items!.length > 20 && (
              <span className="text-xs text-on-surface-variant">+{l.items!.length - 20}</span>
            )}
          </div>
        </div>
      ))}
    </>
  );
}

function EntityDetail({ nodeType, data, onNavigate }: { nodeType: string; data: Record<string, unknown>; onNavigate?: (type: string, name: string) => void }) {
  const { t } = useLang();
  const relatedDiseases = (data.related_diseases as string[]) || [];
  const relatedCount = (data.related_count as number) || 0;

  return (
    <div>
      <p className="text-sm text-on-surface-variant mb-3">
        {t("关联", "Related to")} <span className="font-semibold text-on-surface">{relatedCount}</span> {t("种疾病", "diseases")}
      </p>
      <h4 className="text-sm font-semibold text-on-surface mb-1.5">{t("关联疾病", "Related Diseases")}</h4>
      <div className="flex flex-wrap gap-1.5">
        {relatedDiseases.slice(0, 30).map((d) => (
          <button
            key={d}
            onClick={() => onNavigate?.("disease", d)}
            className="px-2 py-0.5 rounded-full text-xs bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer transition-colors"
          >
            {d}
          </button>
        ))}
        {relatedDiseases.length > 30 && (
          <span className="text-xs text-on-surface-variant">+{relatedDiseases.length - 30}</span>
        )}
      </div>
    </div>
  );
}
