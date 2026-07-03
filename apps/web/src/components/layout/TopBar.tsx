"use client";

import { useTheme } from "@/lib/theme-context";
import { useLang } from "@/lib/lang-context";

export default function TopBar() {
  const { theme, toggleTheme } = useTheme();
  const { lang, toggleLang } = useLang();

  return (
    <div className="flex items-center gap-1">
      {/* Theme toggle */}
      <button
        onClick={toggleTheme}
        className="p-1.5 rounded-md text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container transition-colors"
        title={theme === "light" ? "切换深色模式" : "切换浅色模式"}
      >
        <span className="material-symbols-outlined text-[18px] leading-none">
          {theme === "light" ? "dark_mode" : "light_mode"}
        </span>
      </button>

      {/* Language toggle */}
      <button
        onClick={toggleLang}
        className="px-2 py-1 rounded-md text-xs font-medium text-on-surface-variant/60 hover:text-on-surface hover:bg-surface-container transition-colors"
        title={lang === "zh" ? "Switch to English" : "切换到中文"}
      >
        {lang === "zh" ? "EN" : "中"}
      </button>
    </div>
  );
}
