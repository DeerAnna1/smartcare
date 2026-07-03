"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

interface SearchResult {
  type: string;
  name: string;
  desc: string;
}

interface KGSearchBarProps {
  onSelect: (type: string, name: string) => void;
  className?: string;
}

const TYPE_ICONS: Record<string, string> = {
  disease: "local_hospital",
  symptom: "sick",
  drug: "medication",
  food: "restaurant",
  check: "biotech",
  department: "business",
};

export default function KGSearchBar({ onSelect, className = "" }: KGSearchBarProps) {
  const { t } = useLang();
  const [query, setQuery] = useState("");

  const TYPE_LABELS: Record<string, string> = {
    disease: t("疾病", "Disease"),
    symptom: t("症状", "Symptom"),
    drug: t("药物", "Drug"),
    food: t("食物", "Food"),
    check: t("检查", "Check"),
    department: t("科室", "Department"),
  };
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("all");
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const doSearch = useCallback(async (q: string, type: string) => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const data = await api.kgSearch(q, type, 15);
      setResults(data.results);
      setOpen(true);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleChange = (value: string) => {
    setQuery(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => doSearch(value, filter), 300);
  };

  const handleFilterChange = (newFilter: string) => {
    setFilter(newFilter);
    if (query.trim()) {
      doSearch(query, newFilter);
    }
  };

  const handleSelect = (type: string, name: string) => {
    setOpen(false);
    setQuery(name);
    onSelect(type, name);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && query.trim()) {
      doSearch(query, filter);
    }
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <div className="flex items-center gap-2">
        {/* 搜索框 */}
        <div className="flex-1 relative">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-xl">search</span>
          <input
            type="text"
            value={query}
            onChange={(e) => handleChange(e.target.value)}
            onFocus={() => results.length > 0 && setOpen(true)}
            onKeyDown={handleKeyDown}
            placeholder={t("搜索疾病、症状、药物...", "Search diseases, symptoms, drugs...")}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-surface-container border border-outline/20 text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-all"
          />
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          )}
        </div>

        {/* 类型筛选 */}
        <div className="flex gap-1">
          {["all", "disease", "symptom", "drug"].map((typeKey) => (
            <button
              key={typeKey}
              onClick={() => handleFilterChange(typeKey)}
              className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                filter === typeKey
                  ? "bg-primary text-on-primary"
                  : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              {typeKey === "all" ? t("全部", "All") : TYPE_LABELS[typeKey] || typeKey}
            </button>
          ))}
        </div>
      </div>

      {/* 搜索结果下拉 */}
      {open && results.length > 0 && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-surface-container border border-outline/20 rounded-xl shadow-lg max-h-80 overflow-y-auto">
          {results.map((r, i) => (
            <button
              key={`${r.type}_${r.name}_${i}`}
              onClick={() => handleSelect(r.type, r.name)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-surface-container-high transition-colors text-left"
            >
              <span className="material-symbols-outlined text-lg text-primary">{TYPE_ICONS[r.type] || "help"}</span>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-on-surface truncate">{r.name}</div>
                <div className="text-xs text-on-surface-variant truncate">{r.desc}</div>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-container-high text-on-surface-variant">
                {TYPE_LABELS[r.type] || r.type}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* 无结果 */}
      {open && query.trim() && !loading && results.length === 0 && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-surface-container border border-outline/20 rounded-xl shadow-lg p-4 text-center text-sm text-on-surface-variant">
          {t("未找到相关结果", "No related results found")}
        </div>
      )}
    </div>
  );
}
