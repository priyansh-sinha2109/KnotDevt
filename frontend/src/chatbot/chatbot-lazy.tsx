"use client";

/**
 * Lazy-loaded wrapper for the chatbot widget.
 *
 * Uses next/dynamic with ssr: false so the widget does not slow down the
 * initial page load or the static export. The component chunk is fetched
 * on demand when the page is interactive.
 */

import dynamic from "next/dynamic";

const ChatbotWidget = dynamic(() => import("./chatbot-widget"), {
  ssr: false,
  loading: () => null,
});

export function ChatbotLazy() {
  return <ChatbotWidget />;
}
