"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";

export type Lang = "zh" | "en";

interface LangContextValue {
  lang: Lang;
  toggleLang: () => void;
  t: (zh: string, en: string) => string;
}

const LangContext = createContext<LangContextValue>({ lang: "zh", toggleLang: () => {}, t: (zh) => zh });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("zh");

  useEffect(() => {
    const cached = localStorage.getItem("lang") as Lang | null;
    if (cached === "zh" || cached === "en") setLang(cached);
  }, []);

  const toggleLang = useCallback(() => {
    setLang((prev) => {
      const next = prev === "zh" ? "en" : "zh";
      localStorage.setItem("lang", next);
      return next;
    });
  }, []);

  const t = useCallback((zh: string, en: string) => (lang === "zh" ? zh : en), [lang]);

  return (
    <LangContext.Provider value={{ lang, toggleLang, t }}>
      {children}
    </LangContext.Provider>
  );
}

export function useLang() {
  return useContext(LangContext);
}
