"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api-client";

interface FileUploadProps {
  onFileUploaded?: (result: {
    filename: string;
    url: string;
    size: number;
    type: string;
    extracted_text: string;
    extraction_status: "success" | "unsupported" | "failed" | "empty";
  }) => void;
  onError?: (error: string) => void;
  acceptedTypes?: string;
  label?: string;
}

export default function FileUpload({
  onFileUploaded,
  onError,
  acceptedTypes = ".pdf,.doc,.docx,.txt",
  label = "上传文件（支持 PDF、Word、TXT）",
}: FileUploadProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ filename: string; url: string; size: number }>>([]);

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;

    setIsUploading(true);
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const result = await api.uploadDocument(file);
        setUploadedFiles((prev) => [...prev, { filename: result.filename, url: result.url, size: result.size }]);
        onFileUploaded?.(result);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Upload failed";
      onError?.(errorMessage);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleRemoveFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-3">
      <div className="relative">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={acceptedTypes}
          onChange={handleFileSelect}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="w-full p-3 rounded-xl border-2 border-dashed border-primary/40 hover:border-primary/60 transition-all disabled:opacity-50 bg-surface-container/30 flex items-center justify-center gap-2 text-on-surface"
        >
          <span className="material-symbols-outlined">cloud_upload</span>
          <span className="text-sm font-medium">{isUploading ? "上传中..." : label}</span>
        </button>
      </div>

      {uploadedFiles.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-bold text-on-surface-variant uppercase">已上传文件</p>
          <div className="space-y-2">
            {uploadedFiles.map((file, index) => (
              <div
                key={index}
                className="flex items-center justify-between p-3 rounded-xl bg-surface-container/50 group"
              >
                <div className="flex items-center gap-2 flex-1">
                  <span className="material-symbols-outlined text-primary text-[18px]">description</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-on-surface truncate">{file.filename}</p>
                    <p className="text-xs text-on-surface-variant">{(file.size / 1024).toFixed(2)} KB</p>
                  </div>
                </div>
                <button
                  onClick={() => handleRemoveFile(index)}
                  className="p-1 text-on-surface-variant hover:bg-surface-container rounded opacity-0 group-hover:opacity-100 transition-all"
                >
                  <span className="material-symbols-outlined text-[18px]">close</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
