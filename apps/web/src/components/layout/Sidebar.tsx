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
    group: "知识",
    items: [
      { href: "/kg", label: "知识图谱", icon: "account_tree" },
      { href: "/knowledge-base", label: "知识库管理", icon: "library_books" },
      { href: "/memory", label: "长期记忆", icon: "psychology" },
      { href: "/scheduled-tasks", label: "定时科普", icon: "schedule" },
    ],
  },
  {
    group: "管理",
    items: [
      { href: "/tools", label: "工具管理", icon: "handyman" },
      { href: "/settings", label: "模型配置", icon: "tune" },
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
    group: "Knowledge",
    items: [
      { href: "/kg", label: "Knowledge Graph", icon: "account_tree" },
      { href: "/knowledge-base", label: "Knowledge Base", icon: "library_books" },
      { href: "/memory", label: "Memory", icon: "psychology" },
      { href: "/scheduled-tasks", label: "Scheduled Tasks", icon: "schedule" },
    ],
  },
  {
    group: "Management",
    items: [
      { href: "/tools", label: "Tools", icon: "handyman" },
      { href: "/settings", label: "AI Config", icon: "tune" },
    ],
  },
];

interface SidebarProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export default function Sidebar({ collapsed = false, onToggleCollapse, mobileOpen = false, onMobileClose }: SidebarProps) {
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
  const [hasScheduledTaskUnread, setHasScheduledTaskUnread] = useState(false);
  const newChatSequenceRef = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const stored = getStoredAuth();
      if (stored) {
        setCurrentUser(stored.user);
        setAvatarUrl(toAbsoluteMediaUrl(stored.user.avatar_url || ""));
      }
    }, 0);
    api.getCurrentUser().then((u) => {
      setCurrentUser(u);
      setAvatarUrl(toAbsoluteMediaUrl(u.avatar_url || ""));
    }).catch(() => {});
    return () => window.clearTimeout(timer);
  }, []);

  // 定期检查定时科普未读状态
  useEffect(() => {
    const checkUnread = () => {
      api.getScheduledTaskUnread()
        .then((data) => setHasScheduledTaskUnread(data.total_unread > 0))
        .catch(() => {});
    };
    checkUnread();
    const interval = window.setInterval(checkUnread, 30000); // 每30秒检查一次
    return () => window.clearInterval(interval);
  }, []);

  // 进入定时科普页面时刷新未读状态
  useEffect(() => {
    if (pathname.startsWith("/scheduled-tasks")) {
      api.getScheduledTaskUnread()
        .then((data) => setHasScheduledTaskUnread(data.total_unread > 0))
        .catch(() => {});
    }
  }, [pathname]);

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
    if (href === "/knowledge-base") return pathname.startsWith("/knowledge-base");
    if (href === "/memory") return pathname.startsWith("/memory");
    if (href === "/scheduled-tasks") return pathname.startsWith("/scheduled-tasks");
    if (href === "/tools") return pathname.startsWith("/tools");
    if (href === "/settings") return pathname.startsWith("/settings");
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

  // 移动端点击导航链接后自动关闭侧边栏
  const handleNavClick = (event: React.MouseEvent, href: string) => {
    if (onMobileClose) onMobileClose();
    if (href === "/chat/new") {
      event.preventDefault();
      // A unique URL forces NewChatPage to remount ChatPanel even when the
      // user is already on /chat/new. The previous server-side run continues.
      newChatSequenceRef.current += 1;
      router.push(`/chat/new?new=${newChatSequenceRef.current}`);
    }
  };

  const sidebarContent = (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-30 flex h-screen h-dvh flex-shrink-0 flex-col bg-surface-container-lowest border-r border-outline-variant/20 transition-all duration-300 md:sticky md:inset-y-auto md:top-0",
        // 移动端: 固定定位, 宽度固定为 w-60
        collapsed ? "w-60 md:w-[68px]" : "w-60 md:w-60",
        // 移动端: 根据 mobileOpen 控制显示/隐藏
        mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
      )}
    >
      {/* Logo + collapse toggle */}
      <div className="flex shrink-0 items-center justify-between px-4 py-4">
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
              >
                {lang === "en" ? "ZhiYu" : "智愈"}
              </span>
              <p className="text-[10px] text-on-surface-variant leading-none mt-0.5">
                {lang === "en" ? "Health Assistant" : "全程健康助手"}
              </p>
            </div>
          )}
        </Link>
        {/* 移动端显示关闭按钮，桌面端显示折叠按钮 */}
        {mobileOpen ? (
          <button
            onClick={onMobileClose}
            className="p-1.5 rounded-lg text-on-surface-variant hover:bg-surface-container transition-colors flex-shrink-0"
            title={lang === "en" ? "Close sidebar" : "关闭侧边栏"}
          >
            <span className="material-symbols-outlined text-[18px] leading-none">
              close
            </span>
          </button>
        ) : onToggleCollapse && (
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
      <nav className="no-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto px-2 pb-4">
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
                const showBadge = item.href === "/scheduled-tasks" && hasScheduledTaskUnread;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    title={collapsed ? item.label : undefined}
                    onClick={(event) => handleNavClick(event, item.href)}
                    className={cn(
                      "flex items-center rounded-xl text-sm transition-all duration-200 relative",
                      collapsed ? "justify-center px-0 py-2.5 mx-1" : "gap-2.5 px-3 py-2",
                      active
                        ? "bg-primary/8 text-primary font-semibold border-l-2 border-primary"
                        : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface border-l-2 border-transparent"
                    )}
                  >
                    <span className="relative flex-shrink-0">
                      <span
                        className={cn(
                          "material-symbols-outlined text-[20px] leading-none",
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
                      {showBadge && (
                        <span className="absolute -top-1 -right-1 w-2 h-2 bg-error rounded-full" />
                      )}
                    </span>
                    {!collapsed && (
                      <span className="truncate">
                        {item.label}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* User + Logout */}
      <div className="relative shrink-0 space-y-1 border-t border-outline-variant/20 px-2 py-3" ref={profileRef}>
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
              "absolute bottom-full mb-2 bg-surface-container-lowest rounded-2xl border border-outline-variant/15 shadow-lg p-4 z-50",
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
              <div className="rounded-xl bg-surface-container-low px-3 py-2.5 text-xs text-on-surface-variant space-y-1">
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

  return (
    <>
      {/* 移动端遮罩层 */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-20 md:hidden"
          onClick={onMobileClose}
        />
      )}
      {sidebarContent}
    </>
  );
}
