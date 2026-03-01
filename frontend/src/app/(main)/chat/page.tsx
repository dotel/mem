"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot } from "lucide-react";
import { api } from "@/lib/api";

type Message = { role: "user" | "assistant"; text: string; time?: string };

const WELCOME =
  "Hello! I'm your productivity assistant. I can help you with time management, focus techniques, and answering questions based on the documents you've uploaded in the Memory section. How can I help you today?";

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", text: WELCOME, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    const userMsg: Message = { role: "user", text, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) };
    const assistantMsg: Message = { role: "assistant", text: "", time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) };
    setMessages((m) => [...m, userMsg, assistantMsg]);
    setLoading(true);
    setError(null);
    const assistantIndex = messages.length + 1;
    try {
      const history = messages.slice(-10).map((m) => ({
        role: m.role,
        text: m.text,
      }));
      await api.sendCommandStream(text, (chunk) => {
        setMessages((m) => {
          const next = [...m];
          if (assistantIndex < next.length) next[assistantIndex] = { ...next[assistantIndex], text: next[assistantIndex].text + chunk };
          return next;
        });
      }, history);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send");
      setMessages((m) => {
        const next = [...m];
        if (assistantIndex < next.length) next[assistantIndex] = { ...next[assistantIndex], text: `Error: ${e instanceof Error ? e.message : "Failed"}` };
        return next;
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col rounded-2xl border border-stone-200 bg-white shadow-sm" style={{ minHeight: "70vh" }}>
      <h1 className="border-b border-stone-100 p-4 text-lg font-semibold text-stone-800">Chat</h1>

      <div className="flex-1 overflow-y-auto p-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`mb-4 flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}
          >
            {msg.role === "assistant" && (
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-stone-200 text-stone-600">
                <Bot size={18} />
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                msg.role === "user"
                  ? "bg-stone-800 text-white"
                  : "bg-stone-100 text-stone-800"
              }`}
            >
              <p className="text-sm">{msg.text}</p>
              {msg.time && (
                <p className={`mt-1 text-xs ${msg.role === "user" ? "text-stone-300" : "text-stone-500"}`}>
                  {msg.time}
                </p>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="border-t border-stone-100 px-4 py-2">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      <div className="border-t border-stone-100 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Ask me about productivity, time management, or your uploaded documents..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 rounded-xl border border-stone-300 px-4 py-3 text-stone-800 placeholder-stone-400 focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500"
          />
          <button
            disabled={loading || !input.trim()}
            onClick={send}
            className="rounded-xl bg-stone-800 p-3 text-white hover:bg-stone-700 disabled:opacity-50"
          >
            <Send size={20} />
          </button>
        </div>
        <p className="mt-2 text-xs text-stone-500">
          Press Enter to send, Shift+Enter for new line.
        </p>
      </div>
    </div>
  );
}
