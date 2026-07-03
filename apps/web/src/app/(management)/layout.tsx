"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";
import { ThemeProvider } from "@/lib/theme-context";
import { LangProvider } from "@/lib/lang-context";
import { MobileSidebarProvider, useMobileSidebar } from "@/lib/mobile-sidebar-context";

function ManagementLayoutInner({ children }: { children: React.ReactNode }) {
  const { mobileOpen, openMobile, closeMobile } = useMobileSidebar();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const cached = localStorage.getItem("sidebar_collapsed");
    if (cached === "1") setCollapsed(true);
  }, []);

  const toggleCollapse = () => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar_collapsed", next ? "1" : "0");
      return next;
    });
  };

  return (
    <div className="flex h-screen h-dvh overflow-hidden bg-surface">
      <Sidebar collapsed={collapsed} onToggleCollapse={toggleCollapse} mobileOpen={mobileOpen} onMobileClose={closeMobile} />
      <main className="no-scrollbar h-full min-w-0 flex-1 overflow-y-auto">
        <div className="flex items-center px-4 md:px-6 py-3">
          <button onClick={openMobile} className="p-1.5 rounded-md text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container transition-colors md:hidden mr-auto" title="菜单">
            <span className="material-symbols-outlined text-[20px] leading-none">menu</span>
          </button>
          <div className="ml-auto"><TopBar /></div>
        </div>
        {children}
      </main>
    </div>
  );
}

export default function ManagementLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ThemeProvider>
      <LangProvider>
        <MobileSidebarProvider>
          <ManagementLayoutInner>{children}</ManagementLayoutInner>
        </MobileSidebarProvider>
      </LangProvider>
    </ThemeProvider>
  );
}
