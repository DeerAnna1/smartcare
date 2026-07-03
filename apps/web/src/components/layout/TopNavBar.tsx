"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, toAbsoluteMediaUrl } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";
import AvatarUpload from "@/components/input/AvatarUpload";
import {
  AUTH_CHANGED_EVENT,
  clearStoredAuth,
  getStoredAuth,
  setStoredAuth,
  type StoredUser,
} from "@/lib/auth";

interface TopNavBarProps {
  platformName?: string;
  showSearch?: boolean;
  searchPlaceholder?: string;
}

export default function TopNavBar({
  platformName = "智愈全程健康助手",
  showSearch = true,
  searchPlaceholder = "搜索...",
}: TopNavBarProps) {
  const { t } = useLang();
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [currentUser, setCurrentUser] = useState<StoredUser | null>(null);
  const [avatarUrl, setAvatarUrl] = useState("");
  const profileRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const hydrateUser = async () => {
      const storedAuth = getStoredAuth();
      if (!storedAuth) {
        setCurrentUser(null);
        setAvatarUrl("");
        return;
      }

      setCurrentUser(storedAuth.user);
      setAvatarUrl(toAbsoluteMediaUrl(storedAuth.user.avatar_url || ""));

      try {
        const user = await api.getCurrentUser();
        setCurrentUser(user);
        setAvatarUrl(toAbsoluteMediaUrl(user.avatar_url || ""));
      } catch {
        clearStoredAuth();
        setCurrentUser(null);
        setAvatarUrl("");
      }
    };

    hydrateUser();

    const handleAuthChange = () => {
      void hydrateUser();
    };
    const handleOutsideClick = (event: MouseEvent) => {
      if (!profileRef.current?.contains(event.target as Node)) {
        setIsProfileOpen(false);
      }
    };

    window.addEventListener(AUTH_CHANGED_EVENT, handleAuthChange);
    window.addEventListener("mousedown", handleOutsideClick);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, handleAuthChange);
      window.removeEventListener("mousedown", handleOutsideClick);
    };
  }, []);

  const handleLogout = () => {
    clearStoredAuth();
    if (typeof window !== "undefined") {
      // Clear transient chat bootstrap state to avoid stale data after logout.
      Object.keys(window.sessionStorage).forEach((key) => {
        if (key.startsWith("pending_msg_")) {
          window.sessionStorage.removeItem(key);
        }
      });
    }
    setCurrentUser(null);
    setAvatarUrl("");
    setIsProfileOpen(false);
    if (typeof window !== "undefined") {
      window.location.assign("/auth");
    }
  };

  const handleAvatarUploaded = (url: string) => {
    setAvatarUrl(url);
    setCurrentUser((prev) => (prev ? { ...prev, avatar_url: url } : prev));
    // Persist to localStorage so avatar survives page refresh
    const storedAuth = getStoredAuth();
    if (storedAuth) {
      setStoredAuth({ ...storedAuth, user: { ...storedAuth.user, avatar_url: url } });
    }
  };

  return (
    <nav className="fixed top-0 w-full z-50 flex justify-between items-center px-8 py-3 h-16 bg-surface border-b border-outline-variant/10">
      {/* 左侧：品牌名 + 主导航 */}
      <div className="flex items-center gap-8">
        <Link href="/">
          <span className="font-headline font-extrabold text-primary tracking-tighter text-xl">
            {platformName}
          </span>
        </Link>
      </div>

      {/* 右侧：搜索 + 操作区 */}
      <div className="flex items-center gap-4">
        {showSearch && (
          <div className="relative flex items-center">
            <span className="material-symbols-outlined absolute left-3 text-on-surface-variant text-[20px]">
              search
            </span>
            <input
              className="bg-surface-container-low border-none rounded-xl pl-10 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 w-64"
              placeholder={searchPlaceholder}
              type="text"
            />
          </div>
        )}
        <div className="flex items-center gap-2">
          <button className="p-2 text-on-surface-variant hover:bg-surface-container-low rounded-full transition-all">
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <button className="p-2 text-on-surface-variant hover:bg-surface-container-low rounded-full transition-all">
            <span className="material-symbols-outlined">settings</span>
          </button>
          <div className="relative ml-2" ref={profileRef}>
            <button
              type="button"
              onClick={() => setIsProfileOpen((prev) => !prev)}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-outline-variant/20 bg-primary-fixed transition hover:scale-[1.02]"
            >
              {avatarUrl ? (
                <img
                  src={avatarUrl}
                  alt="用户头像"
                  className="h-full w-full rounded-full object-cover"
                  onError={(e) => {
                    // 图片加载失败（如容器重启后文件丢失）则回退到默认图标
                    e.currentTarget.style.display = "none";
                    e.currentTarget.nextElementSibling?.removeAttribute("style");
                  }}
                />
              ) : null}
              <span
                className="material-symbols-outlined text-primary text-[18px]"
                style={avatarUrl ? { display: "none" } : undefined}
              >
                person
              </span>
            </button>

            {isProfileOpen ? (
              <div className="absolute right-0 top-11 w-72 rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-4 shadow-lg">
                {currentUser ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-3">
                      <div className="w-24">
                        <AvatarUpload
                          currentAvatarUrl={avatarUrl}
                          onAvatarUploaded={handleAvatarUploaded}
                          onError={(message) => alert(message)}
                        />
                      </div>
                      <div>
                        <p className="font-semibold text-on-surface">{currentUser.display_name}</p>
                        <p className="text-xs text-on-surface-variant">@{currentUser.username}</p>
                        <p className="text-[11px] text-on-surface-variant mt-1">{t("点击头像可上传", "Click avatar to upload")}</p>
                      </div>
                    </div>
                    <div className="rounded-2xl bg-surface-container-low px-4 py-3 text-sm text-on-surface-variant">
                      <p>{t("用户名", "Username")}：{currentUser.username}</p>
                      <p>{t("注册时间", "Registered")}：{new Date(currentUser.created_at).toLocaleDateString("zh-CN")}</p>
                    </div>
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="w-full rounded-xl border border-outline-variant/15 px-4 py-2 text-sm font-medium text-on-surface transition hover:bg-surface-container-low"
                    >
                      {t("退出登录", "Logout")}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <p className="font-semibold text-on-surface">{t("未登录", "Not Logged In")}</p>
                      <p className="mt-1 text-sm leading-6 text-on-surface-variant">
                        {t("登录后可查看个人信息，并按账号隔离问诊、执行和健康档案数据。",
                           "Log in to view personal info and isolate consultation, execution, and health record data by account.")}
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <Link
                        href="/auth"
                        className="rounded-xl bg-primary px-4 py-2 text-center text-sm font-semibold text-on-primary transition hover:opacity-90"
                        onClick={() => setIsProfileOpen(false)}
                      >
                        {t("登录", "Login")}
                      </Link>
                      <Link
                        href="/auth?mode=register"
                        className="rounded-xl border border-outline-variant/15 px-4 py-2 text-center text-sm font-semibold text-on-surface transition hover:bg-surface-container-low"
                        onClick={() => setIsProfileOpen(false)}
                      >
                        {t("注册", "Register")}
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </nav>
  );
}
