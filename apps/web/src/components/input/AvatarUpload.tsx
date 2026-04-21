"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api-client";

interface AvatarUploadProps {
  onAvatarUploaded?: (url: string) => void;
  onError?: (error: string) => void;
  currentAvatarUrl?: string;
}

export default function AvatarUpload({ onAvatarUploaded, onError, currentAvatarUrl }: AvatarUploadProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(currentAvatarUrl || null);

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith("image/")) {
      onError?.("Please select an image file");
      return;
    }

    // Validate file size
    if (file.size > 10 * 1024 * 1024) {
      onError?.("Image size should be less than 10MB");
      return;
    }

    // Create preview
    const reader = new FileReader();
    reader.onload = () => {
      setPreviewUrl(reader.result as string);
    };
    reader.readAsDataURL(file);

    // Upload file
    setIsUploading(true);
    try {
      const result = await api.uploadAvatar(file);
      // Update preview to the persistent API URL so re-opening the panel works
      setPreviewUrl(result.url);
      onAvatarUploaded?.(result.url);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Upload failed";
      onError?.(errorMessage);
      setPreviewUrl(currentAvatarUrl || null);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  return (
    <div className="space-y-3">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileSelect}
        className="hidden"
      />

      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={isUploading}
        className="relative w-full group"
      >
        <div className="w-24 h-24 mx-auto rounded-2xl overflow-hidden bg-primary-fixed relative">
          {previewUrl ? (
            <img src={previewUrl} alt="Avatar preview" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-primary-fixed">
              <span className="material-symbols-outlined text-primary text-[32px]">account_circle</span>
            </div>
          )}
          <div className="absolute inset-0 bg-black/40 group-hover:bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-all">
            <span className="material-symbols-outlined text-white text-[24px]">
              {isUploading ? "loading" : "photo_camera"}
            </span>
          </div>
        </div>
        {isUploading && <p className="text-xs text-center text-on-surface-variant mt-2">上传中...</p>}
      </button>
    </div>
  );
}
