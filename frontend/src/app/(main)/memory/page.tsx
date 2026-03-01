"use client";

import { useState, useEffect, useCallback } from "react";
import { Globe, FileText, Plus, Trash2, Info } from "lucide-react";
import { knowledgeApi, type KnowledgeSource } from "@/lib/api";

type Tab = "website" | "document";

export default function MemoryPage() {
  const [tab, setTab] = useState<Tab>("website");
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await knowledgeApi.list(tab);
      setSources(res.sources);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    load();
  }, [load]);

  const addWebsite = async () => {
    const u = url.trim() || "https://example.com";
    setSubmitting(true);
    setError(null);
    try {
      await knowledgeApi.add({ source_type: "website", url: u, title: u });
      setUrl("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add");
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await knowledgeApi.delete(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    }
  };

  const formatDate = (s: string) => {
    try {
      const d = new Date(s);
      return d.toLocaleDateString("en-US", { month: "numeric", day: "numeric", year: "numeric" });
    } catch {
      return s;
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-stone-800">Knowledge Base</h1>
      <p className="text-stone-600">
        Manage documents and websites for the AI chatbot to reference.
      </p>

      <div className="flex gap-2">
        <button
          onClick={() => setTab("website")}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium ${
            tab === "website" ? "bg-stone-800 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"
          }`}
        >
          <Globe size={18} />
          Websites
        </button>
        <button
          onClick={() => setTab("document")}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium ${
            tab === "document" ? "bg-stone-800 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"
          }`}
        >
          <FileText size={18} />
          Documents
        </button>
      </div>

      {tab === "website" && (
        <div className="rounded-xl border border-stone-200 bg-stone-50/50 p-4">
          <h2 className="mb-2 font-medium text-stone-800">Add Website for Crawling</h2>
          <p className="mb-3 text-sm text-stone-500">
            Enter a URL to crawl and add to the chatbot&apos;s knowledge base.
          </p>
          <div className="flex gap-2">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              className="flex-1 rounded-lg border border-stone-300 px-4 py-2 text-stone-800 placeholder-stone-400 focus:border-stone-500 focus:outline-none"
            />
            <button
              disabled={submitting}
              onClick={addWebsite}
              className="flex items-center gap-2 rounded-lg bg-stone-800 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50"
            >
              <Plus size={18} />
              Add Website
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
      )}

      {loading ? (
        <p className="text-stone-500">Loading…</p>
      ) : sources.length === 0 ? (
        <p className="rounded-xl border border-stone-200 bg-stone-50/50 p-6 text-center text-stone-500">
          No {tab}s added yet.
        </p>
      ) : (
        <div className="space-y-3">
          {sources.map((s) => (
            <div
              key={s.id}
              className="flex items-start justify-between gap-4 rounded-xl border border-stone-200 bg-white p-4"
            >
              <div className="min-w-0 flex-1">
                <h3 className="font-medium text-stone-800">{s.title || s.url || "Untitled"}</h3>
                {s.url && (
                  <p className="mt-0.5 truncate text-sm text-stone-500">{s.url}</p>
                )}
                <div className="mt-2 flex items-center gap-3 text-xs text-stone-500">
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-700">
                    {s.status}
                  </span>
                  <span>Added: {formatDate(s.created_at)}</span>
                  <span>{s.pages_crawled} pages crawled</span>
                </div>
              </div>
              <button
                onClick={() => remove(s.id)}
                className="shrink-0 rounded p-2 text-stone-400 hover:bg-red-50 hover:text-red-600"
                title="Delete"
              >
                <Trash2 size={18} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-3 rounded-xl border border-sky-200 bg-sky-50/80 p-4">
        <Info size={20} className="shrink-0 text-sky-600" />
        <p className="text-sm text-sky-800">
          Documents and websites you add here will be processed and indexed. The AI chatbot will
          use this information to provide more accurate and context-aware responses to your
          questions. In a production environment, this would use RAG (Retrieval-Augmented
          Generation) to find relevant content from your knowledge base.
        </p>
      </div>
    </div>
  );
}
