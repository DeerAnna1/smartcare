"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { icon: "chat", label: "历史问诊", href: "/chat" },
  { icon: "hub", label: "通用执行", href: "/execution" },
  { icon: "folder_managed", label: "健康档案", href: "/health-records" },
  { icon: "monitor_heart", label: "心率模拟", href: "/iot-simulator" },
  { icon: "auto_awesome", label: "技能管理", href: "/skills" },
];

interface SideNavBarProps {
  agentName?: string;
  agentStatus?: string;
  showNewButton?: boolean;
  newButtonLabel?: string;
  newButtonHref?: string;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export default function SideNavBar({
  agentName = "医疗智能体",
  agentStatus = "诊断系统就绪",
  showNewButton = true,
  newButtonLabel = "新建咨询",
  newButtonHref = "/chat/new",
  collapsed = false,
  onToggleCollapse,
}: SideNavBarProps) {
  const pathname = usePathname();
  const navIconClass = "material-symbols-outlined text-[20px] leading-none w-5 h-5 flex items-center justify-center";

  const isActive = (href: string) => {
    if (href === "/chat") return pathname.startsWith("/chat");
    if (href === "/iot-simulator") return pathname.startsWith("/iot-simulator");
    if (href === "/execution") return pathname.startsWith("/execution");
    if (href === "/health-records") return pathname.startsWith("/health-records");
    if (href === "/skills") return pathname.startsWith("/skills");
    return pathname === href;
  };

  return (
    <aside
      className={`fixed left-0 top-16 h-[calc(100vh-64px)] flex flex-col bg-surface-container-low p-4 z-40 transition-all duration-300 ${
        collapsed ? "w-20" : "w-72"
      }`}
    >
      <button
        type="button"
        onClick={onToggleCollapse}
        className="absolute left-3 top-3 w-10 h-10 rounded-lg bg-surface-container text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface transition-all flex items-center justify-center"
        title={collapsed ? "展开导航栏" : "收起导航栏"}
      >
        <span className={navIconClass}>
          {collapsed ? "chevron_right" : "chevron_left"}
        </span>
      </button>

      {/* Agent 标识 */}
      <div
        className={`flex items-center px-2 pt-10 mb-5 ${
          collapsed ? "justify-center" : "gap-3"
        }`}
      >
        <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center shrink-0">
          <span className="material-symbols-outlined text-[20px] leading-none text-on-primary">medical_information</span>
        </div>
        {!collapsed && (
          <div>
            <h3 className="font-headline font-bold text-lg text-primary leading-none">{agentName}</h3>
            <p className="text-xs text-on-surface-variant mt-1">{agentStatus}</p>
          </div>
        )}
      </div>

      {/* 新建按钮 */}
      {showNewButton && (
        <Link
          href={newButtonHref}
          className={`w-full py-3 px-4 bg-primary text-on-primary rounded-xl font-semibold flex items-center justify-center gap-2 shadow-lg hover:opacity-90 active:scale-95 transition-all mb-5 ${
            collapsed ? "px-0" : ""
          }`}
          title={newButtonLabel}
        >
          <span className={navIconClass}>add</span>
          {!collapsed && newButtonLabel}
        </Link>
      )}

      {/* 导航列表 */}
      <nav className="flex-1 space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center px-4 py-3 mx-2 rounded-xl transition-all ${
              isActive(item.href)
                ? "bg-surface-container-lowest text-primary font-bold shadow-sm"
                : "text-on-surface-variant font-medium hover:bg-surface-container-lowest/60"
            } ${collapsed ? "justify-center" : "gap-3"}`}
            title={item.label}
          >
            <span
              className={`${navIconClass} ${item.href === "/execution" ? "scale-90" : ""}`}
              style={{ fontVariationSettings: "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24" }}
            >
              {item.icon}
            </span>
            {!collapsed && <span className="font-inter text-[0.875rem]">{item.label}</span>}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
