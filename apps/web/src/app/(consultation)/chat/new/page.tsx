"use client";

import { Suspense, useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import ChatPanel from "@/components/chat/ChatPanel";
import PatientContextPanel from "@/components/chat/PatientContextPanel";

function NewChatContent() {
  const searchParams = useSearchParams();
  const newChatKey = searchParams.get("new") ?? "initial";
  const [contextRefreshKey, setContextRefreshKey] = useState(0);
  const handleContextRefresh = useCallback(() => {
    setContextRefreshKey((key) => key + 1);
  }, []);

  return (
    <div className="h-full min-h-0 bg-gradient-to-br from-primary-container/15 via-surface-container to-secondary-container/10 p-2 sm:p-3">
      <div className="flex h-full min-h-0 overflow-hidden rounded-2xl border border-outline-variant/15 bg-surface-container-lowest shadow-lg sm:rounded-3xl">
      <div className="min-w-0 flex-1 bg-surface-container-lowest">
        <ChatPanel key={newChatKey} sessionId={null} showBackButton={false} onMessageSent={handleContextRefresh} />
      </div>
      <PatientContextPanel refreshKey={contextRefreshKey} />
      </div>
    </div>
  );
}

export default function NewChatPage() {
  return (
    <Suspense fallback={<div className="flex h-full min-h-0 items-center justify-center text-on-surface-variant">加载中...</div>}>
      <NewChatContent />
    </Suspense>
  );
}
