"use client";

import { useTheme } from "@/lib/theme-context";
import { useLang } from "@/lib/lang-context";

export default function TopBar() {
  const { theme, toggleTheme } = useTheme();
  const { lang, toggleLang } = useLang();

  return (
    <div className="flex items-center gap-2">
      {/* Theme toggle */}
      <button
        onClick={toggleTheme}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
          bg-surface-container-low text-on-surface-variant hover:bg-surface-container transition-colors"
        title={theme === "light" ? "切换深色模式" : "切换浅色模式"}
      >
        <span className="material-symbols-outlined text-[16px] leading-none">
          {theme === "light" ? "dark_mode" : "light_mode"}
        </span>
        {theme === "light" ? "深色" : "浅色"}
      </button>

      {/* Language toggle */}
      <button
        onClick={toggleLang}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
          bg-surface-container-low text-on-surface-variant hover:bg-surface-container transition-colors"
        title={lang === "zh" ? "Switch to English" : "切换到中文"}
      >
        <span className="material-symbols-outlined text-[16px] leading-none">translate</span>
        {lang === "zh" ? "EN" : "中"}
      </button>
    </div>
  );
}
