"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

interface MemoryFact {
  id: string;
  type: string;
  text: string;
  confidence: number;
}

interface LabReport {
  id: string;
  summary: string;
  created_at: string | null;
}

interface Vital {
  id: string;
  metric: string;
  value: string | number;
  unit: string;
  risk_level: string;
  created_at: string | null;
}

interface PatientContext {
  memory_facts: MemoryFact[];
  latest_report: LabReport | null;
  vitals: Vital[];
}

const RISK_COLORS: Record<string, string> = {
  high: "bg-error-container text-error",
  medium: "bg-primary-fixed/60 text-on-primary-fixed-variant",
  low: "bg-secondary-container text-secondary",
  normal: "bg-secondary-container text-secondary",
};

export default function PatientContextPanel({ refreshKey }: { refreshKey?: number }) {
  const { lang, t } = useLang();
  const [data, setData] = useState<PatientContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const loadContext = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      setData(await api.getPatientContext());
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    api.getPatientContext()
      .then((context) => {
        if (!cancelled) {
          setData(context);
          setLoadError(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const hasData = Boolean(
    data && (data.memory_facts.length > 0 || data.latest_report || data.vitals.length > 0)
  );

  const riskLabel = (risk: string) => {
    if (risk === "high") return t("高风险", "High");
    if (risk === "medium") return t("中风险", "Medium");
    return t("正常", "Normal");
  };

  return (
    <aside className="hidden h-full w-80 shrink-0 flex-col border-l border-outline-variant/15 bg-surface-container-lowest lg:flex">
      <div className="flex h-[53px] shrink-0 items-center justify-between border-b border-outline-variant/15 px-4">
        <div className="flex min-w-0 items-center gap-2">
          <span className="material-symbols-outlined text-[18px] text-primary">patient_list</span>
          <h2 className="truncate text-sm font-semibold text-on-surface">{t("其他信息", "Additional Info")}</h2>
        </div>
        <button
          type="button"
          onClick={() => void loadContext()}
          disabled={loading}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface disabled:opacity-50"
          title={t("刷新其他信息", "Refresh additional info")}
        >
          <span className={`material-symbols-outlined text-[17px] ${loading ? "animate-spin" : ""}`}>refresh</span>
        </button>
      </div>

      <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto p-4">
        {loading && !data ? (
          <div className="space-y-4" aria-label={t("正在加载其他信息", "Loading additional info")}>
            {["memory", "lab", "vital"].map((item) => (
              <div key={item} className="space-y-2">
                <div className="h-3 w-28 animate-pulse rounded bg-surface-container" />
                <div className="h-12 animate-pulse rounded-lg bg-surface-container-low" />
              </div>
            ))}
          </div>
        ) : loadError && !data ? (
          <div className="flex h-full flex-col items-center justify-center px-4 text-center">
            <span className="material-symbols-outlined mb-2 text-[24px] text-on-surface-variant/50">cloud_off</span>
            <p className="text-sm text-on-surface-variant">{t("其他信息加载失败", "Failed to load additional info")}</p>
            <button
              type="button"
              onClick={() => void loadContext()}
              className="mt-3 text-xs font-medium text-primary hover:underline"
            >
              {t("重新加载", "Try again")}
            </button>
          </div>
        ) : !hasData ? (
          <div className="flex h-full flex-col items-center justify-center px-4 text-center">
            <span className="material-symbols-outlined mb-2 text-[24px] text-on-surface-variant/40">note_stack</span>
            <p className="text-sm text-on-surface-variant">{t("暂无其他信息", "No additional info")}</p>
          </div>
        ) : (
          <div className="space-y-5">
            {data!.memory_facts.length > 0 && (
              <section>
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-on-surface">
                  <span className="material-symbols-outlined text-[15px] text-primary">memory</span>
                  {t("用户长期记忆", "Long-term Memory")}
                </h3>
                <div className="space-y-2">
                  {data!.memory_facts.map((fact) => (
                    <div key={fact.id} className="flex items-start gap-2 text-xs leading-relaxed">
                      <span className="mt-0.5 shrink-0 font-mono text-[10px] text-primary">[{fact.type}]</span>
                      <span className="min-w-0 text-on-surface-variant">{fact.text}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {data!.latest_report && (
              <section>
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-on-surface">
                  <span className="material-symbols-outlined text-[15px] text-primary">lab_research</span>
                  {t("最近检验摘要", "Latest Lab Summary")}
                </h3>
                <div className="rounded-lg bg-surface-container-low p-3">
                  <p className="text-xs leading-relaxed text-on-surface">
                    {data!.latest_report.summary || t("未提供检验摘要", "No lab summary provided")}
                  </p>
                  {data!.latest_report.created_at && (
                    <p className="mt-1.5 text-[10px] text-on-surface-variant/70">
                      {new Date(data!.latest_report.created_at).toLocaleDateString(lang === "zh" ? "zh-CN" : "en-US")}
                    </p>
                  )}
                </div>
              </section>
            )}

            {data!.vitals.length > 0 && (
              <section>
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-on-surface">
                  <span className="material-symbols-outlined text-[15px] text-primary">monitoring</span>
                  {t("最近穿戴设备数据", "Latest Wearable Data")}
                </h3>
                <div className="space-y-2">
                  {data!.vitals.map((vital) => (
                    <div key={vital.id} className="flex min-w-0 items-center justify-between gap-2 text-xs">
                      <span className="min-w-0 truncate font-mono text-on-surface-variant">
                        {vital.metric}={vital.value}{vital.unit}
                      </span>
                      <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${RISK_COLORS[vital.risk_level] || RISK_COLORS.normal}`}>
                        {riskLabel(vital.risk_level)}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
