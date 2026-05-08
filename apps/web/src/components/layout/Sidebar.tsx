"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  clearStoredAuth,
  getStoredAuth,
  setStoredAuth,
  AUTH_CHANGED_EVENT,
  type StoredUser,
} from "@/lib/auth";
import { api, toAbsoluteMediaUrl } from "@/lib/api-client";
import { useRef as useFileRef } from "react";
import { useLang } from "@/lib/lang-context";

const navItemsZh = [
  {
    group: "问诊工作区",
    items: [
      { href: "/chat/new", label: "新建咨询", icon: "add_circle" },
      { href: "/chat", label: "历史问诊", icon: "chat" },
    ],
  },
  {
    group: "执行工作区",
    items: [
      { href: "/execution", label: "通用执行", icon: "hub" },
      { href: "/health-records", label: "健康档案", icon: "folder_managed" },
      { href: "/iot-simulator", label: "心率模拟", icon: "monitor_heart" },
    ],
  },
  {
    group: "管理",
    items: [
      { href: "/skills", label: "技能管理", icon: "auto_awesome" },
    ],
  },
];

const navItemsEn = [
  {
    group: "Consultation",
    items: [
      { href: "/chat/new", label: "New Consultation", icon: "add_circle" },
      { href: "/chat", label: "History", icon: "chat" },
    ],
  },
  {
    group: "Execution",
    items: [
      { href: "/execution", label: "Execution", icon: "hub" },
      { href: "/health-records", label: "Health Records", icon: "folder_managed" },
      { href: "/iot-simulator", label: "Heart Rate Sim", icon: "monitor_heart" },
    ],
  },
  {
    group: "Management",
    items: [
      { href: "/skills", label: "Skills", icon: "auto_awesome" },
    ],
  },
];

interface SidebarProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export default function Sidebar({ collapsed = false, onToggleCollapse }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { lang } = useLang();
  const navItems = lang === "en" ? navItemsEn : navItemsZh;
  const [currentUser, setCurrentUser] = useState<StoredUser | null>(null);
  const [avatarUrl, setAvatarUrl] = useState("");
  const [showProfile, setShowProfile] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);
  const avatarFileRef = useRef<HTMLInputElement>(null);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);

  useEffect(() => {
    const stored = getStoredAuth();
    if (stored) {
      setCurrentUser(stored.user);
      setAvatarUrl(toAbsoluteMediaUrl(stored.user.avatar_url || ""));
    }
    api.getCurrentUser().then((u) => {
      setCurrentUser(u);
      setAvatarUrl(toAbsoluteMediaUrl(u.avatar_url || ""));
    }).catch(() => {});
  }, []);

  // 点击外部关闭弹窗
  useEffect(() => {
    if (!showProfile) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setShowProfile(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showProfile]);

  const isActive = (href: string) => {
    if (href === "/chat") return pathname.startsWith("/chat") && pathname !== "/chat/new";
    if (href === "/chat/new") return pathname === "/chat/new";
    if (href === "/iot-simulator") return pathname.startsWith("/iot-simulator");
    if (href === "/execution") return pathname.startsWith("/execution");
    if (href === "/health-records") return pathname.startsWith("/health-records");
    if (href === "/skills") return pathname.startsWith("/skills");
    return pathname === href;
  };

  const handleLogout = () => {
    clearStoredAuth();
    if (typeof window !== "undefined") {
      Object.keys(window.sessionStorage).forEach((key) => {
        if (key.startsWith("pending_msg_")) {
          window.sessionStorage.removeItem(key);
        }
      });
    }
    setShowProfile(false);
    router.replace("/auth");
  };

  const handleAvatarUploaded = (url: string) => {
    setAvatarUrl(toAbsoluteMediaUrl(url));
    setCurrentUser((prev) => (prev ? { ...prev, avatar_url: url } : prev));
    const stored = getStoredAuth();
    if (stored) {
      setStoredAuth({ ...stored, user: { ...stored.user, avatar_url: url } });
    }
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  };

  const handleAvatarFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) { alert(lang === "en" ? "Please select an image file" : "请选择图片文件"); return; }
    if (file.size > 10 * 1024 * 1024) { alert(lang === "en" ? "Image size cannot exceed 10MB" : "图片大小不能超过 10MB"); return; }
    setUploadingAvatar(true);
    try {
      const result = await api.uploadAvatar(file);
      handleAvatarUploaded(result.url);
    } catch {
      alert(lang === "en" ? "Upload failed, please retry" : "上传失败，请重试");
    } finally {
      setUploadingAvatar(false);
      if (avatarFileRef.current) avatarFileRef.current.value = "";
    }
  };

  return (
    <aside
      className={cn(
        "flex-shrink-0 bg-surface-container-lowest h-screen sticky top-0 overflow-y-visible flex flex-col border-r border-outline-variant/20 transition-all duration-300 z-30",
        collapsed ? "w-[68px]" : "w-60"
      )}
    >
      {/* Logo + collapse toggle */}
      <div className="px-4 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5 overflow-hidden">
          <div className="w-8 h-8 rounded-xl bg-primary flex items-center justify-center flex-shrink-0">
            <span className="material-symbols-outlined text-[18px] leading-none text-on-primary">
              medical_information
            </span>
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <span
                className="font-bold text-base text-on-surface tracking-tight block truncate"
                style={{ fontFamily: "Manrope, system-ui" }}
              >
                {lang === "en" ? "ZhiYu" : "智愈"}
              </span>
              <p className="text-[10px] text-on-surface-variant leading-none mt-0.5">
                {lang === "en" ? "Health Assistant" : "全程健康助手"}
              </p>
            </div>
          )}
        </Link>
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            className="p-1.5 rounded-lg text-on-surface-variant hover:bg-surface-container transition-colors flex-shrink-0"
            title={collapsed ? (lang === "en" ? "Expand sidebar" : "展开侧边栏") : (lang === "en" ? "Collapse sidebar" : "收起侧边栏")}
          >
            <span className="material-symbols-outlined text-[18px] leading-none">
              {collapsed ? "chevron_right" : "chevron_left"}
            </span>
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 pb-4 space-y-4">
        {navItems.map((group) => (
          <div key={group.group}>
            {!collapsed && (
              <p className="px-3 mb-1 text-[10px] font-semibold text-on-surface-variant/50 uppercase tracking-widest">
                {group.group}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = isActive(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      "flex items-center rounded-xl text-sm transition-all duration-200",
                      collapsed ? "justify-center px-0 py-2.5 mx-1" : "gap-2.5 px-3 py-2",
                      active
                        ? "bg-primary/10 text-primary font-semibold"
                        : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
                    )}
                  >
                    <span
                      className={cn(
                        "material-symbols-outlined text-[20px] leading-none flex-shrink-0",
                        active ? "text-primary" : "text-on-surface-variant"
                      )}
                      style={{
                        fontVariationSettings: active
                          ? "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 24"
                          : "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24",
                      }}
                    >
                      {item.icon}
                    </span>
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* User + Logout */}
      <div className="border-t border-outline-variant/20 px-2 py-3 space-y-1 relative" ref={profileRef}>
        {currentUser && (
          <button
            type="button"
            onClick={() => setShowProfile((prev) => !prev)}
            className={cn(
              "flex items-center rounded-xl hover:bg-surface-container transition-colors w-full text-left",
              collapsed ? "justify-center px-0 py-2" : "gap-2.5 px-3 py-2"
            )}
          >
            {avatarUrl ? (
              <img
                src={avatarUrl}
                alt="头像"
                className="w-8 h-8 rounded-full object-cover flex-shrink-0"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                <span className="material-symbols-outlined text-primary text-[18px]">person</span>
              </div>
            )}
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-on-surface truncate">{currentUser.display_name}</p>
                <p className="text-[11px] text-on-surface-variant truncate">@{currentUser.username}</p>
              </div>
            )}
          </button>
        )}

        {/* 用户信息弹窗 */}
        {showProfile && currentUser && (
          <div
            className={cn(
              "absolute bottom-full mb-2 bg-surface-container-lowest rounded-2xl border border-outline-variant/20 shadow-[0_16px_48px_rgba(0,0,0,0.12)] p-4 z-50",
              collapsed ? "left-[calc(100%+8px)] bottom-0 w-72" : "left-2 right-2 w-auto"
            )}
          >
            <div className="space-y-3">
              {/* 头像 + 基本信息 */}
              <div className="flex items-center gap-3">
                <input ref={avatarFileRef} type="file" accept="image/*" onChange={handleAvatarFileSelect} className="hidden" />
                <button
                  type="button"
                  onClick={() => avatarFileRef.current?.click()}
                  disabled={uploadingAvatar}
                  className="relative w-11 h-11 rounded-full flex-shrink-0 group overflow-hidden"
                >
                  {avatarUrl ? (
                    <img src={avatarUrl} alt="头像" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full bg-primary/10 flex items-center justify-center">
                      <span className="material-symbols-outlined text-primary text-[22px]">person</span>
                    </div>
                  )}
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-all">
                    <span className="material-symbols-outlined text-white text-[16px]">
                      {uploadingAvatar ? "loading" : "photo_camera"}
                    </span>
                  </div>
                </button>
                <div className="min-w-0">
                  <p className="font-semibold text-on-surface text-sm truncate">{currentUser.display_name}</p>
                  <p className="text-[11px] text-on-surface-variant truncate">@{currentUser.username}</p>
                  <p className="text-[10px] text-on-surface-variant/50 mt-0.5">{lang === "en" ? "Click avatar to upload" : "点击头像上传照片"}</p>
                </div>
              </div>

              {/* 详细信息 */}
              <div className="rounded-xl bg-surface-container-lowest px-3 py-2.5 text-xs text-on-surface-variant space-y-1">
                <p>{lang === "en" ? "Username" : "用户名"}：{currentUser.username}</p>
                <p>{lang === "en" ? "Registered" : "注册时间"}：{new Date(currentUser.created_at).toLocaleDateString(lang === "en" ? "en-US" : "zh-CN")}</p>
              </div>

              {/* 退出按钮 */}
              <button
                type="button"
                onClick={handleLogout}
                className="w-full rounded-xl border border-outline-variant/15 px-3 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-lowest transition-colors"
              >
                {lang === "en" ? "Log Out" : "退出登录"}
              </button>
            </div>
          </div>
        )}

      </div>
    </aside>
  );
}
