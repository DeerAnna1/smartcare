"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

interface MobileSidebarContextType {
  mobileOpen: boolean;
  openMobile: () => void;
  closeMobile: () => void;
  toggleMobile: () => void;
}

const MobileSidebarContext = createContext<MobileSidebarContextType>({
  mobileOpen: false,
  openMobile: () => {},
  closeMobile: () => {},
  toggleMobile: () => {},
});

export function MobileSidebarProvider({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const openMobile = useCallback(() => setMobileOpen(true), []);
  const closeMobile = useCallback(() => setMobileOpen(false), []);
  const toggleMobile = useCallback(() => setMobileOpen((v) => !v), []);

  return (
    <MobileSidebarContext.Provider value={{ mobileOpen, openMobile, closeMobile, toggleMobile }}>
      {children}
    </MobileSidebarContext.Provider>
  );
}

export function useMobileSidebar() {
  return useContext(MobileSidebarContext);
}
