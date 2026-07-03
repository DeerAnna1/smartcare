"use client";

import { useState, useEffect, useRef } from "react";
import { api, toAbsoluteMediaUrl } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

interface KnowledgeDoc {
  id: string;
  title: string;
  source_type: string;
  status: string;
  chunk_count: number;
  created_at: string;
  image_url?: string;
  file_url?: string;
}

interface KnowledgeSearchResult {
  content: string;
  score?: number;
  metadata?: Record<string, unknown>;
}

export default function KnowledgeBasePage() {
  const { t } = useLang();
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [hasSearched, setHasSearched] = useState(false);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const loadDocs = async () => {
    try {
      const data = await api.listKnowledgeDocuments();
      setDocs(data.documents || []);
      setTotal(data.total || 0);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    api.listKnowledgeDocuments()
      .then((data) => {
        if (!active) return;
        setDocs(data.documents || []);
        setTotal(data.total || 0);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError("");
    const extension = `.${file.name.split(".").pop()?.toLowerCase() || ""}`;
    const imageExtensions = new Set([".jpg", ".jpeg", ".png", ".webp"]);
    const documentExtensions = new Set([".pdf", ".docx", ".txt", ".xlsx", ".md"]);
    const isImage = imageExtensions.has(extension);
    if (!isImage && !documentExtensions.has(extension)) {
      setUploadError(t(
        "请选择 JPG、PNG、WebP、PDF、DOCX、TXT、XLSX 或 MD 文件",
        "Please select a JPG, PNG, WebP, PDF, DOCX, TXT, XLSX, or MD file"
      ));
      e.target.value = "";
      return;
    }
    const maxSize = isImage ? 10 * 1024 * 1024 : 50 * 1024 * 1024;
    if (file.size > maxSize) {
      setUploadError(t(
        isImage ? "图片不能超过 10MB" : "文档不能超过 50MB",
        isImage ? "Image must not exceed 10MB" : "Document must not exceed 50MB"
      ));
      e.target.value = "";
      return;
    }
    setUploading(true);
    const localUrl = isImage ? URL.createObjectURL(file) : null;
    setPreviewUrl(localUrl);
    try {
      await api.ingestKnowledgeFile(file);
      await loadDocs();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : t("上传失败，请重试", "Upload failed, please try again"));
    } finally {
      setUploading(false);
      setPreviewUrl(null);
      if (localUrl) URL.revokeObjectURL(localUrl);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleOpenDocument = (doc: KnowledgeDoc) => {
    if (!doc.file_url) return;
    const url = toAbsoluteMediaUrl(doc.file_url);
    const ext = doc.title.split(".").pop()?.toLowerCase() || "";
    // PDF、TXT、MD 在新标签页预览，其他格式触发下载
    if (["pdf", "txt", "md"].includes(ext)) {
      window.open(url, "_blank");
    } else {
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.title;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(t("确认删除该文档？", "Are you sure you want to delete this document?"))) return;
    try {
      await api.deleteKnowledgeDocument(id);
      loadDocs();
    } catch {
      alert(t("删除失败", "Deletion failed"));
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchError("");
    setHasSearched(false);
    setSearchResults([]);
    try {
      const data = await api.searchKnowledge(searchQuery.trim());
      setSearchResults(data.result || []);
      setHasSearched(true);
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : t("检索失败，请检查后端服务", "Search failed, please check the backend service"));
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl min-w-0 space-y-5 px-4 py-5 sm:px-6 sm:py-6">

      {/* 上传区 */}
      <div className="min-w-0 rounded-3xl border border-outline-variant/15 bg-surface-container-lowest p-4 shadow-sm sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-lg font-bold text-on-surface"><span className="material-symbols-outlined text-[20px] text-primary">library_books</span>{t("文档与图片", "Documents & Images")}</h2>
            <p className="text-sm text-on-surface-variant">{t("共", "Total")} {total} {t("份文档", "documents")}</p>
          </div>
          <div className="flex items-center gap-3 self-stretch sm:self-auto">
            {previewUrl && (
              <img src={previewUrl} alt={t("预览", "Preview")} className="w-10 h-10 rounded-lg object-cover border border-outline/20" />
            )}
            <input
              ref={fileRef}
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.pdf,.docx,.txt,.xlsx,.md"
              onChange={handleUpload}
              className="hidden"
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-on-primary shadow-sm hover:opacity-90 disabled:opacity-50 sm:flex-none"
            >
              <span className="material-symbols-outlined text-[18px]">upload_file</span>
              {uploading ? t("上传中...", "Uploading...") : t("上传图片或文档", "Upload Image or Document")}
            </button>
          </div>
        </div>
        {uploadError && <p role="alert" className="mb-4 text-sm text-error break-words">{uploadError}</p>}

        {loading ? (
          <p className="text-on-surface-variant text-sm py-8 text-center">{t("加载中...", "Loading...")}</p>
        ) : docs.length === 0 ? (
          <p className="text-on-surface-variant text-sm py-8 text-center">{t("暂无文档", "No documents yet")}</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {docs.map((doc) => (
              <div key={doc.id} className="flex items-start gap-3 rounded-2xl border border-outline-variant/10 bg-surface-container-low p-3 transition-all hover:-translate-y-0.5 hover:bg-surface-container-lowest hover:shadow-sm">
                {/* 缩略图 */}
                {doc.source_type === "image" ? (
                  <button
                    onClick={() => {
                      const url = toAbsoluteMediaUrl(doc.image_url || `/api/v1/rag/documents/${doc.id}/image`);
                      setLightboxUrl(url);
                    }}
                    className="w-16 h-16 rounded-lg bg-surface-container-highest flex-shrink-0 flex items-center justify-center overflow-hidden border border-outline/20 hover:border-primary/50 transition-colors"
                  >
                    {doc.image_url ? (
                      <img src={toAbsoluteMediaUrl(doc.image_url)} alt={doc.title} className="w-full h-full object-cover" />
                    ) : (
                      <span className="material-symbols-outlined text-2xl text-on-surface-variant">image</span>
                    )}
                  </button>
                ) : doc.file_url ? (
                  <button
                    onClick={() => handleOpenDocument(doc)}
                    className="w-16 h-16 rounded-lg bg-surface-container-highest flex-shrink-0 flex items-center justify-center border border-outline/20 hover:border-primary/50 transition-colors"
                    title={t("点击打开文档", "Click to open document")}
                  >
                    <span className="material-symbols-outlined text-2xl text-on-surface-variant">
                      {doc.title.endsWith(".pdf") ? "picture_as_pdf" : "description"}
                    </span>
                  </button>
                ) : (
                  <div className="w-16 h-16 rounded-lg bg-surface-container-highest flex-shrink-0 flex items-center justify-center border border-outline/20">
                    <span className="material-symbols-outlined text-2xl text-on-surface-variant">description</span>
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-on-surface truncate">{doc.title}</p>
                  <p className="text-xs text-on-surface-variant break-words">
                    {doc.source_type} · {doc.chunk_count} chunks · {doc.status}
                  </p>
                </div>
                <button onClick={() => handleDelete(doc.id)} className="p-1.5 rounded-full hover:bg-error/10 text-on-surface-variant hover:text-error transition-colors flex-shrink-0">
                  <span className="material-symbols-outlined text-[18px]">delete</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 检索测试 */}
      <div className="min-w-0 rounded-3xl border border-outline-variant/15 bg-surface-container-lowest p-4 shadow-sm sm:p-6">
        <h2 className="text-lg font-semibold text-on-surface mb-4">{t("检索测试", "Search Test")}</h2>
        <div className="flex flex-col sm:flex-row gap-2 mb-4">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder={t("输入检索关键词...", "Enter search keywords...")}
            className="w-full min-w-0 flex-1 px-4 py-2.5 rounded-xl bg-surface-container-highest text-on-surface border border-outline/30 focus:border-primary focus:outline-none text-sm"
          />
          <button onClick={handleSearch} disabled={searching} className="px-4 py-2.5 rounded-xl bg-primary text-on-primary text-sm font-medium hover:opacity-90 disabled:opacity-50">
            {searching ? t("检索中...", "Searching...") : t("检索", "Search")}
          </button>
        </div>
        {searchError && (
          <p className="text-sm text-error mb-3">{searchError}</p>
        )}
        {searchResults.length > 0 && (
          <div className="space-y-3">
            {searchResults.map((r, i) => (
              <div key={i} className="p-3 rounded-xl bg-surface-container-low text-sm min-w-0 overflow-hidden">
                <p className="text-on-surface break-all [overflow-wrap:anywhere]">{r.content}</p>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-on-surface-variant mt-2 min-w-0">
                  <span>{t("相似度：", "Similarity: ")}{r.score?.toFixed(3) ?? "-"}</span>
                  {typeof r.metadata?.source === "string" && <span className="truncate max-w-[200px]">{t("来源：", "Source: ")}{r.metadata.source}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
        {hasSearched && searchResults.length === 0 && !searchError && (
          <p className="text-sm text-on-surface-variant py-4 text-center">{t("未找到相关知识，请尝试更具体的关键词", "No relevant knowledge found, please try more specific keywords")}</p>
        )}
      </div>

      {/* 图片灯箱 */}
      {lightboxUrl && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center cursor-pointer p-4"
          onClick={() => setLightboxUrl(null)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh]">
            <img src={lightboxUrl} alt={t("大图预览", "Image Preview")} className="max-w-full max-h-[90vh] object-contain rounded-lg" />
            <button
              onClick={() => setLightboxUrl(null)}
              className="absolute top-3 right-3 w-10 h-10 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 transition-colors"
            >
              <span className="material-symbols-outlined text-xl">close</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
