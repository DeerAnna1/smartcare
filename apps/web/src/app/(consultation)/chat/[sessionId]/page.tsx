"use client";

import { use, useState, useCallback } from "react";
import ChatPanel from "@/components/chat/ChatPanel";
import PatientContextPanel from "@/components/chat/PatientContextPanel";

interface ChatPageProps {
  params: Promise<{ sessionId: string }>;
}

export default function ChatPage({ params }: ChatPageProps) {
  const { sessionId } = use(params);
  const [contextRefreshKey, setContextRefreshKey] = useState(0);

  const handleContextRefresh = useCallback(() => {
    setContextRefreshKey((k) => k + 1);
  }, []);

  return (
    <div className="flex h-full min-h-0">
      <div className="min-w-0 flex-1">
        <ChatPanel sessionId={sessionId} onMessageSent={handleContextRefresh} />
      </div>
      <PatientContextPanel refreshKey={contextRefreshKey} />
    </div>
  );
}
