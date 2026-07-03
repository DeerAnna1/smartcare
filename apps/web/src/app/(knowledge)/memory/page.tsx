"use client";

import { useState, useEffect, useMemo } from "react";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

interface MemoryFact {
  id: string;
  fact_type: string;
  value: { text?: string; [key: string]: unknown };
  source_type: string;
  confidence: number;
  status: string;
  created_at: string;
}

export default function MemoryPage() {
  const { t } = useLang();

  const FACT_TYPES = useMemo(
    () => [
      { value: "", label: t("全部", "All") },
      { value: "preference", label: t("偏好", "Preference") },
      { value: "condition", label: t("疾病", "Condition") },
      { value: "allergy", label: t("过敏", "Allergy") },
      { value: "medication", label: t("用药", "Medication") },
      { value: "lifestyle", label: t("生活方式", "Lifestyle") },
      { value: "other", label: t("其他", "Other") },
    ],
    [t]
  );

  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [newText, setNewText] = useState("");
  const [newType, setNewType] = useState("preference");
  const [saving, setSaving] = useState(false);

  const loadFacts = async () => {
    setLoading(true);
    try {
      const data = await api.listMemoryFacts(filterType || undefined);
      setFacts(data);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Reload when the selected memory type changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadFacts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterType]);

  const handleAdd = async () => {
    if (!newText.trim()) return;
    setSaving(true);
    try {
      await api.createDirectMemory({ text: newText.trim(), fact_type: newType });
      setNewText("");
      setShowAdd(false);
      loadFacts();
    } catch {
      alert(t("保存失败", "Save failed"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(t("确认删除该记忆？", "Delete this memory?"))) return;
    try {
      await api.deleteMemoryFact(id);
      loadFacts();
    } catch {
      alert(t("删除失败", "Delete failed"));
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-5 sm:px-6">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setShowAdd(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-on-primary shadow-sm hover:opacity-90"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          {t("添加记忆", "Add Memory")}
        </button>
      </div>

      {/* 筛选 */}
      <div className="flex flex-wrap gap-2 rounded-2xl border border-outline-variant/10 bg-surface-container-lowest p-2 shadow-sm">
        {FACT_TYPES.map((item) => (
          <button
            key={item.value}
            onClick={() => setFilterType(item.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
              filterType === item.value
                ? "bg-primary text-on-primary"
                : "bg-surface-container-low text-on-surface-variant hover:bg-surface-container"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* 添加弹窗 */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-container rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-bold text-on-surface mb-4">{t("添加长期记忆", "Add Long-term Memory")}</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-on-surface mb-1">{t("类型", "Type")}</label>
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 text-sm"
                >
                  {FACT_TYPES.filter((item) => item.value).map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-on-surface mb-1">{t("内容", "Content")}</label>
                <textarea
                  value={newText}
                  onChange={(e) => setNewText(e.target.value)}
                  placeholder={t("例如：我对青霉素过敏", "e.g. I'm allergic to penicillin")}
                  rows={3}
                  className="w-full px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm resize-none"
                />
              </div>
            </div>
            <div className="flex gap-3 justify-end mt-5">
              <button onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-xl text-sm text-on-surface-variant hover:bg-surface-container-high">{t("取消", "Cancel")}</button>
              <button onClick={handleAdd} disabled={saving} className="px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-medium hover:opacity-90 disabled:opacity-50">
                {saving ? t("保存中...", "Saving...") : t("保存", "Save")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 记忆列表 */}
      {loading ? (
        <p className="text-on-surface-variant text-sm py-12 text-center">{t("加载中...", "Loading...")}</p>
      ) : facts.length === 0 ? (
        <p className="text-on-surface-variant text-sm py-12 text-center">{t("暂无记忆", "No memories yet")}</p>
      ) : (
        <div className="space-y-3">
          {facts.map((f) => (
            <div key={f.id} className="flex items-start justify-between rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-4 transition-all hover:border-primary/20 hover:shadow-sm">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-[10px] font-semibold">{f.fact_type}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${f.status === "confirmed" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>
                    {f.status}
                  </span>
                </div>
                <p className="text-sm text-on-surface">{f.value?.text || JSON.stringify(f.value)}</p>
                <p className="text-xs text-on-surface-variant mt-1">
                  {t("来源", "Source")}: {f.source_type} · {t("置信度", "Confidence")}: {(f.confidence * 100).toFixed(0)}%
                </p>
              </div>
              <button onClick={() => handleDelete(f.id)} className="ml-3 p-1.5 rounded-full hover:bg-error/10 text-on-surface-variant hover:text-error transition-colors flex-shrink-0">
                <span className="material-symbols-outlined text-[18px]">delete</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
