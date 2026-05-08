"use client";

import { use } from "react";
import ChatPanel from "@/components/chat/ChatPanel";

interface ChatPageProps {
  params: Promise<{ sessionId: string }>;
}

export default function ChatPage({ params }: ChatPageProps) {
  const { sessionId } = use(params);
  return <ChatPanel sessionId={sessionId} />;
}
