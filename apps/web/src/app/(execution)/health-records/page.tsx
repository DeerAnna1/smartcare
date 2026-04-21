"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api-client";

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
        alert("已保存到当前用户健康档案");
      }
    } catch {
      setSaveState("error");
      if (!options?.silent) {
        alert("保存失败，请重试");
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
      event.returnValue = "你有未保存的健康档案输入，确定要离开吗？";
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
    if (records.length === 0) return "暂无归档内容";
    return records
      .map((record, index) => {
        const createdAt = new Date(record.created_at).toLocaleString("zh-CN", { hour12: false });
        return `${index + 1}. 时间：${createdAt}\n主诉：${record.title}\n科室：${record.department || "未分科"}\n同步状态：${record.sync_status}`;
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
      alert("同步失败，请重试");
    } finally {
      setSyncingRecordId(null);
    }
  };

  const generateSummary = async () => {
    if (generatingSummary) return;
    setGeneratingSummary(true);
    try {
      const profileDigest = [
        `姓名：${profile.name || "未填写"}`,
        `性别：${profile.gender || "未填写"}`,
        `年龄：${profile.age || "未填写"}`,
        `联系方式：${profile.contact || "未填写"}`,
      ].join("\n");
      const summaryInput = [
        "【个人基础信息】",
        profileDigest,
        "",
        "【用户补充病史】",
        manualHistory || "未填写",
      ].join("\n");

      const data = await api.generateEhrSummary(summaryInput);
      setEhrSummary(data.summary || "");
    } catch {
      alert("生成完整 EHR 失败，请重试");
    } finally {
      setGeneratingSummary(false);
    }
  };

  const buildDownloadContent = () => {
    const profileDigest = [
      `姓名：${profile.name || "未填写"}`,
      `性别：${profile.gender || "未填写"}`,
      `年龄：${profile.age || "未填写"}`,
      `联系方式：${profile.contact || "未填写"}`,
    ].join("\n");

    return [
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
          alert("PDF 导出失败，请重试");
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
            <h1 className="font-headline font-bold text-3xl text-on-surface">健康档案</h1>
            <p className="text-on-surface-variant text-sm mt-1">
              输入个人实际病史，结合系统归档内容，生成一份完整的个人 EHR 并支持下载。
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-surface-container-lowest rounded-2xl p-6 border-l-4 border-primary shadow-sm">
          <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2">待同步档案</p>
          <p className="font-headline font-bold text-4xl text-primary">{pendingCount}</p>
          <p className="text-xs text-on-surface-variant mt-2">需要处理</p>
        </div>
        <div className="bg-surface-container-lowest rounded-2xl p-6 border-l-4 border-secondary shadow-sm">
          <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2">已同步档案</p>
          <p className="font-headline font-bold text-4xl text-secondary">{syncedCount}</p>
          <p className="text-xs text-on-surface-variant mt-2">当前账号</p>
        </div>
        <div className="bg-surface-container-lowest rounded-2xl p-6 border-l-4 border-tertiary shadow-sm">
          <p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2">档案总数</p>
          <p className="font-headline font-bold text-4xl text-tertiary">{records.length}</p>
          <p className="text-xs text-on-surface-variant mt-2">个人 EHR</p>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-5 space-y-6">
          <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 shadow-sm p-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-headline font-bold text-on-surface">个人信息填写</h2>
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
                    ? "自动保存中..."
                    : saveState === "saved"
                    ? "已自动保存"
                    : saveState === "error"
                    ? "自动保存失败"
                    : saveState === "dirty"
                    ? "等待自动保存..."
                    : ""}
                </span>
                <button
                  onClick={() => void saveProfile()}
                  disabled={savingProfile}
                  className="px-4 py-2 rounded-xl bg-primary text-on-primary text-sm font-semibold hover:opacity-90 transition-all disabled:opacity-60"
                >
                  {savingProfile ? "保存中..." : "立即保存"}
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4 mb-5">
              <label className="space-y-2 col-span-2">
                <span className="text-sm font-medium text-on-surface">姓名</span>
                <input
                  value={profile.name}
                  onChange={(event) => setProfile((prev) => ({ ...prev, name: event.target.value }))}
                  className="w-full rounded-2xl bg-surface-container p-3 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
                  placeholder="请输入姓名"
                />
              </label>

              <div className="space-y-2 col-span-2">
                <span className="text-sm font-medium text-on-surface">性别</span>
                <div className="flex items-center gap-4 rounded-2xl bg-surface-container p-3">
                  <label className="flex items-center gap-2 text-sm text-on-surface">
                    <input
                      type="radio"
                      name="gender"
                      checked={profile.gender === "男"}
                      onChange={() => setProfile((prev) => ({ ...prev, gender: "男" }))}
                    />
                    男
                  </label>
                  <label className="flex items-center gap-2 text-sm text-on-surface">
                    <input
                      type="radio"
                      name="gender"
                      checked={profile.gender === "女"}
                      onChange={() => setProfile((prev) => ({ ...prev, gender: "女" }))}
                    />
                    女
                  </label>
                </div>
              </div>

              <label className="space-y-2">
                <span className="text-sm font-medium text-on-surface">年龄</span>
                <input
                  value={profile.age}
                  onChange={(event) => setProfile((prev) => ({ ...prev, age: event.target.value }))}
                  className="w-full rounded-2xl bg-surface-container p-3 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
                  placeholder="请输入年龄"
                  inputMode="numeric"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-on-surface">联系方式</span>
                <input
                  value={profile.contact}
                  onChange={(event) => setProfile((prev) => ({ ...prev, contact: event.target.value }))}
                  className="w-full rounded-2xl bg-surface-container p-3 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
                  placeholder="请输入手机号或其他联系方式"
                />
              </label>
            </div>

            <h2 className="font-headline font-bold text-on-surface mb-3">用户输入病史</h2>
            <p className="text-sm text-on-surface-variant mb-3">请填写既往疾病史、手术史、过敏史、长期用药、家族史等真实信息。</p>
            <textarea
              value={manualHistory}
              onChange={(event) => setManualHistory(event.target.value)}
              className="w-full min-h-[220px] rounded-2xl bg-surface-container p-4 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40"
              placeholder="例如：2019 年确诊高血压，长期服用缬沙坦；青霉素过敏；父亲有冠心病史……"
            />
          </div>

          <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 shadow-sm p-6">
            <h2 className="font-headline font-bold text-on-surface mb-3">系统归档内容</h2>
            <pre className="whitespace-pre-wrap text-sm text-on-surface-variant bg-surface-container rounded-2xl p-4 max-h-[320px] overflow-y-auto">
              {archiveDigest}
            </pre>
          </div>
        </div>

        <div className="col-span-7 space-y-6">
          <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-headline font-bold text-on-surface">完整 EHR 生成</h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={generateSummary}
                  disabled={generatingSummary}
                  className="px-4 py-2 rounded-xl bg-primary text-on-primary font-semibold hover:opacity-90 transition-all disabled:opacity-50"
                >
                  {generatingSummary ? "生成中..." : "AI 生成完整 EHR"}
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
                  下载文件
                </button>
              </div>
            </div>

            <textarea
              value={ehrSummary}
              onChange={(e) => setEhrSummary(e.target.value)}
              className="w-full h-[320px] resize-none rounded-2xl bg-surface-container p-4 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/40 overflow-y-auto"
              placeholder="点击「AI 生成完整 EHR」后，这里会输出汇总后的个人完整电子健康档案。"
            />
          </div>

          <div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 shadow-sm overflow-hidden">
            <div className="p-6 border-b border-outline-variant/10">
              <h2 className="font-headline font-bold text-on-surface">已归档内容</h2>
            </div>

            {loading ? (
              <div className="p-10 text-center text-on-surface-variant">加载中...</div>
            ) : records.length === 0 ? (
              <div className="p-10 text-center text-on-surface-variant">暂无健康档案</div>
            ) : (
              <div className="divide-y divide-outline-variant/10">
                {records.map((rec) => {
                  const isSynced = rec.sync_status === "synced";
                  const isSyncing = syncingRecordId === rec.id;
                  const createdAt = new Date(rec.created_at).toLocaleString("zh-CN", { hour12: false });

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
                          <p className="text-xs text-on-surface-variant">{rec.department || "未分科"}</p>
                        </div>
                        <p className="font-semibold text-on-surface mt-0.5">{rec.title || "健康问诊归档"}</p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                          isSynced ? "bg-secondary-container/40 text-secondary" : "bg-error-container/40 text-error"
                        }`}>
                          {isSynced ? "已同步 EHR" : "未同步 EHR"}
                        </span>
                        {!isSynced ? (
                          <button
                            onClick={() => syncOne(rec.id)}
                            disabled={isSyncing}
                            className="px-4 py-1.5 bg-primary text-on-primary rounded-xl text-xs font-semibold hover:opacity-90 transition-all disabled:opacity-50"
                          >
                            {isSyncing ? "同步中..." : "同步至 EHR"}
                          </button>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-secondary font-medium">
                            <span className="material-symbols-outlined text-[14px]" style={{ fontVariationSettings: "'FILL' 1" }}>
                              check_circle
                            </span>
                            同步成功
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
