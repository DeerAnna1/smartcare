"use client";

import { useEffect, useState } from "react";
import TopNavBar from "@/components/layout/TopNavBar";
import SideNavBar from "@/components/layout/SideNavBar";

export default function ExecutionLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [navCollapsed, setNavCollapsed] = useState(false);

  useEffect(() => {
    const cached = localStorage.getItem("side_nav_collapsed");
    setNavCollapsed(cached === "1");
  }, []);

  const toggleNav = () => {
    setNavCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("side_nav_collapsed", next ? "1" : "0");
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-surface">
      {/* 执行区 Header 染色（DESIGN.md §5 工作区染色） */}
      <div className="fixed top-0 w-full z-50">
        <div className="h-1 w-full bg-primary-fixed"></div>
        <TopNavBar platformName="智愈全程健康助手" searchPlaceholder="搜索工作台..." />
      </div>
      <div className="flex h-screen pt-16">
        <SideNavBar
          agentName="医疗智能体"
          agentStatus="系统运行中"
          newButtonLabel="新建咨询"
          newButtonHref="/chat/new"
          collapsed={navCollapsed}
          onToggleCollapse={toggleNav}
        />
        <main
          className={`flex-1 overflow-y-auto no-scrollbar transition-all duration-300 ${
            navCollapsed ? "ml-20" : "ml-72"
          }`}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
