"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, Settings, CheckCircle, ChevronDown, ChevronRight, ExternalLink, Calendar, ChevronLeft } from "lucide-react";
import { srApi, type SRTopic, type NeetcodeProblem } from "@/lib/api";
import { usePomodoro } from "@/contexts/PomodoroContext";

const SR_INTERVALS = [1, 3, 7, 14];

function nextInLadder(current: number): number {
  const idx = SR_INTERVALS.indexOf(current);
  if (idx < 0) return 14;
  return SR_INTERVALS[Math.min(idx + 1, SR_INTERVALS.length - 1)];
}

function formatDate(d: Date): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  if (d.getTime() === today.getTime()) return "Today";
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (d.getTime() === tomorrow.getTime()) return "Tomorrow";
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function toDateStr(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function parseDateStr(s: string): Date {
  return new Date(s + "T12:00:00");
}

/** Capacity-aware scheduler: assigns topics to days so no day exceeds daily capacity. */
function getCapacityAwareScheduledDates(
  topics: SRTopic[],
  dailyCapacityMinutes: number,
  count: number = 4
): Map<number, string[]> {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayStr = toDateStr(today);

  // dayMinutes: date string -> total minutes scheduled that day
  const dayMinutes = new Map<string, number>();
  const getDayMinutes = (d: string) => dayMinutes.get(d) ?? 0;
  const addToDay = (d: string, mins: number) => dayMinutes.set(d, getDayMinutes(d) + mins);

  // per-topic state for each "round" of scheduling
  type TopicState = { id: number; mins: number; lastScheduled: string; interval: number };
  let states: TopicState[] = topics.map((t) => {
    const interval = t.next_interval_days ?? 1;
    let lastScheduled = todayStr;
    if (t.skip_show_again_date && t.skip_show_again_date > todayStr) {
      lastScheduled = t.skip_show_again_date;
    } else if (t.last_reviewed) {
      const last = parseDateStr(t.last_reviewed);
      const ideal = new Date(last);
      ideal.setDate(ideal.getDate() + interval);
      ideal.setHours(0, 0, 0, 0);
      if (ideal < today) lastScheduled = todayStr;
      else lastScheduled = toDateStr(ideal);
    } else if (t.first_due_date) {
      lastScheduled = t.first_due_date;
    }
    return {
      id: t.id,
      mins: t.estimated_minutes ?? 60,
      lastScheduled,
      interval,
    };
  });

  const result = new Map<number, string[]>();

  for (let round = 0; round < count; round++) {
    // Compute ideal due date for each topic (may be in the past if overdue)
    const candidates: { state: TopicState; idealStr: string }[] = states.map((s) => {
      const idealDate = parseDateStr(s.lastScheduled);
      const idealStr = idealDate < today ? todayStr : toDateStr(idealDate);
      return { state: s, idealStr };
    });

    // Sort by ideal date (earliest first), then by minutes (smaller first)
    candidates.sort((a, b) => {
      const da = a.idealStr;
      const db = b.idealStr;
      if (da !== db) return da.localeCompare(db);
      return a.state.mins - b.state.mins;
    });

    const nextStates: TopicState[] = [];
    for (const { state, idealStr } of candidates) {
      let d = idealStr;
      if (state.mins <= dailyCapacityMinutes) {
        while (getDayMinutes(d) + state.mins > dailyCapacityMinutes) {
          const next = parseDateStr(d);
          next.setDate(next.getDate() + 1);
          d = toDateStr(next);
        }
      }
      addToDay(d, state.mins);
      const arr = result.get(state.id) ?? [];
      arr.push(formatDate(parseDateStr(d)));
      result.set(state.id, arr);
      const nextInterval = nextInLadder(state.interval);
      nextStates.push({
        ...state,
        lastScheduled: d,
        interval: nextInterval,
      });
    }
    // For next round: ideal date = lastScheduled + interval
    states = nextStates.map((s) => {
      const next = parseDateStr(s.lastScheduled);
      next.setDate(next.getDate() + s.interval);
      return { ...s, lastScheduled: toDateStr(next) };
    });
  }

  return result;
}

/** Build list of days with scheduled topics for tab view. */
function getScheduleByDay(
  topics: SRTopic[],
  schedule: Map<number, string[]>,
  dayCount: number = 14
): { dateStr: string; label: string; topicIds: number[] }[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const result: { dateStr: string; label: string; topicIds: number[] }[] = [];
  for (let i = 0; i < dayCount; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() + i);
    const dateStr = toDateStr(d);
    const label = formatDate(d);
    const topicIds = topics
      .filter((t) => (schedule.get(t.id) ?? []).includes(label))
      .map((t) => t.id);
    result.push({ dateStr, label, topicIds });
  }
  return result;
}

export default function PracticePage() {
  const { streak, refreshStreak } = usePomodoro();
  const [topics, setTopics] = useState<SRTopic[]>([]);
  const [settings, setSettings] = useState<{ daily_capacity_minutes: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newEstimate, setNewEstimate] = useState<number | "">(60);
  const [adding, setAdding] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editCapacity, setEditCapacity] = useState<number | "">(120);
  const [editingEstimateId, setEditingEstimateId] = useState<number | null>(null);
  const [editingEstimateValue, setEditingEstimateValue] = useState<number | "">(60);
  const [neetcodeOpen, setNeetcodeOpen] = useState(false);
  const [neetcodeProblems, setNeetcodeProblems] = useState<NeetcodeProblem[]>([]);
  const [neetcodeLoading, setNeetcodeLoading] = useState(false);
  const [neetcodeSelected, setNeetcodeSelected] = useState<Set<string>>(new Set());
  const [neetcodeImporting, setNeetcodeImporting] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [deleteAllConfirm, setDeleteAllConfirm] = useState(false);
  const [deletingAll, setDeletingAll] = useState(false);
  const [selectedDayIndex, setSelectedDayIndex] = useState(0);
  const [neetcodePatternPage, setNeetcodePatternPage] = useState(0);
  const [topicsPage, setTopicsPage] = useState(0);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [topicsRes, settingsRes] = await Promise.all([
        srApi.listTopics(),
        srApi.getSettings(),
      ]);
      await refreshStreak();
      setTopics(topicsRes.topics);
      setSettings(settingsRes);
      setEditCapacity(settingsRes.daily_capacity_minutes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
      setTopics([]);
      setSettings(null);
    } finally {
      setLoading(false);
    }
  }, [refreshStreak]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!neetcodeOpen || neetcodeProblems.length > 0) return;
    setNeetcodeLoading(true);
    srApi.getNeetcode150()
      .then((r) => setNeetcodeProblems(r.problems || []))
      .catch(() => setNeetcodeProblems([]))
      .finally(() => setNeetcodeLoading(false));
  }, [neetcodeOpen, neetcodeProblems.length]);

  useEffect(() => {
    if (neetcodeProblems.length > 0) setNeetcodePatternPage(0);
  }, [neetcodeProblems.length]);

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(topics.length / 15));
    if (topicsPage >= totalPages) setTopicsPage(Math.max(0, totalPages - 1));
  }, [topics.length, topicsPage]);

  const handleImportNeetcode = async () => {
    const slugs = Array.from(neetcodeSelected);
    if (!slugs.length) return;
    setNeetcodeImporting(true);
    setError(null);
    try {
      const res = await srApi.importNeetcode150(slugs);
      setTopics(res.topics);
      setNeetcodeSelected(new Set());
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to import");
    } finally {
      setNeetcodeImporting(false);
    }
  };

  const handleAdd = async () => {
    const name = newName.trim();
    if (!name) return;
    setAdding(true);
    setError(null);
    try {
      const mins = newEstimate === "" ? 60 : (Number(newEstimate) || 60);
      await srApi.createTopic({ name, estimated_minutes: mins });
      setNewName("");
      setNewEstimate(60);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add");
    } finally {
      setAdding(false);
    }
  };

  const handleDeleteAll = async () => {
    setDeletingAll(true);
    setError(null);
    try {
      await srApi.deleteAllTopics();
      setDeleteAllConfirm(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    } finally {
      setDeletingAll(false);
    }
  };

  const handleDelete = async (id: number) => {
    setDeleteConfirmId(null);
    setError(null);
    try {
      await srApi.deleteTopic(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    }
  };

  const handleSaveSettings = async () => {
    setError(null);
    try {
      const cap = editCapacity === "" ? 120 : (Number(editCapacity) || 120);
      await srApi.updateSettings({ daily_capacity_minutes: cap });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    }
    setSettingsOpen(false);
  };

  const handleRetire = async (topicId: number) => {
    if (!confirm("Mark this topic as done completely? It will be removed from practice.")) return;
    setError(null);
    try {
      await srApi.retireTopic(topicId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to retire");
    }
  };

  const handleUpdateEstimate = async (topicId: number, value: number | "", currentMins: number) => {
    const mins = value === "" ? currentMins : Math.max(1, Math.min(480, Number(value) || 60));
    setEditingEstimateId(null);
    if (mins === currentMins) return;
    setError(null);
    try {
      await srApi.updateTopic(topicId, { estimated_minutes: mins });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update");
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-stone-300 border-t-stone-600" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="rounded-2xl border border-stone-200 bg-white p-8 shadow-sm">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold text-stone-800">Spaced Repetition</h1>
          <div className="flex items-center gap-2">
            {streak && (streak.current_streak > 0 || streak.longest_streak > 0) && (
              <span className="rounded-full bg-amber-50 px-3 py-1 text-sm text-amber-800" title="Practice streak">
                🔥 {streak.current_streak} day{streak.current_streak === 1 ? "" : "s"} streak{streak.longest_streak > streak.current_streak ? ` (best: ${streak.longest_streak})` : ""}
              </span>
            )}
            <button
              onClick={() => setSettingsOpen((v) => !v)}
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-stone-600 hover:bg-stone-100 hover:text-stone-800"
            >
              <Settings size={18} />
              Settings
            </button>
          </div>

          {settingsOpen && (
            <div className="mb-6 rounded-lg border border-stone-200 bg-stone-50 p-4">
              <label className="mb-2 block text-sm font-medium text-stone-600">
                Daily capacity (minutes)
              </label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min={15}
                  max={720}
                  value={editCapacity}
                  onChange={(e) => {
                    const v = e.target.value;
                    setEditCapacity(v === "" ? "" : parseInt(v, 10) || 120);
                  }}
                  className="rounded-lg border border-stone-200 px-4 py-2 text-stone-800"
                />
                <button
                  onClick={handleSaveSettings}
                  className="rounded-lg bg-stone-800 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700"
                >
                  Save
                </button>
              </div>
              <p className="mt-2 text-xs text-stone-500">
                How many minutes you can devote to practice per day (used for scheduling).
              </p>
              {topics.length > 0 && (
                <div className="mt-4 border-t border-stone-200 pt-4">
                  <label className="mb-2 block text-sm font-medium text-stone-600">Danger zone</label>
                  {deleteAllConfirm ? (
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-stone-600">Delete all {topics.length} topics?</span>
                      <button
                        onClick={handleDeleteAll}
                        disabled={deletingAll}
                        className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
                      >
                        Yes, delete all
                      </button>
                      <button
                        onClick={() => setDeleteAllConfirm(false)}
                        className="rounded border border-stone-300 px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-100"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setDeleteAllConfirm(true)}
                      className="rounded border border-red-200 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-100"
                    >
                      Delete all topics
                    </button>
                  )}
                  <p className="mt-1 text-xs text-stone-500">
                    Clears your task list so you can start fresh. Completion history and streak are preserved.
                  </p>
                </div>
              )}
            </div>
          )}

          {error && (
            <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
          )}

          {topics.length > 0 && (
            <div className="mb-8">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-medium text-stone-600">
                <Calendar size={16} />
                Upcoming schedule
              </h2>
              {(() => {
                const schedule = getCapacityAwareScheduledDates(
                  topics,
                  settings?.daily_capacity_minutes ?? 120,
                  4
                );
                const scheduleByDay = getScheduleByDay(topics, schedule, 14);
                const selectedDay = scheduleByDay[selectedDayIndex];
                const topicMap = new Map(topics.map((t) => [t.id, t]));
                const DAYS_PER_PAGE = 7;
                const pageStart = Math.floor(selectedDayIndex / DAYS_PER_PAGE) * DAYS_PER_PAGE;
                const visibleDays = scheduleByDay.slice(pageStart, pageStart + DAYS_PER_PAGE);
                return (
                  <div className="rounded-xl border border-stone-200 bg-stone-50/50">
                    <div className="flex items-center gap-1 border-b border-stone-200 p-2">
                      <button
                        type="button"
                        onClick={() => setSelectedDayIndex((i) => Math.max(0, i - DAYS_PER_PAGE))}
                        disabled={pageStart === 0}
                        className="rounded-lg p-2 text-stone-600 hover:bg-stone-100 disabled:opacity-40 disabled:hover:bg-transparent"
                        aria-label="Previous week"
                      >
                        <ChevronLeft size={20} />
                      </button>
                      <div className="flex flex-1 justify-center gap-1">
                        {visibleDays.map((day, idx) => {
                          const i = pageStart + idx;
                          const isSelected = i === selectedDayIndex;
                          const hasTopics = day.topicIds.length > 0;
                          return (
                            <button
                              key={day.dateStr}
                              type="button"
                              onClick={() => setSelectedDayIndex(i)}
                              className={`min-w-16 shrink-0 cursor-pointer rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                                isSelected
                                  ? "bg-white text-stone-900 shadow-sm ring-1 ring-stone-200"
                                  : "text-stone-600 hover:bg-white/60 hover:text-stone-800"
                              } ${hasTopics ? "" : "opacity-70"}`}
                            >
                              {(day.label === "Today" || day.label === "Tomorrow") ? (
                                <span className="block truncate">{day.label}</span>
                              ) : (
                                <>
                                  <span className="block truncate text-xs font-normal text-stone-500">
                                    {day.label.split(", ")[0]}
                                  </span>
                                  <span className="block truncate">{day.label.split(", ")[1] ?? day.label}</span>
                                </>
                              )}
                              {hasTopics && (
                                <span className="mt-0.5 block text-xs font-normal text-amber-600">
                                  {day.topicIds.length}
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                      <button
                        type="button"
                        onClick={() => setSelectedDayIndex((i) => Math.min(13, i + DAYS_PER_PAGE))}
                        disabled={pageStart + DAYS_PER_PAGE >= scheduleByDay.length}
                        className="rounded-lg p-2 text-stone-600 hover:bg-stone-100 disabled:opacity-40 disabled:hover:bg-transparent"
                        aria-label="Next week"
                      >
                        <ChevronRight size={20} />
                      </button>
                    </div>
                    <div className="p-4">
                      {selectedDay.topicIds.length === 0 ? (
                        <p className="text-sm text-stone-500">
                          No topics scheduled for {selectedDay.label}.
                        </p>
                      ) : (
                        <ul className="space-y-2">
                          {selectedDay.topicIds.map((id) => {
                            const t = topicMap.get(id);
                            if (!t) return null;
                            return (
                              <li
                                key={id}
                                className="flex items-center justify-between rounded-lg border border-stone-200 bg-white px-4 py-3"
                              >
                                <span className="font-medium text-stone-800">{t.name}</span>
                                <span className="text-sm text-stone-500">
                                  {t.estimated_minutes ?? 60} min
                                </span>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>
                  </div>
                );
              })()}
            </div>
          )}

          <div className="mb-6">
            <h2 className="mb-3 text-sm font-medium text-stone-600">Add topic</h2>
            <div className="flex flex-wrap gap-2">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Two Pointers"
                className="rounded-lg border border-stone-200 px-4 py-2 text-stone-800 placeholder:text-stone-400"
              />
              <input
                type="number"
                min={1}
                max={480}
                value={newEstimate}
                onChange={(e) => {
                  const v = e.target.value;
                  setNewEstimate(v === "" ? "" : parseInt(v, 10) || 60);
                }}
                className="w-24 rounded-lg border border-stone-200 px-4 py-2 text-stone-800"
                title="Est. minutes"
              />
              <span className="flex items-center text-sm text-stone-500">min</span>
              <button
                disabled={adding || !newName.trim()}
                onClick={handleAdd}
                className="flex items-center gap-2 rounded-lg bg-stone-800 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50"
              >
                <Plus size={18} />
                Add
              </button>
            </div>
          </div>

          <div className="mb-6 rounded-lg border border-stone-200">
            <button
              type="button"
              onClick={() => setNeetcodeOpen(!neetcodeOpen)}
              className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-stone-700 hover:bg-stone-50"
            >
              <span>Import from NeetCode 150</span>
              {neetcodeOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
            </button>
            {neetcodeOpen && (
              <div className="border-t border-stone-200 px-4 py-3">
                {neetcodeLoading ? (
                  <p className="text-sm text-stone-500">Loading…</p>
                ) : neetcodeProblems.length === 0 ? (
                  <p className="text-sm text-stone-500">No problems available.</p>
                ) : (
                  <>
                    <p className="mb-3 text-xs text-stone-500">
                      Select problems to add as spaced repetition topics. Est. minutes: Easy 30, Medium 45, Hard 60.
                    </p>
                    {(() => {
                      const all150Selected = neetcodeProblems.length > 0 && neetcodeProblems.every((p) => neetcodeSelected.has(p.slug));
                      return (
                        <div className="mb-3 flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setNeetcodeSelected((prev) => {
                                const next = new Set(prev);
                                if (all150Selected) neetcodeProblems.forEach((p) => next.delete(p.slug));
                                else neetcodeProblems.forEach((p) => next.add(p.slug));
                                return next;
                              });
                            }}
                            className="rounded border border-stone-300 bg-stone-50 px-3 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-100"
                          >
                            {all150Selected ? "Deselect all 150" : "Select all 150"}
                          </button>
                          <span className="text-xs text-stone-500">
                            {neetcodeSelected.size} of {neetcodeProblems.length} selected
                          </span>
                        </div>
                      );
                    })()}
                    {(() => {
                      const byPattern = neetcodeProblems.reduce<Record<string, NeetcodeProblem[]>>(
                        (acc, p) => {
                          const k = p.pattern || "Other";
                          if (!acc[k]) acc[k] = [];
                          acc[k].push(p);
                          return acc;
                        },
                        {}
                      );
                      const patterns = Object.keys(byPattern).sort();
                      const PATTERNS_PER_PAGE = 2;
                      const totalPatternPages = Math.max(1, Math.ceil(patterns.length / PATTERNS_PER_PAGE));
                      const safePage = Math.min(neetcodePatternPage, totalPatternPages - 1);
                      const visiblePatterns = patterns.slice(
                        safePage * PATTERNS_PER_PAGE,
                        (safePage + 1) * PATTERNS_PER_PAGE
                      );
                      return (
                        <div className="space-y-4">
                          {visiblePatterns.map((pattern) => {
                            const probs = byPattern[pattern];
                            const allSelected = probs.every((p) => neetcodeSelected.has(p.slug));
                            return (
                              <div key={pattern}>
                                <div className="mb-2 flex items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setNeetcodeSelected((prev) => {
                                        const next = new Set(prev);
                                        if (allSelected) probs.forEach((p) => next.delete(p.slug));
                                        else probs.forEach((p) => next.add(p.slug));
                                        return next;
                                      });
                                    }}
                                    className="rounded border border-stone-300 px-2 py-1 text-xs font-medium text-stone-600 hover:bg-stone-100"
                                  >
                                    {allSelected ? "Deselect all" : "Select all"}
                                  </button>
                                  <span className="text-sm font-medium text-stone-600">{pattern}</span>
                                </div>
                                <ul className="space-y-1 pl-2">
                                  {probs.map((p) => (
                                    <li key={p.slug} className="flex items-center gap-2 text-sm">
                                      <input
                                        type="checkbox"
                                        checked={neetcodeSelected.has(p.slug)}
                                        onChange={() => {
                                          setNeetcodeSelected((prev) => {
                                            const next = new Set(prev);
                                            if (next.has(p.slug)) next.delete(p.slug);
                                            else next.add(p.slug);
                                            return next;
                                          });
                                        }}
                                        className="rounded border-stone-300"
                                      />
                                      <span className={p.difficulty === "Easy" ? "text-green-600" : p.difficulty === "Hard" ? "text-red-600" : "text-amber-600"}>
                                        {p.difficulty}
                                      </span>
                                      <span className="text-stone-800">{p.title}</span>
                                      {p.leetcode_url && (
                                        <a
                                          href={p.leetcode_url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-stone-400 hover:text-stone-600"
                                          aria-label="Open LeetCode"
                                        >
                                          <ExternalLink size={12} />
                                        </a>
                                      )}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            );
                          })}
                          {totalPatternPages > 1 && (
                            <div className="flex items-center justify-between border-t border-stone-200 pt-3">
                              <button
                                type="button"
                                onClick={() => setNeetcodePatternPage((p) => Math.max(0, p - 1))}
                                disabled={safePage === 0}
                                className="flex items-center gap-1 rounded border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-600 hover:bg-stone-100 disabled:opacity-40"
                              >
                                <ChevronLeft size={16} />
                                Previous
                              </button>
                              <span className="text-sm text-stone-500">
                                Page {safePage + 1} of {totalPatternPages}
                              </span>
                              <button
                                type="button"
                                onClick={() => setNeetcodePatternPage((p) => Math.min(totalPatternPages - 1, p + 1))}
                                disabled={safePage >= totalPatternPages - 1}
                                className="flex items-center gap-1 rounded border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-600 hover:bg-stone-100 disabled:opacity-40"
                              >
                                Next
                                <ChevronRight size={16} />
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })()}
                    <div className="mt-4 flex items-center gap-3">
                      <button
                        disabled={neetcodeImporting || neetcodeSelected.size === 0}
                        onClick={handleImportNeetcode}
                        className="flex items-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-500 disabled:opacity-50"
                      >
                        Add {neetcodeSelected.size} selected
                      </button>
                      {neetcodeSelected.size > 0 && (
                        <button
                          type="button"
                          onClick={() => setNeetcodeSelected(new Set())}
                          className="text-sm text-stone-500 hover:text-stone-700"
                        >
                          Clear selection
                        </button>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          <div>
            <h2 className="mb-3 text-sm font-medium text-stone-600">All topics</h2>
            {topics.length === 0 ? (
              <p className="text-stone-500">No topics yet. Add one above.</p>
            ) : (() => {
              const TOPICS_PER_PAGE = 15;
              const totalPages = Math.max(1, Math.ceil(topics.length / TOPICS_PER_PAGE));
              const safePage = Math.min(topicsPage, totalPages - 1);
              const visibleTopics = topics.slice(
                safePage * TOPICS_PER_PAGE,
                (safePage + 1) * TOPICS_PER_PAGE
              );
              const schedule = getCapacityAwareScheduledDates(
                topics,
                settings?.daily_capacity_minutes ?? 120,
                4
              );
              return (
                <>
                  <ul className="space-y-2">
                    {visibleTopics.map((t) => (
                      <li
                        key={t.id}
                        className="flex items-center justify-between gap-4 rounded-lg border border-stone-200 px-4 py-3"
                      >
                        <div className="min-w-0 flex-1">
                          <span className="font-medium text-stone-800">{t.name}</span>
                          <span className="ml-2 inline-flex items-center gap-1 text-sm text-stone-500">
                            <input
                              type="number"
                              min={1}
                              max={480}
                              value={editingEstimateId === t.id ? editingEstimateValue : t.estimated_minutes}
                              onChange={(e) => {
                                const v = e.target.value;
                                setEditingEstimateId(t.id);
                                setEditingEstimateValue(v === "" ? "" : parseInt(v, 10) || 60);
                              }}
                              onFocus={() => {
                                setEditingEstimateId(t.id);
                                setEditingEstimateValue(t.estimated_minutes);
                              }}
                              onBlur={() => {
                                if (editingEstimateId === t.id) {
                                  const val = editingEstimateValue === "" ? t.estimated_minutes : editingEstimateValue;
                                  handleUpdateEstimate(t.id, val, t.estimated_minutes);
                                }
                              }}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && editingEstimateId === t.id) {
                                  (e.target as HTMLInputElement).blur();
                                }
                              }}
                              className="w-14 rounded border border-stone-200 bg-white px-1.5 py-0.5 text-right text-stone-600 focus:border-stone-400 focus:outline-none focus:ring-1 focus:ring-stone-400"
                            />
                            min
                          </span>
                          <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-stone-500">
                            {(schedule.get(t.id) ?? []).map((label, i) => (
                              <span key={i} className="rounded bg-stone-100 px-1.5 py-0.5">
                                {label}
                              </span>
                            ))}
                          </div>
                        </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {deleteConfirmId === t.id ? (
                        <span className="flex items-center gap-1 text-sm">
                          <span className="text-stone-500">Delete?</span>
                          <button
                            onClick={() => handleDelete(t.id)}
                            className="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-500"
                          >
                            Delete
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(null)}
                            className="rounded border border-stone-300 px-2 py-1 text-xs font-medium text-stone-600 hover:bg-stone-100"
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <>
                          <button
                            onClick={() => handleRetire(t.id)}
                            className="rounded p-2 text-stone-400 hover:bg-green-50 hover:text-green-600"
                            title="Mark as done completely"
                          >
                            <CheckCircle size={16} />
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(t.id)}
                            className="rounded p-2 text-stone-400 hover:bg-red-50 hover:text-red-600"
                            title="Delete"
                          >
                            <Trash2 size={16} />
                          </button>
                        </>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              {totalPages > 1 && (
                <div className="mt-4 flex items-center justify-between border-t border-stone-200 pt-3">
                  <button
                    type="button"
                    onClick={() => setTopicsPage((p) => Math.max(0, p - 1))}
                    disabled={safePage === 0}
                    className="flex items-center gap-1 rounded border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-600 hover:bg-stone-100 disabled:opacity-40"
                  >
                    <ChevronLeft size={16} />
                    Previous
                  </button>
                  <span className="text-sm text-stone-500">
                    Page {safePage + 1} of {totalPages} ({topics.length} topics)
                  </span>
                  <button
                    type="button"
                    onClick={() => setTopicsPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={safePage >= totalPages - 1}
                    className="flex items-center gap-1 rounded border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-600 hover:bg-stone-100 disabled:opacity-40"
                  >
                    Next
                    <ChevronRight size={16} />
                  </button>
                </div>
              )}
                </>
              );
            })()}
          </div>
        </div>
      </div>
    </div>
  );
}
