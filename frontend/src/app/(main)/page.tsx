"use client";

import { useState, useEffect } from "react";
import { Play, RotateCcw, BookOpen, Check, ThumbsUp, Minus, ThumbsDown, SkipForward, Target, CheckCircle2, Clock, CalendarClock } from "lucide-react";
import Link from "next/link";
import { usePomodoro } from "@/contexts/PomodoroContext";
import { srApi, type SRTopic } from "@/lib/api";

export default function PomodoroPage() {
  const {
    mode,
    minutes,
    seconds,
    running,
    paused,
    completedToday,
    streak,
    project,
    error,
    loading,
    timerReady,
    settings,
    effectiveWorkMinutes,
    setMode,
    setProject,
    setWorkDurationOverride,
    runPomodoro,
    pendingDifficultyPrompt,
    submitDifficulty,
    dismissDifficultyPrompt,
    saveSettings,
  } = usePomodoro();

  const currentModeMins =
    mode === "work" ? effectiveWorkMinutes : mode === "short" ? settings.short_break_minutes : settings.long_break_minutes;
  const [editingValue, setEditingValue] = useState<string | null>(null);
  const displayValue = editingValue !== null ? editingValue : String(currentModeMins);

  useEffect(() => setEditingValue(null), [mode]);
  const [srTopics, setSrTopics] = useState<SRTopic[]>([]);
  const [dueToday, setDueToday] = useState<
    { id: number; name: string; estimated_minutes: number; completed?: boolean }[]
  >([]);
  const [taskSelect, setTaskSelect] = useState<string>("");
  const [skipModalTopic, setSkipModalTopic] = useState<{ id: number; name: string } | null>(null);

  const refreshDueToday = () => {
    srApi.getDueToday().then((r) => setDueToday(r.topics)).catch(() => {});
  };

  useEffect(() => {
    srApi.listTopics().then((r) => setSrTopics(r.topics)).catch(() => {});
    refreshDueToday();
  }, [streak]);

  const taskSelectValue =
    project && srTopics.some((t) => t.name === project)
      ? project
      : project
        ? "__custom__"
        : "";

  const totalSec =
    (mode === "work"
      ? effectiveWorkMinutes
      : mode === "short"
        ? settings.short_break_minutes
        : settings.long_break_minutes) * 60;
  const progress = totalSec > 0 ? 1 - (minutes * 60 + seconds) / totalSec : 0;

  return (
    <>
      <div className="rounded-2xl border border-stone-200 bg-white p-8 shadow-sm">
        <h1 className="mb-6 text-xl font-semibold text-stone-800">Pomodoro Timer</h1>

        {!timerReady ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-stone-300 border-t-stone-600" />
          </div>
        ) : (
        <>
        <div className="mb-6 flex gap-2">
          {(["work", "short", "long"] as const).map((m) => (
            <button
              key={m}
              onClick={() => {
                if (!running && !paused) {
                  setMode(m);
                }
              }}
              disabled={running || paused}
              className={`flex-1 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                mode === m
                  ? "bg-stone-800 text-white"
                  : "bg-stone-100 text-stone-600 hover:bg-stone-200"
              } ${running ? "opacity-70" : ""}`}
            >
              {m === "work" ? "Work" : m === "short" ? "Short Break" : "Long Break"}
            </button>
          ))}
        </div>

        <div className="mb-4 text-center">
          {running || paused ? (
            <div className="rounded-xl border-2 border-transparent bg-stone-50 px-6 py-3 font-mono text-6xl font-bold tabular-nums text-stone-800">
              {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
            </div>
          ) : (
            <div className="flex items-baseline justify-center gap-1">
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                value={displayValue}
                onChange={(e) => {
                  const raw = e.target.value.replace(/\D/g, "");
                  setEditingValue(raw === "" ? "" : raw);
                }}
                onFocus={() => setEditingValue(String(currentModeMins))}
                onBlur={() => {
                  if (editingValue !== null) {
                    const parsed = parseInt(editingValue, 10);
                    const max = mode === "work" ? 1440 : 60;
                    const v = Number.isNaN(parsed) || parsed < 1 ? 1 : Math.min(max, parsed);
                    saveSettings({
                      work_duration_minutes: mode === "work" ? v : settings.work_duration_minutes,
                      short_break_minutes: mode === "short" ? v : settings.short_break_minutes,
                      long_break_minutes: mode === "long" ? v : settings.long_break_minutes,
                    });
                    setEditingValue(null);
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                }}
                className="w-28 rounded-xl border-2 border-stone-200 bg-stone-50 px-4 py-2 text-center text-5xl font-bold tabular-nums text-stone-800 outline-none transition-colors placeholder:text-stone-400 focus:border-amber-500 focus:bg-white focus:ring-2 focus:ring-amber-500/20"
                placeholder="0"
                aria-label={`${mode === "work" ? "Work" : mode === "short" ? "Short break" : "Long break"} duration (minutes)`}
              />
              <span className="text-4xl font-bold tabular-nums text-stone-500">:00</span>
            </div>
          )}
        </div>

        <div className="mb-6 h-1.5 w-full overflow-hidden rounded-full bg-stone-200">
          <div
            className="h-full bg-stone-600 transition-all duration-300"
            style={{ width: `${progress * 100}%` }}
          />
        </div>

        <div className="mb-4">
          <label htmlFor="task" className="mb-1 block text-sm font-medium text-stone-600">
            Task (optional)
          </label>
          <div className="space-y-2">
            <select
              id="task"
              value={taskSelectValue || taskSelect}
              onChange={(e) => {
                const v = e.target.value;
                setTaskSelect(v);
                if (v === "__custom__" || !v) {
                  setProject(v === "__custom__" ? "" : "");
                  setWorkDurationOverride(null);
                } else {
                  setProject(v);
                  const topic = srTopics.find((t) => t.name === v);
                  setWorkDurationOverride(topic ? topic.estimated_minutes : null);
                  if (!running) setMode("work");
                }
              }}
              disabled={running || paused}
              className="w-full rounded-lg border border-stone-200 bg-white px-4 py-2 text-stone-800 focus:border-stone-400 focus:outline-none focus:ring-1 focus:ring-stone-400 disabled:opacity-70"
            >
              <option value="">— None —</option>
              {srTopics.map((t) => (
                <option key={t.id} value={t.name}>
                  {t.name} (~{t.estimated_minutes} min)
                </option>
              ))}
              <option value="__custom__">Custom...</option>
            </select>
            {(taskSelectValue === "__custom__" || taskSelect === "__custom__") && (
              <input
                type="text"
                value={project}
                onChange={(e) => setProject(e.target.value)}
                placeholder="e.g. LeetCode, Writing"
                disabled={running || paused}
                className="w-full rounded-lg border border-stone-200 bg-white px-4 py-2 text-stone-800 placeholder:text-stone-400 focus:border-stone-400 focus:outline-none focus:ring-1 focus:ring-stone-400 disabled:opacity-70"
              />
            )}
          </div>
        </div>

        <div className="mb-6 overflow-hidden rounded-xl border border-stone-200 bg-gradient-to-br from-stone-50 to-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm font-semibold text-stone-700">
              <Target size={16} className="text-amber-500" />
              Today&apos;s practice
            </span>
            <Link
              href="/practice"
              className="text-sm text-stone-500 transition-colors hover:text-stone-700"
            >
              Manage →
            </Link>
          </div>
          {dueToday.length > 0 ? (
            <ul className="space-y-2">
              {dueToday.map((t) => (
                <li key={t.id} className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setTaskSelect(t.name);
                      setProject(t.name);
                      setWorkDurationOverride(t.estimated_minutes);
                      if (!running) setMode("work");
                    }}
                    disabled={running || paused}
                    className={`group flex min-w-0 flex-1 items-center gap-3 rounded-xl border px-4 py-3.5 text-left transition-all duration-200 disabled:opacity-70 ${
                      t.completed
                        ? "border-emerald-200 bg-gradient-to-r from-emerald-50 to-green-50 shadow-sm"
                        : project === t.name
                          ? "border-amber-500 bg-amber-500 shadow-md ring-2 ring-amber-400/40"
                          : "border-stone-200 bg-white text-stone-800 shadow-sm hover:border-stone-300 hover:shadow transition-shadow"
                    } ${!t.completed && project !== t.name ? "hover:bg-stone-50" : ""}`}
                  >
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors ${
                        t.completed
                          ? "bg-emerald-100 text-emerald-600"
                          : project === t.name
                            ? "bg-white/25 text-white"
                            : "bg-stone-100 text-stone-600 group-hover:bg-stone-200"
                      }`}
                    >
                      {t.completed ? (
                        <CheckCircle2 size={20} strokeWidth={2.5} />
                      ) : (
                        <Target size={20} strokeWidth={2} />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <span
                        className={`font-semibold ${
                          t.completed ? "text-emerald-800" : project === t.name ? "text-white" : "text-stone-800"
                        }`}
                      >
                        {t.name}
                      </span>
                      <span
                        className={`ml-2 inline-flex items-center gap-1 text-sm ${
                          t.completed
                            ? "text-emerald-600"
                            : project === t.name
                              ? "text-amber-100"
                              : "text-stone-500"
                        }`}
                      >
                        <Clock size={14} />
                        {t.estimated_minutes} min
                      </span>
                    </div>
                  </button>
                  {!t.completed && (
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          srApi.skipToday(t.id).then((r) => setDueToday(r.topics)).catch(() => {});
                        }}
                        title="Skip today"
                        className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white px-2.5 py-1.5 text-xs font-medium text-stone-500 shadow-sm transition-all hover:border-stone-300 hover:bg-stone-50 hover:text-stone-700"
                      >
                        <SkipForward size={14} />
                        Skip
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSkipModalTopic({ id: t.id, name: t.name });
                        }}
                        title="Skip and reschedule"
                        className="flex items-center gap-1 rounded-lg border border-stone-200 bg-white px-2.5 py-1.5 text-xs font-medium text-stone-500 shadow-sm transition-all hover:border-amber-200 hover:bg-amber-50 hover:text-amber-700"
                      >
                        <CalendarClock size={14} />
                        Later
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-stone-500">
              Nothing due today.{" "}
              <Link href="/practice" className="text-stone-600 hover:text-stone-800 underline">
                Add topics in Practice
              </Link>
            </p>
          )}
        </div>

        <div className="mb-6 flex items-center justify-center gap-3">
          <button
            disabled={loading}
            onClick={() =>
              running ? runPomodoro("pause") : paused ? runPomodoro("resume") : runPomodoro("start")
            }
            className="flex items-center gap-2 rounded-lg bg-stone-800 px-6 py-3 font-medium text-white hover:bg-stone-700 disabled:opacity-50"
          >
            <Play size={20} />
            {running ? "Pause" : paused ? "Continue" : "Start"}
          </button>
          <button
            disabled={loading}
            onClick={() => runPomodoro("stop")}
            className="rounded-full p-3 text-stone-500 hover:bg-stone-100 hover:text-stone-700"
            title="Reset"
          >
            <RotateCcw size={22} />
          </button>
        </div>

        {error && (
          <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
        )}

        <div className="mb-2 flex flex-wrap items-center justify-center gap-4 text-stone-600">
          <span>
            Completed Pomodoros Today: <span className="font-bold text-stone-800">{completedToday}</span>
          </span>
          {streak && (streak.current_streak > 0 || streak.longest_streak > 0) && (
            <span title="Practice streak (consecutive days with completed tasks)">
              🔥 <span className="font-bold text-stone-800">{streak.current_streak}</span>
              {streak.longest_streak > streak.current_streak && (
                <span className="text-stone-500"> (best: {streak.longest_streak})</span>
              )}
            </span>
          )}
        </div>

        <p className="text-center text-sm text-stone-500">
          Take regular breaks to maintain focus and productivity.
          <br />
          Use the chat feature to get AI-powered productivity tips!
        </p>
        </>
        )}
      </div>

      {pendingDifficultyPrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
            <h2 className="mb-1 text-lg font-semibold text-stone-800">How did it go?</h2>
            <p className="mb-4 text-sm text-stone-500">
              Rate your practice for &quot;{pendingDifficultyPrompt.project}&quot;
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => submitDifficulty("hard")}
                className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-sm text-stone-600 hover:bg-stone-50"
              >
                <ThumbsDown size={18} />
                Hard
              </button>
              <button
                onClick={() => submitDifficulty("medium")}
                className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-sm text-stone-600 hover:bg-stone-50"
              >
                <Minus size={18} />
                Medium
              </button>
              <button
                onClick={() => submitDifficulty("easy")}
                className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-sm text-stone-600 hover:bg-stone-50"
              >
                <ThumbsUp size={18} />
                Easy
              </button>
            </div>
            <button
              onClick={dismissDifficultyPrompt}
              className="mt-3 w-full rounded-lg py-2 text-sm text-stone-500 hover:bg-stone-50 hover:text-stone-700"
            >
              Skip
            </button>
          </div>
        </div>
      )}

      {skipModalTopic && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-lg">
            <h2 className="mb-1 text-lg font-semibold text-stone-800">Skip &quot;{skipModalTopic.name}&quot;</h2>
            <p className="mb-4 text-sm text-stone-500">
              When do you want this to show up again?
            </p>
            <div className="flex flex-col gap-2">
              {([1, 3, 7, 14] as const).map((days) => (
                <button
                  key={days}
                  onClick={() => {
                    srApi
                      .skipUntil(skipModalTopic.id, days)
                      .then((r) => {
                        setDueToday(r.topics);
                        setSkipModalTopic(null);
                      })
                      .catch(() => {});
                  }}
                  className="rounded-lg border border-stone-200 px-4 py-2.5 text-left text-sm text-stone-700 hover:bg-stone-50"
                >
                  {days === 1 ? "1 day" : days === 3 ? "3 days" : days === 7 ? "1 week" : "2 weeks"}
                </button>
              ))}
            </div>
            <button
              onClick={() => {
                srApi
                  .retireTopic(skipModalTopic.id)
                  .then((r) => {
                    setDueToday(r.topics);
                    setSkipModalTopic(null);
                    srApi.listTopics().then((list) => setSrTopics(list.topics)).catch(() => {});
                  })
                  .catch(() => {});
              }}
              className="mt-2 rounded-lg border border-stone-200 px-4 py-2.5 text-left text-sm text-green-700 hover:bg-green-50"
            >
              Mark as done completely
            </button>
            <button
              onClick={() => setSkipModalTopic(null)}
              className="mt-3 w-full rounded-lg py-2 text-sm text-stone-500 hover:bg-stone-50 hover:text-stone-700"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

    </>
  );
}
