"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

type RecordItem = {
  id: string;
  title: string;
  department: string;
  sync_status: string;
  tags: string[];
  event_id?: string | null;
  created_at: string;
};

export default function HealthRecordsPage() {
  const { lang } = useLang();
  const t = (zh: string, en: string) => lang === "zh" ? zh : en;
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingRecordId, setSyncingRecordId] = useState<string | null>(null);
  const [archiveFilter, setArchiveFilter] = useState<"all" | "pending" | "synced">("all");
  const [savingProfile, setSavingProfile] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "dirty" | "saving" | "saved" | "error">("idle");
  const [downloadFormat, setDownloadFormat] = useState("txt");
  const [profile, setProfile] = useState({
    name: "",
    gender: "",
    age: "",
    contact: "",
  });
  const [manualHistory, setManualHistory] = useState("");
  const [savedSnapshot, setSavedSnapshot] = useState({
    name: "",
    gender: "",
    age: "",
    contact: "",
    manual_history: "",
    updated_at: "",
  });
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [ehrSummary, setEhrSummary] = useState("");
  const [isEditingSummary, setIsEditingSummary] = useState(false);
  const pdfContentRef = useRef<HTMLDivElement>(null);

  const draftPayload = useMemo(
    () => ({
      name: profile.name.trim(),
      gender: profile.gender.trim(),
      age: profile.age.trim(),
      contact: profile.contact.trim(),
      manual_history: manualHistory.trim(),
    }),
    [profile, manualHistory]
  );

  const savedPayload = useMemo(
    () => ({
      name: (savedSnapshot.name || "").trim(),
      gender: (savedSnapshot.gender || "").trim(),
      age: (savedSnapshot.age || "").trim(),
      contact: (savedSnapshot.contact || "").trim(),
      manual_history: (savedSnapshot.manual_history || "").trim(),
    }),
    [savedSnapshot]
  );

  const hasUnsavedChanges = useMemo(
    () => JSON.stringify(draftPayload) !== JSON.stringify(savedPayload),
    [draftPayload, savedPayload]
  );

  const loadRecords = async () => {
    setLoading(true);
    try {
      const data = await api.listRecords();
      setRecords(data || []);
    } catch {
      setRecords([]);
    } finally {
      setLoading(false);
    }
  };

  const loadProfile = async () => {
    try {
      const data = await api.getHealthArchiveProfile();
      setProfile({
        name: data.name || "",
        gender: data.gender || "",
        age: data.age || "",
        contact: data.contact || "",
      });
      setManualHistory(data.manual_history || "");
      const nextSaved = {
        name: data.name || "",
        gender: data.gender || "",
        age: data.age || "",
        contact: data.contact || "",
        manual_history: data.manual_history || "",
        updated_at: data.updated_at || "",
      };
      setSavedSnapshot(nextSaved);
      setSaveState("idle");
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    void Promise.all([loadRecords(), loadProfile()]);
  }, []);

  const saveProfile = async (options?: { silent?: boolean }) => {
    if (savingProfile) return;
    setSavingProfile(true);
    setSaveState("saving");
    try {
      const data = await api.updateHealthArchiveProfile(draftPayload);
      const nextSaved = {
        name: data.name || "",
        gender: data.gender || "",
        age: data.age || "",
        contact: data.contact || "",
        manual_history: data.manual_history || "",
        updated_at: data.updated_at || "",
      };
      setSavedSnapshot(nextSaved);
      setSaveState("saved");
      if (!options?.silent) {
        alert(t("已保存到当前用户健康档案", "Saved to health archive"));
      }
    } catch {
      setSaveState("error");
      if (!options?.silent) {
        alert(t("保存失败，请重试", "Save failed, please retry"));
      }
    } finally {
      setSavingProfile(false);
    }
  };

  useEffect(() => {
    if (savingProfile) return;
    if (!hasUnsavedChanges) {
      if (saveState === "dirty") {
        setSaveState("saved");
      }
      return;
    }

    setSaveState("dirty");
    const timer = window.setTimeout(() => {
      void saveProfile({ silent: true });
    }, 1500);

    return () => {
      window.clearTimeout(timer);
    };
  }, [draftPayload, hasUnsavedChanges]);

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!hasUnsavedChanges || savingProfile) return;
      event.preventDefault();
      event.returnValue = t("你有未保存的健康档案输入，确定要离开吗？", "You have unsaved health record changes. Are you sure you want to leave?");
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [hasUnsavedChanges, savingProfile]);

  const pendingCount = useMemo(
    () => records.filter((r) => r.sync_status !== "synced").length,
    [records]
  );

  const syncedCount = useMemo(
    () => records.filter((r) => r.sync_status === "synced").length,
    [records]
  );

  const filteredRecords = useMemo(() => {
    if (archiveFilter === "pending") return records.filter((record) => record.sync_status !== "synced");
    if (archiveFilter === "synced") return records.filter((record) => record.sync_status === "synced");
    return records;
  }, [archiveFilter, records]);

  const archiveDigest = useMemo(() => {
    if (records.length === 0) return t("暂无归档内容", "No archived content");
    return records
      .map((record, index) => {
        const createdAt = new Date(record.created_at).toLocaleString(lang === "zh" ? "zh-CN" : "en-US", { hour12: false });
        return lang === "zh"
          ? `${index + 1}. 时间：${createdAt}\n主诉：${record.title}\n科室：${record.department || "未分科"}\n同步状态：${record.sync_status}`
          : `${index + 1}. Time: ${createdAt}\nChief Complaint: ${record.title}\nDepartment: ${record.department || "Uncategorized"}\nSync Status: ${record.sync_status}`;
      })
      .join("\n\n");
  }, [records]);

  const syncOne = async (recordId: string) => {
    setSyncingRecordId(recordId);
    try {
      await api.syncRecord(recordId);
      setRecords((prev) =>
        prev.map((r) =>
          r.id === recordId ? { ...r, sync_status: "synced" } : r
        )
      );
    } catch {
      alert(t("同步失败，请重试", "Sync failed, please retry"));
    } finally {
      setSyncingRecordId(null);
    }
  };

  const unsyncOne = async (recordId: string) => {
    setSyncingRecordId(recordId);
    try {
      await api.unsyncRecord(recordId);
      setRecords((prev) => prev.map((r) =>
        r.id === recordId ? { ...r, sync_status: "pending" } : r
      ));
      setEhrSummary("");
    } catch {
      alert(t("取消同步失败，请重试", "Failed to cancel sync, please retry"));
    } finally {
      setSyncingRecordId(null);
    }
  };

  const generateSummary = async () => {
    if (generatingSummary) return;
    setGeneratingSummary(true);
    try {
      const profileDigest = lang === "zh"
        ? [
            `姓名：${profile.name || "未填写"}`,
            `性别：${profile.gender || "未填写"}`,
            `年龄：${profile.age || "未填写"}`,
            `联系方式：${profile.contact || "未填写"}`,
          ].join("\n")
        : [
            `Name: ${profile.name || "Not filled"}`,
            `Gender: ${profile.gender || "Not filled"}`,
            `Age: ${profile.age || "Not filled"}`,
            `Contact: ${profile.contact || "Not filled"}`,
          ].join("\n");
      const summaryInput = lang === "zh"
        ? [
            "【个人基础信息】",
            profileDigest,
            "",
            "【用户补充病史】",
            manualHistory || "未填写",
          ].join("\n")
        : [
            "【Personal Basic Info】",
            profileDigest,
            "",
            "【User Supplementary History】",
            manualHistory || "Not filled",
          ].join("\n");

      const data = await api.generateEhrSummary(summaryInput);
      setEhrSummary(data.summary || "");
    } catch {
      alert(t("生成完整 EHR 失败，请重试", "Failed to generate EHR, please retry"));
    } finally {
      setGeneratingSummary(false);
    }
  };

  const buildDownloadContent = () => {
    const profileDigest = lang === "zh"
      ? [
          `姓名：${profile.name || "未填写"}`,
          `性别：${profile.gender || "未填写"}`,
          `年龄：${profile.age || "未填写"}`,
          `联系方式：${profile.contact || "未填写"}`,
        ].join("\n")
      : [
          `Name: ${profile.name || "Not filled"}`,
          `Gender: ${profile.gender || "Not filled"}`,
          `Age: ${profile.age || "Not filled"}`,
          `Contact: ${profile.contact || "Not filled"}`,
        ].join("\n");

    return lang === "zh"
      ? [
          "完整电子健康档案（EHR）",
          "",
          "【个人基础信息】",
          profileDigest,
          "",
          "【用户补充病史】",
          manualHistory || "未填写",
          "",
          "【AI 汇总结果】",
          ehrSummary || "未生成",
          "",
          "【系统归档内容】",
          archiveDigest,
        ].join("\n")
      : [
          "Complete Electronic Health Record (EHR)",
          "",
          "【Personal Basic Info】",
          profileDigest,
          "",
          "【User Supplementary History】",
          manualHistory || "Not filled",
          "",
          "【AI Summary】",
          ehrSummary || "Not generated",
          "",
          "【System Archived Content】",
          archiveDigest,
        ].join("\n");
  };

  const downloadSummary = async () => {
    if (!ehrSummary.trim()) return;

    const content = buildDownloadContent();

    if (downloadFormat === "pdf") {
      try {
        const profileLines = lang === "zh"
          ? [
              `姓名：${profile.name || "未填写"}`,
              `性别：${profile.gender || "未填写"}`,
              `年龄：${profile.age || "未填写"}`,
              `联系方式：${profile.contact || "未填写"}`,
            ]
          : [
              `Name: ${profile.name || "Not filled"}`,
              `Gender: ${profile.gender || "Not filled"}`,
              `Age: ${profile.age || "Not filled"}`,
              `Contact: ${profile.contact || "Not filled"}`,
            ];

        // 获取渲染后的 EHR 内容 HTML
        const ehrHtml = pdfContentRef.current?.innerHTML || "";

        // 如果没有渲染后的 HTML，用简单 markdown 转 HTML
        const renderMarkdown = (md: string) => {
          return md
            .replace(/^### (.+)$/gm, '<h3 style="font-size:15px;font-weight:600;margin:12px 0 6px;color:#b45309;">$1</h3>')
            .replace(/^## (.+)$/gm, '<h2 style="font-size:16px;font-weight:600;margin:16px 0 8px;color:#b45309;">$1</h2>')
            .replace(/^# (.+)$/gm, '<h1 style="font-size:18px;font-weight:bold;margin:20px 0 10px;color:#b45309;">$1</h1>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/^- (.+)$/gm, '<li style="margin:2px 0;margin-left:20px;">$1</li>')
            .replace(/^(\d+)\. (.+)$/gm, '<li style="margin:2px 0;margin-left:20px;">$1. $2</li>')
            .replace(/\n\n/g, '</p><p style="margin:6px 0;font-size:14px;">')
            .replace(/\n/g, '<br/>');
        };

        const finalEhrHtml = ehrHtml || `<p style="margin:6px 0;font-size:14px;">${renderMarkdown(ehrSummary)}</p>`;

        const fullHtml = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>EHR</title>
<style>
  @media print {
    body { margin: 0; }
    @page { margin: 15mm; }
  }
</style>
</head>
<body style="font-family: 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif; color: #1c1917; padding: 20px; max-width: 800px; margin: 0 auto;">
  <h1 style="font-size: 22px; font-weight: bold; text-align: center; margin-bottom: 24px; color: #b45309;">
    ${lang === "zh" ? "完整电子健康档案（EHR）" : "Complete Electronic Health Record (EHR)"}
  </h1>

  <h2 style="font-size: 16px; font-weight: 600; margin-top: 20px; margin-bottom: 8px; color: #b45309;">
    ${lang === "zh" ? "个人基础信息" : "Personal Basic Info"}
  </h2>
  <div style="background: #fef3c7; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px;">
    ${profileLines.map(l => `<p style="margin: 4px 0; font-size: 14px;">${l}</p>`).join("")}
  </div>

  ${manualHistory.trim() ? `
  <h2 style="font-size: 16px; font-weight: 600; margin-top: 20px; margin-bottom: 8px; color: #b45309;">
    ${lang === "zh" ? "用户补充病史" : "User Supplementary History"}
  </h2>
  <div style="background: #f5f5f4; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px;">
    <p style="margin: 0; font-size: 14px; white-space: pre-wrap;">${manualHistory}</p>
  </div>
  ` : ""}

  <h2 style="font-size: 16px; font-weight: 600; margin-top: 20px; margin-bottom: 8px; color: #b45309;">
    ${lang === "zh" ? "AI 汇总结果" : "AI Summary"}
  </h2>
  <div style="background: #f5f5f4; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
    ${finalEhrHtml}
  </div>

  <h2 style="font-size: 16px; font-weight: 600; margin-top: 20px; margin-bottom: 8px; color: #b45309;">
    ${lang === "zh" ? "系统归档内容" : "System Archived Content"}
  </h2>
  <div style="background: #f5f5f4; padding: 12px 16px; border-radius: 8px;">
    <pre style="margin: 0; font-size: 13px; white-space: pre-wrap; font-family: inherit;">${archiveDigest}</pre>
  </div>
</body>
</html>`;

        const printWindow = window.open("", "_blank");
        if (!printWindow) {
          alert(t("请允许弹出窗口以导出 PDF", "Please allow popups to export PDF"));
          return;
        }
        printWindow.document.write(fullHtml);
        printWindow.document.close();
        printWindow.onload = () => {
          printWindow.print();
        };
      } catch (err) {
        console.error("PDF export error:", err);
        alert(t("PDF 导出失败，请重试", "PDF export failed, please retry"));
      }
      return;
    }

    const blob =
      downloadFormat === "word"
        ? new Blob(
            [
              `<html><head><meta charset="utf-8"></head><body><pre>${content}</pre></body></html>`,
            ],
            { type: "application/msword;charset=utf-8" }
          )
        : new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = downloadFormat === "word" ? "complete-ehr.doc" : "complete-ehr.txt";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-w-0 space-y-6 p-4 sm:p-6 lg:p-8">
      <section className="sr-only">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
          <div className="flex max-w-2xl items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-container text-primary">
              <span className="material-symbols-outlined text-[21px]" style={{ fontVariationSettings: "'FILL' 1" }}>health_and_safety</span>
            </div>
            <div><h1 className="font-headline text-xl font-bold text-on-surface sm:text-2xl">{t("我的健康档案", "My Health Records")}</h1>
            <p className="mt-1 max-w-xl text-sm text-on-surface-variant">
              {t("集中管理个人资料、问诊归档与 EHR，同步状态清晰可控。", "Manage your profile, consultation archives, and EHR with clear sync controls.")}
            </p></div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: t("全部档案", "All"), value: records.length, icon: "folder_shared" },
              { label: t("待同步", "Pending"), value: pendingCount, icon: "pending_actions" },
              { label: t("已同步", "Synced"), value: syncedCount, icon: "cloud_done" },
            ].map((item) => (
              <div key={item.label} className="min-w-[82px] rounded-xl bg-surface-container px-3 py-2 sm:min-w-[96px]">
                <div className="flex items-center justify-between gap-2">
                  <span className="material-symbols-outlined text-[16px] text-on-surface-variant">{item.icon}</span>
                  <span className="font-headline text-lg font-bold text-on-surface">{item.value}</span>
                </div>
                <p className="text-[10px] font-semibold text-on-surface-variant">{item.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-stretch">
        <div className="min-w-0 space-y-6 lg:contents">
          <div className="rounded-3xl border border-outline-variant/15 bg-surface-container-lowest p-5 shadow-sm sm:p-6 lg:col-span-5 lg:row-start-1">
            <div className="mb-5 flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary-container text-primary">
                  <span className="material-symbols-outlined text-[21px]">person_edit</span>
                </div>
                <div>
                  <h2 className="font-headline font-bold text-on-surface">{t("个人健康资料", "Personal Health Profile")}</h2>
                  <p className="mt-0.5 text-xs text-on-surface-variant">{t("用于生成更完整的个人 EHR", "Used to build a more complete EHR")}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs ${
                  saveState === "saving"
                    ? "text-primary"
                    : saveState === "saved"
                    ? "text-secondary"
                    : saveState === "error"
                    ? "text-error"
                    : "text-on-surface-variant"
                }`}>
                  {saveState === "saving"
                    ? t("自动保存中...", "Auto-saving...")
                    : saveState === "saved"
                    ? t("已自动保存", "Auto-saved")
                    : saveState === "error"
                    ? t("自动保存失败", "Auto-save failed")
                    : saveState === "dirty"
                    ? t("等待自动保存...", "Pending auto-save...")
                    : ""}
                </span>
                <button
                  onClick={() => void saveProfile()}
                  disabled={savingProfile}
                  className="rounded-xl bg-primary px-3 py-2 text-xs font-bold text-on-primary shadow-sm transition-all hover:opacity-90 disabled:opacity-60 sm:px-4"
                >
                  {savingProfile ? t("保存中...", "Saving...") : t("立即保存", "Save Now")}
                </button>
              </div>
            </div>
            <div className="mb-6 grid grid-cols-2 gap-4">
              <label className="space-y-2 col-span-2">
                <span className="text-sm font-medium text-on-surface">{t("姓名", "Name")}</span>
                <input
                  value={profile.name}
                  onChange={(event) => setProfile((prev) => ({ ...prev, name: event.target.value }))}
                  className="w-full rounded-2xl border border-transparent bg-surface-container px-4 py-3 text-on-surface transition-all focus:border-primary/30 focus:bg-surface-container-lowest focus:outline-none focus:ring-4 focus:ring-primary/10"
                  placeholder={t("请输入姓名", "Enter name")}
                />
              </label>

              <div className="space-y-2 col-span-2">
                <span className="text-sm font-medium text-on-surface">{t("性别", "Gender")}</span>
                <div className="flex items-center gap-5 rounded-2xl border border-transparent bg-surface-container px-4 py-3">
                  <label className="flex items-center gap-2 text-sm text-on-surface">
                    <input
                      type="radio"
                      name="gender"
                      checked={profile.gender === "男"}
                      onChange={() => setProfile((prev) => ({ ...prev, gender: "男" }))}
                    />
                    {t("男", "Male")}
                  </label>
                  <label className="flex items-center gap-2 text-sm text-on-surface">
                    <input
                      type="radio"
                      name="gender"
                      checked={profile.gender === "女"}
                      onChange={() => setProfile((prev) => ({ ...prev, gender: "女" }))}
                    />
                    {t("女", "Female")}
                  </label>
                </div>
              </div>

              <label className="space-y-2">
                <span className="text-sm font-medium text-on-surface">{t("年龄", "Age")}</span>
                <input
                  value={profile.age}
                  onChange={(event) => setProfile((prev) => ({ ...prev, age: event.target.value }))}
                  className="w-full rounded-2xl border border-transparent bg-surface-container px-4 py-3 text-on-surface transition-all focus:border-primary/30 focus:bg-surface-container-lowest focus:outline-none focus:ring-4 focus:ring-primary/10"
                  placeholder={t("请输入年龄", "Enter age")}
                  inputMode="numeric"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-on-surface">{t("联系方式", "Contact")}</span>
                <input
                  value={profile.contact}
                  onChange={(event) => setProfile((prev) => ({ ...prev, contact: event.target.value }))}
                  className="w-full rounded-2xl border border-transparent bg-surface-container px-4 py-3 text-on-surface transition-all focus:border-primary/30 focus:bg-surface-container-lowest focus:outline-none focus:ring-4 focus:ring-primary/10"
                  placeholder={t("请输入手机号或其他联系方式", "Enter phone or other contact info")}
                />
              </label>
            </div>

            <div className="mb-3 flex items-center gap-2 border-t border-outline-variant/10 pt-5">
              <span className="material-symbols-outlined text-[19px] text-primary">history_edu</span>
              <h2 className="font-headline font-bold text-on-surface">{t("既往健康史", "Medical History")}</h2>
            </div>
            <p className="mb-3 text-sm leading-6 text-on-surface-variant">{t("请填写既往疾病史、手术史、过敏史、长期用药、家族史等真实信息。", "Please fill in past medical history, surgical history, allergies, long-term medications, family history, etc.")}</p>
            <textarea
              value={manualHistory}
              onChange={(event) => setManualHistory(event.target.value)}
              className="min-h-[220px] w-full resize-y rounded-2xl border border-transparent bg-surface-container p-4 leading-6 text-on-surface transition-all focus:border-primary/30 focus:bg-surface-container-lowest focus:outline-none focus:ring-4 focus:ring-primary/10"
              placeholder={t("例如：2019 年确诊高血压，长期服用缬沙坦；青霉素过敏；父亲有冠心病史……", "e.g.: Diagnosed with hypertension in 2019, taking valsartan; Penicillin allergy; Father has coronary heart disease...")}
            />
          </div>

          <div className="overflow-hidden rounded-3xl border border-outline-variant/15 bg-surface-container-lowest shadow-sm lg:col-span-12 lg:row-start-2">
            <div className="border-b border-outline-variant/10 bg-gradient-to-r from-primary-container/35 via-surface-container-lowest to-secondary-container/25 px-5 py-5 sm:px-6">
              <div className="flex items-start justify-between gap-4">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary text-on-primary shadow-sm">
                    <span className="material-symbols-outlined text-[22px]" style={{ fontVariationSettings: "'FILL' 1" }}>inventory_2</span>
                  </div>
                  <div className="min-w-0">
                    <h2 className="font-headline text-lg font-bold text-on-surface">{t("系统归档内容", "System Archives")}</h2>
                    <p className="mt-0.5 text-xs text-on-surface-variant">{t("管理归档记录及 EHR 同步状态", "Manage archived records and EHR sync status")}</p>
                  </div>
                </div>
                <span className="shrink-0 rounded-full bg-surface-container-lowest/80 px-3 py-1 text-xs font-bold text-on-surface shadow-sm ring-1 ring-outline-variant/10">
                  {records.length} {t("条", "records")}
                </span>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2" role="tablist" aria-label={t("归档状态筛选", "Archive status filter")}>
                {([
                  { key: "all" as const, label: t("全部", "All"), count: records.length, icon: "folder_shared", tone: "text-on-surface" },
                  { key: "pending" as const, label: t("待同步", "Pending"), count: pendingCount, icon: "schedule", tone: "text-primary" },
                  { key: "synced" as const, label: t("已同步", "Synced"), count: syncedCount, icon: "cloud_done", tone: "text-secondary" },
                ]).map((filterItem) => {
                  const selected = archiveFilter === filterItem.key;
                  return (
                    <button
                      key={filterItem.key}
                      type="button"
                      role="tab"
                      aria-selected={selected}
                      onClick={() => setArchiveFilter(filterItem.key)}
                      className={`flex min-w-0 items-center gap-1.5 rounded-2xl px-2 py-2.5 text-left transition-all sm:px-3 ${
                        selected
                          ? "bg-surface-container-lowest shadow-sm ring-2 ring-primary/25"
                          : "bg-surface-container-low/70 hover:bg-surface-container-lowest/80"
                      } ${filterItem.tone}`}
                    >
                      <span className="material-symbols-outlined hidden text-[17px] sm:block" style={{ fontVariationSettings: filterItem.key === "synced" ? "'FILL' 1" : "'FILL' 0" }}>{filterItem.icon}</span>
                      <span className="truncate text-[11px] font-bold sm:text-xs">{filterItem.label}</span>
                      <span className="ml-auto font-headline text-base font-bold sm:text-lg">{filterItem.count}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {loading ? (
              <div className="flex items-center justify-center gap-2 px-6 py-12 text-sm text-on-surface-variant">
                <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
                <span>{t("正在加载归档...", "Loading archives...")}</span>
              </div>
            ) : records.length === 0 ? (
              <div className="px-6 py-12 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-container text-on-surface-variant">
                  <span className="material-symbols-outlined">folder_off</span>
                </div>
                <p className="mt-3 text-sm font-semibold text-on-surface">{t("暂无系统归档", "No system archives")}</p>
                <p className="mt-1 text-xs text-on-surface-variant">{t("归档通用执行后会显示在这里", "Archived executions will appear here")}</p>
              </div>
            ) : filteredRecords.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <span className="material-symbols-outlined text-3xl text-on-surface-variant/50">filter_alt_off</span>
                <p className="mt-2 text-sm font-semibold text-on-surface">{t("当前筛选下暂无档案", "No records match this filter")}</p>
                <button type="button" onClick={() => setArchiveFilter("all")} className="mt-3 text-xs font-bold text-primary hover:underline">
                  {t("查看全部档案", "View all records")}
                </button>
              </div>
            ) : (
              <div className="max-h-[440px] space-y-3 overflow-y-auto p-4 sm:p-5">
                {filteredRecords.map((rec) => {
                  const isSynced = rec.sync_status === "synced";
                  const isSyncing = syncingRecordId === rec.id;
                  const createdAt = new Date(rec.created_at).toLocaleString(lang === "zh" ? "zh-CN" : "en-US", { hour12: false });
                  return (
                    <article
                      key={rec.id}
                      className={`relative overflow-hidden rounded-2xl border p-4 transition-all hover:-translate-y-0.5 hover:shadow-md ${
                        isSynced
                          ? "border-secondary/20 bg-secondary-container/15"
                          : "border-primary/20 bg-primary-container/15"
                      }`}
                    >
                      <div className={`absolute inset-y-0 left-0 w-1 ${isSynced ? "bg-secondary" : "bg-primary"}`} />
                      <div className="flex items-start gap-3">
                        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                          isSynced ? "bg-secondary-container text-secondary" : "bg-primary-container text-primary"
                        }`}>
                          <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: isSynced ? "'FILL' 1" : "'FILL' 0" }}>
                            {isSynced ? "cloud_done" : "pending_actions"}
                          </span>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-2">
                            <p className="line-clamp-2 text-sm font-bold leading-5 text-on-surface">
                              {rec.title || t("健康问诊归档", "Health Consultation Archive")}
                            </p>
                            <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${
                              isSynced ? "bg-secondary text-on-secondary" : "bg-primary text-on-primary"
                            }`}>
                              {isSynced ? t("已同步", "SYNCED") : t("待同步", "PENDING")}
                            </span>
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-on-surface-variant">
                            <span className="inline-flex items-center gap-1"><span className="material-symbols-outlined text-[14px]">schedule</span>{createdAt}</span>
                            <span className="inline-flex items-center gap-1"><span className="material-symbols-outlined text-[14px]">clinical_notes</span>{rec.department || t("未分科", "Uncategorized")}</span>
                          </div>
                          <button
                            onClick={() => isSynced ? unsyncOne(rec.id) : syncOne(rec.id)}
                            disabled={isSyncing}
                            className={`mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold transition-all disabled:cursor-wait disabled:opacity-50 ${
                              isSynced
                                ? "bg-surface-container-lowest text-error ring-1 ring-error/20 hover:bg-error-container/30"
                                : "bg-primary text-on-primary shadow-sm hover:opacity-90"
                            }`}
                          >
                            <span className="material-symbols-outlined text-[16px]">{isSynced ? "cloud_off" : "cloud_upload"}</span>
                            {isSyncing ? t("处理中...", "Processing...") : isSynced ? t("取消 EHR 同步", "Cancel EHR Sync") : t("同步至 EHR", "Sync to EHR")}
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="min-w-0 space-y-6 lg:col-span-7 lg:row-start-1 lg:h-full">
          <div className="flex h-full flex-col overflow-hidden rounded-3xl border border-outline-variant/15 bg-surface-container-lowest shadow-sm">
            <div className="border-b border-outline-variant/10 bg-gradient-to-r from-secondary-container/25 to-surface-container-lowest p-5 sm:p-6">
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-secondary text-on-secondary shadow-sm">
                  <span className="material-symbols-outlined text-[22px]" style={{ fontVariationSettings: "'FILL' 1" }}>clinical_notes</span>
                </div>
                <div>
                  <h2 className="font-headline text-lg font-bold text-on-surface">{t("完整 EHR 工作台", "EHR Workspace")}</h2>
                  <p className="mt-0.5 text-xs text-on-surface-variant">{t("基于已同步档案生成，可继续编辑并导出", "Generate from synced records, then edit and export")}</p>
                </div>
              </div>
              <div className="mt-5 flex flex-wrap items-center gap-2">
                <button
                  onClick={generateSummary}
                  disabled={generatingSummary}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-on-primary shadow-sm transition-all hover:opacity-90 disabled:opacity-50"
                >
                  <span className={`material-symbols-outlined text-[17px] ${generatingSummary ? "animate-spin" : ""}`}>{generatingSummary ? "progress_activity" : "auto_awesome"}</span>
                  {generatingSummary ? t("生成中...", "Generating...") : t("AI 生成完整 EHR", "AI Generate EHR")}
                </button>
                <select
                  value={downloadFormat}
                  onChange={(event) => setDownloadFormat(event.target.value)}
                  className="rounded-xl border border-outline-variant/20 bg-surface-container-lowest px-3 py-2.5 text-sm font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/30"
                >
                  <option value="txt">TXT</option>
                  <option value="word">Word</option>
                  <option value="pdf">PDF</option>
                </select>
                <button
                  onClick={downloadSummary}
                  disabled={!ehrSummary.trim()}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-secondary px-4 py-2.5 text-sm font-bold text-on-secondary transition-all hover:opacity-90 disabled:opacity-40"
                >
                  <span className="material-symbols-outlined text-[17px]">download</span>
                  {t("下载文件", "Download")}
                </button>
              </div>
            </div>

            <div className="flex flex-1 flex-col p-4 sm:p-6">
              <div className="mb-3 flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold text-on-surface-variant">
                  <span className="h-2 w-2 rounded-full bg-secondary" />
                  {isEditingSummary ? t("编辑模式", "Edit mode") : t("预览模式", "Preview mode")}
                </span>
                {ehrSummary.trim() && (
                  <button
                    onClick={() => setIsEditingSummary(!isEditingSummary)}
                    className="inline-flex items-center gap-1 rounded-xl bg-surface-container px-3 py-1.5 text-xs font-bold text-on-surface-variant transition-all hover:bg-surface-container-high"
                  >
                    <span className="material-symbols-outlined text-[15px]">{isEditingSummary ? "visibility" : "edit"}</span>
                    {isEditingSummary ? t("预览", "Preview") : t("编辑", "Edit")}
                  </button>
                )}
              </div>
              {isEditingSummary ? (
                <textarea
                  value={ehrSummary}
                  onChange={(e) => setEhrSummary(e.target.value)}
                  className="h-[390px] w-full resize-none overflow-y-auto rounded-2xl border border-primary/15 bg-surface-container p-5 text-sm leading-6 text-on-surface focus:outline-none focus:ring-4 focus:ring-primary/10"
                  placeholder={t("点击「AI 生成完整 EHR」后，这里会输出汇总后的个人完整电子健康档案。", "Click 'AI Generate EHR' to generate a complete electronic health record here.")}
                />
              ) : (
                <div className="h-[390px] w-full overflow-y-auto rounded-2xl border border-outline-variant/10 bg-surface-container p-5">
                  {ehrSummary.trim() ? (
                    <div ref={pdfContentRef} className="chat-markdown text-sm leading-6 text-on-surface">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{ehrSummary}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center text-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-secondary-container/50 text-secondary">
                        <span className="material-symbols-outlined text-3xl">docs_add_on</span>
                      </div>
                      <p className="mt-4 font-semibold text-on-surface">{t("尚未生成 EHR", "No EHR generated yet")}</p>
                      <p className="mt-1 max-w-sm text-xs leading-5 text-on-surface-variant">{t("先同步需要纳入的健康档案，然后点击上方按钮生成完整 EHR。", "Sync the records you want to include, then generate your complete EHR above.")}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
