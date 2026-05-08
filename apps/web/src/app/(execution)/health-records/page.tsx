"use client";

import { useEffect, useMemo, useState } from "react";
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

  const downloadSummary = () => {
    if (!ehrSummary.trim()) return;

    const content = buildDownloadContent();

    if (downloadFormat === "pdf") {
      void (async () => {
        try {
          const blob = await api.exportEhrPdf(content, "complete-ehr.pdf");
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = "complete-ehr.pdf";
          link.click();
          URL.revokeObjectURL(url);
        } catch {
          alert(t("PDF 导出失败，请重试", "PDF export failed, please retry"));
        }
      })();
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
    <div className="p-8 space-y-6">
      <div className="mb-2">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-headline font-bold text-3xl text-on-surface">{t("健康档案", "Health Records")}</h1>
            <p className="text-on-surface-variant text-sm mt-1">
              {t("输入个人实际病史，结合系统归档内容，生成一份完整的个人 EHR 并支持下载。", "Enter personal medical history, combine with system archives, generate a complete EHR and download.")}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-surface-container-lowest rounded-2xl p-6 border-l-4 border-primary shadow-sm">
          <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2">{t("待同步档案", "Pending Sync")}</p>
          <p className="font-headline font-bold text-4xl text-primary">{pendingCount}</p>
          <p className="text-xs text-on-surface-variant mt-2">{t("需要处理", "Needs processing")}</p>
        </div>
        <div className="bg-surface-container-lowest rounded-2xl p-6 border-l-4 border-secondary shadow-sm">
          <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2">{t("已同步档案", "Synced")}</p>
          <p className="font-headline font-bold text-4xl text-secondary">{syncedCount}</p>
          <p className="text-xs text-on-surface-variant mt-2">{t("当前账号", "Current account")}</p>
        </div>
        <div className="bg-surface-container-lowest rounded-2xl p-6 border-l-4 border-tertiary shadow-sm">
          <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2">{t("档案总数", "Total Records")}</p>
          <p className="font-headline font-bold text-4xl text-tertiary">{records.length}</p>
          <p className="text-xs text-on-surface-variant mt-2">EHR</p>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-5 space-y-6">
          <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 shadow-sm p-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-headline font-bold text-on-surface">{t("个人信息填写", "Personal Information")}</h2>
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
                  className="px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-semibold hover:opacity-90 transition-all disabled:opacity-60"
                >
                  {savingProfile ? t("保存中...", "Saving...") : t("立即保存", "Save Now")}
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4 mb-5">
              <label className="space-y-2 col-span-2">
                <span className="text-sm font-medium text-on-surface">{t("姓名", "Name")}</span>
                <input
                  value={profile.name}
                  onChange={(event) => setProfile((prev) => ({ ...prev, name: event.target.value }))}
                  className="w-full rounded-2xl bg-surface-container p-3 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
                  placeholder={t("请输入姓名", "Enter name")}
                />
              </label>

              <div className="space-y-2 col-span-2">
                <span className="text-sm font-medium text-on-surface">{t("性别", "Gender")}</span>
                <div className="flex items-center gap-4 rounded-2xl bg-surface-container p-3">
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
                  className="w-full rounded-2xl bg-surface-container p-3 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
                  placeholder={t("请输入年龄", "Enter age")}
                  inputMode="numeric"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-on-surface">{t("联系方式", "Contact")}</span>
                <input
                  value={profile.contact}
                  onChange={(event) => setProfile((prev) => ({ ...prev, contact: event.target.value }))}
                  className="w-full rounded-2xl bg-surface-container p-3 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
                  placeholder={t("请输入手机号或其他联系方式", "Enter phone or other contact info")}
                />
              </label>
            </div>

            <h2 className="font-headline font-bold text-on-surface mb-3">{t("用户输入病史", "Medical History")}</h2>
            <p className="text-sm text-on-surface-variant mb-3">{t("请填写既往疾病史、手术史、过敏史、长期用药、家族史等真实信息。", "Please fill in past medical history, surgical history, allergies, long-term medications, family history, etc.")}</p>
            <textarea
              value={manualHistory}
              onChange={(event) => setManualHistory(event.target.value)}
              className="w-full min-h-[220px] rounded-2xl bg-surface-container p-4 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
              placeholder={t("例如：2019 年确诊高血压，长期服用缬沙坦；青霉素过敏；父亲有冠心病史……", "e.g.: Diagnosed with hypertension in 2019, taking valsartan; Penicillin allergy; Father has coronary heart disease...")}
            />
          </div>

          <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 shadow-sm p-6">
            <h2 className="font-headline font-bold text-on-surface mb-3">{t("系统归档内容", "System Archives")}</h2>
            <pre className="whitespace-pre-wrap text-sm text-on-surface-variant bg-surface-container rounded-2xl p-4 max-h-[320px] overflow-y-auto">
              {archiveDigest}
            </pre>
          </div>
        </div>

        <div className="col-span-7 space-y-6">
          <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-headline font-bold text-on-surface">{t("完整 EHR 生成", "EHR Generation")}</h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={generateSummary}
                  disabled={generatingSummary}
                  className="px-4 py-2 rounded-xl bg-primary text-on-primary font-semibold hover:opacity-90 transition-all disabled:opacity-50"
                >
                  {generatingSummary ? t("生成中...", "Generating...") : t("AI 生成完整 EHR", "AI Generate EHR")}
                </button>
                <select
                  value={downloadFormat}
                  onChange={(event) => setDownloadFormat(event.target.value)}
                  className="px-3 py-2 rounded-xl bg-surface-container text-on-surface border border-outline-variant/20 focus:outline-none focus:ring-2 focus:ring-primary/40"
                >
                  <option value="txt">TXT</option>
                  <option value="word">Word</option>
                  <option value="pdf">PDF</option>
                </select>
                <button
                  onClick={downloadSummary}
                  disabled={!ehrSummary.trim()}
                  className="px-4 py-2 rounded-xl bg-secondary text-on-secondary font-semibold hover:opacity-90 transition-all disabled:opacity-50"
                >
                  {t("下载文件", "Download")}
                </button>
              </div>
            </div>

            <textarea
              value={ehrSummary}
              onChange={(e) => setEhrSummary(e.target.value)}
              className="w-full h-[320px] resize-none rounded-2xl bg-surface-container p-4 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40 overflow-y-auto"
              placeholder={t("点击「AI 生成完整 EHR」后，这里会输出汇总后的个人完整电子健康档案。", "Click 'AI Generate EHR' to generate a complete electronic health record here.")}
            />
          </div>

          <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 shadow-sm overflow-hidden">
            <div className="p-6 border-b border-outline-variant/10">
              <h2 className="font-headline font-bold text-on-surface">{t("已归档内容", "Archived Content")}</h2>
            </div>

            {loading ? (
              <div className="p-10 text-center text-on-surface-variant">{t("加载中...", "Loading...")}</div>
            ) : records.length === 0 ? (
              <div className="p-10 text-center text-on-surface-variant">{t("暂无健康档案", "No health records")}</div>
            ) : (
              <div className="divide-y divide-outline-variant/10">
                {records.map((rec) => {
                  const isSynced = rec.sync_status === "synced";
                  const isSyncing = syncingRecordId === rec.id;
                  const createdAt = new Date(rec.created_at).toLocaleString(lang === "zh" ? "zh-CN" : "en-US", { hour12: false });

                  return (
                    <div key={rec.id} className="flex items-center gap-5 px-6 py-4 hover:bg-surface-container-low transition-all">
                      <div className="w-12 h-12 rounded-2xl bg-primary-fixed/60 flex items-center justify-center shrink-0">
                        <span className="material-symbols-outlined text-on-surface" style={{ fontVariationSettings: "'FILL' 1" }}>
                          folder_shared
                        </span>
                      </div>

                      <div className="flex-1">
                        <div className="flex items-center gap-3">
                          <p className="text-xs text-on-surface-variant">{createdAt}</p>
                          <p className="text-xs text-on-surface-variant">{rec.department || t("未分科", "Uncategorized")}</p>
                        </div>
                        <p className="font-semibold text-on-surface mt-0.5">{rec.title || t("健康问诊归档", "Health Consultation Archive")}</p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                          isSynced ? "bg-secondary-container/40 text-secondary" : "bg-error-container/40 text-error"
                        }`}>
                          {isSynced ? t("已同步 EHR", "Synced EHR") : t("未同步 EHR", "Unsynced EHR")}
                        </span>
                        {!isSynced ? (
                          <button
                            onClick={() => syncOne(rec.id)}
                            disabled={isSyncing}
                            className="px-4 py-1.5 bg-primary text-on-primary rounded-xl text-xs font-semibold hover:opacity-90 transition-all disabled:opacity-50"
                          >
                            {isSyncing ? t("同步中...", "Syncing...") : t("同步至 EHR", "Sync to EHR")}
                          </button>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-secondary font-medium">
                            <span className="material-symbols-outlined text-[14px]" style={{ fontVariationSettings: "'FILL' 1" }}>
                              check_circle
                            </span>
                            {t("同步成功", "Synced")}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
