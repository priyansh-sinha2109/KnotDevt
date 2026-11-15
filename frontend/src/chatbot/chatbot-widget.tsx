"use client";

/**
 * KnotDevt AI Guide Chatbot — floating assistant widget.
 *
 * Features:
 * - Floating button at bottom-right with KnotDevt branding
 * - Smooth open/close animations (Framer Motion, reduced-motion aware)
 * - Context-aware greetings and suggested questions
 * - User and AI message bubbles with safe markdown rendering
 * - Loading, typing, error, and empty states
 * - Copy-answer, retry-failed-message, and clear-history buttons
 * - Scroll-to-latest without disrupting user scrolling
 * - Keyboard navigation and screen-reader accessibility
 * - Guest and authenticated access isolation
 * - Light and dark theme adaptation
 * - Responsive desktop and mobile layout
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Bot, Copy, Check, RefreshCw, Send, X, Sparkles, Trash2 } from "lucide-react";
import { createApi, ApiError, type Api } from "../api";
import { ChatMarkdown } from "./chatbot-markdown";
import { detectPageContext, getGreeting } from "./chatbot-knowledge";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  error_code: string | null;
  created_at?: string;
}

interface ApiResponse {
  session_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}

interface AvailabilityResponse {
  available: boolean;
  mode: string;
  reason: string | null;
}

const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080/api/v1"
).replace(/\/+$/, "");

export default function ChatbotWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [available, setAvailable] = useState(true);
  const [darkMode, setDarkMode] = useState(false);
  const [pageContext, setPageContext] = useState("landing");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const isAtBottomRef = useRef(true);
  const reduceMotion = useReducedMotion();

  // Determine the API client (with or without CSRF).
  const api: Api = useMemo(
    () => createApi(csrfToken || undefined),
    [csrfToken],
  );

  // Detect current page context on mount and when the URL changes.
  useEffect(() => {
    const update = () => setPageContext(detectPageContext());
    update();
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);

  // Check auth status and availability on mount.
  useEffect(() => {
    let cancelled = false;
    const anonymous = createApi();
    (async () => {
      try {
        const session = await anonymous<{ csrf_token: string } | null>("/auth/me");
        if (cancelled) return;
        if (session && session.csrf_token) {
          setCsrfToken(session.csrf_token);
          setAuthenticated(true);
        }
      } catch {
        // Guest user — no session.
        if (cancelled) return;
        setAuthenticated(false);
      }
      try {
        const avail = await anonymous<AvailabilityResponse>("/chatbot/availability");
        if (cancelled) return;
        setAvailable(avail.available);
      } catch {
        if (cancelled) return;
        setAvailable(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Detect dark mode by observing the workspace element.
  useEffect(() => {
    const checkDark = () => {
      setDarkMode(!!document.querySelector(".workspace.dark"));
    };
    checkDark();
    const observer = new MutationObserver(checkDark);
    observer.observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  // Scroll to bottom when new messages arrive (only if user is at bottom).
  const scrollToBottom = useCallback((force: boolean) => {
    const container = messagesContainerRef.current;
    if (!container) return;
    if (force || isAtBottomRef.current) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: reduceMotion ? "auto" : "smooth",
      });
    }
  }, [reduceMotion]);

  // Track whether the user is scrolled to the bottom.
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const threshold = 60;
    isAtBottomRef.current =
      container.scrollHeight - container.scrollTop - container.clientHeight <
      threshold;
  }, []);

  useEffect(() => {
    scrollToBottom(false);
  }, [messages, scrollToBottom]);

  // Focus input when panel opens.
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), reduceMotion ? 0 : 300);
      scrollToBottom(true);
    }
  }, [isOpen, reduceMotion, scrollToBottom]);

  const greeting = useMemo(
    () => getGreeting(pageContext),
    [pageContext],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || loading || !available) return;

      setInput("");
      setError(null);
      setLoading(true);
      setLastFailedMessage(null);

      // Optimistically add the user message.
      const userMsg: ChatMessage = {
        id: `temp-${Date.now()}`,
        role: "user",
        content: trimmed,
        error_code: null,
      };
      setMessages((prev) => [...prev, userMsg]);
      isAtBottomRef.current = true;

      try {
        const response = await api<ApiResponse>("/chatbot/messages", {
          method: "POST",
          body: {
            message: trimmed,
            page_context: pageContext,
            session_id: sessionId,
          },
        });

        setSessionId(response.session_id);
        // Replace optimistic user message and add assistant response.
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== userMsg.id),
          response.user_message,
          response.assistant_message,
        ]);
        if (response.assistant_message.error_code) {
          setError(response.assistant_message.content);
          setLastFailedMessage(trimmed);
        }
      } catch (err) {
        const msg =
          err instanceof ApiError
            ? err.message
            : "I couldn't reach the AI guide. Please check your connection.";
        setError(msg);
        setLastFailedMessage(trimmed);
        // Add an error assistant message.
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: msg,
            error_code: "request_failed",
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [api, available, loading, pageContext, sessionId],
  );

  const retry = useCallback(() => {
    if (!lastFailedMessage) return;
    // Remove the last message if it's an error.
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      if (last.error_code) return prev.slice(0, -1);
      return prev;
    });
    setError(null);
    sendMessage(lastFailedMessage);
  }, [lastFailedMessage, sendMessage]);

  const clearHistory = useCallback(async () => {
    if (sessionId) {
      try {
        await fetch(`${API_BASE}/chatbot/sessions/${sessionId}`, {
          method: "DELETE",
          credentials: "include",
          headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {},
        });
      } catch {
        // Ignore — clear local state regardless.
      }
    }
    setMessages([]);
    setSessionId(null);
    setError(null);
    setLastFailedMessage(null);
  }, [sessionId, csrfToken]);

  const copyMessage = useCallback(async (content: string, id: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // Clipboard not available.
    }
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage(input);
      }
      if (e.key === "Escape") {
        setIsOpen(false);
      }
    },
    [input, sendMessage],
  );

  const themeClass = darkMode ? "chatbot-dark" : "chatbot-light";

  return (
    <div className={`chatbot-root ${themeClass}`} aria-hidden={!isOpen}>
      {/* Floating button */}
      <motion.button
        className="chatbot-fab"
        onClick={() => setIsOpen(!isOpen)}
        aria-label={isOpen ? "Close AI guide" : "Open AI guide"}
        aria-expanded={isOpen}
        whileHover={reduceMotion ? undefined : { scale: 1.05 }}
        whileTap={reduceMotion ? undefined : { scale: 0.95 }}
        initial={false}
      >
        {isOpen ? <X size={22} /> : <Bot size={22} />}
        <Sparkles size={14} className="chatbot-fab-spark" />
      </motion.button>

      {/* Chat panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="chatbot-panel"
            role="dialog"
            aria-label="KnotDevt AI Guide"
            initial={
              reduceMotion
                ? { opacity: 0 }
                : { opacity: 0, y: 20, scale: 0.95 }
            }
            animate={
              reduceMotion
                ? { opacity: 1 }
                : { opacity: 1, y: 0, scale: 1 }
            }
            exit={
              reduceMotion
                ? { opacity: 0 }
                : { opacity: 0, y: 20, scale: 0.95 }
            }
            transition={{ duration: 0.2, ease: "easeOut" }}
          >
            {/* Header */}
            <div className="chatbot-header">
              <div className="chatbot-header-brand">
                <Bot size={18} />
                <span>KnotDevt Guide</span>
              </div>
              <div className="chatbot-header-actions">
                {messages.length > 0 && (
                  <button
                    className="chatbot-icon-btn"
                    onClick={clearHistory}
                    aria-label="Clear chat history"
                    title="Clear chat history"
                  >
                    <Trash2 size={15} />
                  </button>
                )}
                <button
                  className="chatbot-icon-btn"
                  onClick={() => setIsOpen(false)}
                  aria-label="Close chat"
                  title="Close"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Messages area */}
            <div
              className="chatbot-messages"
              ref={messagesContainerRef}
              onScroll={handleScroll}
              role="log"
              aria-live="polite"
              aria-atomic="false"
            >
              {messages.length === 0 && !loading && (
                <div className="chatbot-empty">
                  <p className="chatbot-greeting">{greeting.greeting}</p>
                  <div className="chatbot-suggestions">
                    {greeting.questions.map((q, i) => (
                      <button
                        key={i}
                        className="chatbot-suggestion"
                        onClick={() => sendMessage(q)}
                        disabled={!available}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                  {!available && (
                    <p className="chatbot-unavailable">
                      The AI guide is not configured. Please contact an administrator.
                    </p>
                  )}
                  <p className="chatbot-disclaimer">
                    Guide Mode: answers about KnotDevt features and navigation.
                    {authenticated ? " You are signed in." : " You are browsing as a guest."}
                  </p>
                </div>
              )}

              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`chatbot-bubble ${
                    msg.role === "user" ? "chatbot-bubble-user" : "chatbot-bubble-ai"
                  }`}
                >
                  <div className="chatbot-bubble-content">
                    {msg.role === "assistant" ? (
                      <ChatMarkdown content={msg.content} />
                    ) : (
                      <span>{msg.content}</span>
                    )}
                  </div>
                  {msg.role === "assistant" && !msg.error_code && (
                    <button
                      className="chatbot-bubble-action"
                      onClick={() => copyMessage(msg.content, msg.id)}
                      aria-label="Copy answer"
                      title="Copy answer"
                    >
                      {copiedId === msg.id ? (
                        <Check size={13} />
                      ) : (
                        <Copy size={13} />
                      )}
                    </button>
                  )}
                  {msg.error_code && (
                    <button
                      className="chatbot-bubble-action chatbot-retry"
                      onClick={retry}
                      aria-label="Retry"
                      title="Retry"
                    >
                      <RefreshCw size={13} />
                    </button>
                  )}
                </div>
              ))}

              {loading && (
                <div className="chatbot-bubble chatbot-bubble-ai">
                  <div className="chatbot-typing">
                    <span className="chatbot-typing-dot" />
                    <span className="chatbot-typing-dot" />
                    <span className="chatbot-typing-dot" />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
            <div className="chatbot-input-area">
              {error && (
                <div className="chatbot-error-bar">
                  <span>{error}</span>
                  {lastFailedMessage && (
                    <button
                      className="chatbot-retry-btn"
                      onClick={retry}
                    >
                      <RefreshCw size={12} /> Retry
                    </button>
                  )}
                </div>
              )}
              <div className="chatbot-input-row">
                <input
                  ref={inputRef}
                  className="chatbot-input"
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    available
                      ? "Ask about KnotDevt…"
                      : "AI guide unavailable…"
                  }
                  disabled={loading || !available}
                  aria-label="Type your question"
                  maxLength={2000}
                />
                <button
                  className="chatbot-send-btn"
                  onClick={() => sendMessage(input)}
                  disabled={loading || !input.trim() || !available}
                  aria-label="Send message"
                >
                  <Send size={16} />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
