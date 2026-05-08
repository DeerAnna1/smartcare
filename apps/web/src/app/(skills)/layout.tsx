"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";
import { ThemeProvider } from "@/lib/theme-context";
import { LangProvider } from "@/lib/lang-context";

export default function SkillsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
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
    <ThemeProvider>
      <LangProvider>
        <div className="flex min-h-screen bg-surface">
          <Sidebar collapsed={collapsed} onToggleCollapse={toggleCollapse} />
          <main className="flex-1 overflow-y-auto no-scrollbar min-w-0">
            <div className="flex justify-end px-6 py-3">
              <TopBar />
            </div>
            {children}
          </main>
        </div>
      </LangProvider>
    </ThemeProvider>
  );
}
