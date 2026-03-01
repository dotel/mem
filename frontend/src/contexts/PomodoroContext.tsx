"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  api,
  analyticsApi,
  srApi,
  type DailyStats,
  type WeekStats,
} from "@/lib/api";

const DEFAULT_WORK = 25;
const DEFAULT_SHORT = 5;
const DEFAULT_LONG = 15;

export type Mode = "work" | "short" | "long";
export type AnalyticsTab = "day" | "week" | "month";

type PomodoroState = {
  mode: Mode;
  minutes: number;
  seconds: number;
  running: boolean;
  paused: boolean;
  completedToday: number;
  project: string;
};

export type HistoryEntry = { date: string; data: DailyStats | null };

type AnalyticsState = {
  todayData: DailyStats | null;
  weekData: WeekStats | null;
  monthData: {
    total_minutes: number;
    total_sessions: number;
    active_days: number;
  } | null;
  historyData: HistoryEntry[];
  analyticsLoading: boolean;
};

export type PomodoroSettings = {
  work_duration_minutes: number;
  short_break_minutes: number;
  long_break_minutes: number;
};

export type Streak = { current_streak: number; longest_streak: number };

export type PendingDifficultyPrompt = { project: string } | null;

type PomodoroContextValue = PomodoroState &
  AnalyticsState & {
    error: string | null;
    loading: boolean;
    analyticsTab: AnalyticsTab;
    settings: PomodoroSettings;
    timerReady: boolean;
    effectiveWorkMinutes: number;
    streak: Streak | null;
    pendingDifficultyPrompt: PendingDifficultyPrompt;
    setMode: (m: Mode) => void;
    setProject: (p: string) => void;
    setWorkDurationOverride: (mins: number | null) => void;
    setAnalyticsTab: (t: AnalyticsTab) => void;
    runPomodoro: (action: "start" | "pause" | "resume" | "stop") => Promise<void>;
    refreshStatus: () => Promise<void>;
    refreshAnalytics: () => Promise<void>;
    refreshStreak: () => Promise<void>;
    saveSettings: (s: PomodoroSettings) => Promise<void>;
    submitDifficulty: (difficulty: "easy" | "medium" | "hard") => Promise<void>;
    dismissDifficultyPrompt: () => void;
  };

const PomodoroContext = createContext<PomodoroContextValue | null>(null);

function playCompletionSound() {
  try {
    const Ctx = globalThis.AudioContext || (globalThis as unknown as { webkitAudioContext: new () => AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    osc.type = "sine";
    gain.gain.value = 0.2;
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.15);
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.frequency.value = 1100;
    osc2.type = "sine";
    gain2.gain.value = 0.15;
    osc2.start(ctx.currentTime + 0.15);
    osc2.stop(ctx.currentTime + 0.5);
  } catch {
    /* fallback: no sound */
  }
}

export function PomodoroProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<PomodoroSettings>({
    work_duration_minutes: DEFAULT_WORK,
    short_break_minutes: DEFAULT_SHORT,
    long_break_minutes: DEFAULT_LONG,
  });
  const [mode, setModeState] = useState<Mode>("work");
  const [minutes, setMinutes] = useState(DEFAULT_WORK);
  const [seconds, setSeconds] = useState(0);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [completedToday, setCompletedToday] = useState(0);
  const [project, setProject] = useState("");
  const [workDurationOverride, setWorkDurationOverride] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pomodoroLoading, setPomodoroLoading] = useState(false);
  const [analyticsTab, setAnalyticsTab] = useState<AnalyticsTab>("day");
  const [todayData, setTodayData] = useState<DailyStats | null>(null);
  const [weekData, setWeekData] = useState<WeekStats | null>(null);
  const [monthData, setMonthData] = useState<{
    total_minutes: number;
    total_sessions: number;
    active_days: number;
  } | null>(null);
  const [historyData, setHistoryData] = useState<HistoryEntry[]>([]);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [timerReady, setTimerReady] = useState(false);
  const [streak, setStreak] = useState<Streak | null>(null);
  const [pendingDifficultyPrompt, setPendingDifficultyPrompt] =
    useState<PendingDifficultyPrompt>(null);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const startInProgressRef = useRef(false);
  const runningRef = useRef(running);
  runningRef.current = running;

  const effectiveWorkMinutes = workDurationOverride ?? settings.work_duration_minutes;

  // Sync timer display when work duration override changes (e.g. task selected)
  // Only when idle — don't reset when paused (we must preserve remaining time)
  useEffect(() => {
    if (mode === "work" && !running && !paused) {
      setMinutes(effectiveWorkMinutes);
      setSeconds(0);
    }
  }, [effectiveWorkMinutes, mode, running, paused]);

  const setMode = useCallback(
    (m: Mode) => {
      const mins =
        m === "work"
          ? effectiveWorkMinutes
          : m === "short"
            ? settings.short_break_minutes
            : settings.long_break_minutes;
      setModeState(m);
      setMinutes(mins);
      setSeconds(0);
    },
    [settings, effectiveWorkMinutes]
  );

  const refreshStatus = useCallback(async () => {
    try {
      await api.getStatus();
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to get status");
    }
  }, []);

  const refreshStreak = useCallback(async () => {
    try {
      const s = await srApi.getStreak();
      setStreak(s);
    } catch {
      setStreak(null);
    }
  }, []);

  const submitDifficulty = useCallback(
    async (difficulty: "easy" | "medium" | "hard") => {
      const p = pendingDifficultyPrompt;
      setPendingDifficultyPrompt(null);
      if (!p?.project) return;
      try {
        const res = await srApi.completeTask(p.project, difficulty);
        setStreak(res.streak);
      } catch {
        /* ignore */
      }
    },
    [pendingDifficultyPrompt]
  );

  const dismissDifficultyPrompt = useCallback(() => {
    const p = pendingDifficultyPrompt;
    setPendingDifficultyPrompt(null);
    if (!p?.project) return;
    srApi.completeTask(p.project).then((res) => setStreak(res.streak)).catch(() => { });
  }, [pendingDifficultyPrompt]);

  const refreshAnalytics = useCallback(async () => {
    setAnalyticsLoading(true);
    try {
      const [todayRes, weekRes, historyRes] = await Promise.all([
        analyticsApi.today(),
        analyticsApi.week(),
        analyticsApi.history(30),
      ]);
      setTodayData(todayRes.data);
      setCompletedToday(todayRes.data?.completed_sessions ?? 0);
      setWeekData(weekRes);
      const entries = historyRes.history.filter((e) => e.data);
      const total = entries.reduce(
        (acc, e) => ({
          minutes: acc.minutes + (e.data?.total_work_minutes ?? 0),
          sessions: acc.sessions + (e.data?.completed_sessions ?? 0),
        }),
        { minutes: 0, sessions: 0 }
      );
      setMonthData({
        total_minutes: total.minutes,
        total_sessions: total.sessions,
        active_days: entries.length,
      });
      setHistoryData(historyRes.history);
    } catch {
      setTodayData(null);
      setWeekData(null);
      setMonthData(null);
      setHistoryData([]);
    } finally {
      setAnalyticsLoading(false);
    }
  }, []);

  const saveSettings = useCallback(async (s: PomodoroSettings) => {
    try {
      const updated = await api.updatePomodoroSettings({
        work_duration_minutes: s.work_duration_minutes,
        short_break_minutes: s.short_break_minutes,
        long_break_minutes: s.long_break_minutes,
      });
      setSettings({
        work_duration_minutes: updated.work_duration_minutes,
        short_break_minutes: updated.short_break_minutes,
        long_break_minutes: updated.long_break_minutes,
      });
      if (!running) {
        const mins =
          mode === "work"
            ? updated.work_duration_minutes
            : mode === "short"
              ? updated.short_break_minutes
              : updated.long_break_minutes;
        setMinutes(mins);
        setSeconds(0);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save settings");
    }
  }, [mode, running]);

  // Sync from backend on mount (e.g. after tab switch or refresh)
  useEffect(() => {
    let cancelled = false;
    async function sync() {
      try {
        const [st, s] = await Promise.all([api.getPomodoroStatus(), api.getPomodoroSettings()]);
        if (cancelled) return;
        if (startInProgressRef.current) return;
        setSettings({
          work_duration_minutes: s.work_duration_minutes ?? DEFAULT_WORK,
          short_break_minutes: s.short_break_minutes ?? DEFAULT_SHORT,
          long_break_minutes: s.long_break_minutes ?? DEFAULT_LONG,
        });
        const workDur = s.work_duration_minutes ?? DEFAULT_WORK;
        const shortDur = s.short_break_minutes ?? DEFAULT_SHORT;
        const longDur = s.long_break_minutes ?? DEFAULT_LONG;
        if (st.running || st.paused) {
          const mins = Math.floor(st.remaining_ms / 60000);
          const secs = Math.floor((st.remaining_ms % 60000) / 1000);
          setMinutes(mins);
          setSeconds(secs);
          setRunning(st.running);
          const modeFromDuration: Mode =
            st.duration_minutes === longDur
              ? "long"
              : st.duration_minutes === shortDur
                ? "short"
                : "work";
          setModeState(modeFromDuration);
          setProject(st.project || "");
        } else if (!runningRef.current) {
          const modeFromDuration: Mode =
            st.mode === "short"
              ? "short"
              : st.mode === "long"
                ? "long"
                : "work";
          const mins = Math.max(1,
            modeFromDuration === "work"
              ? workDur
              : modeFromDuration === "short"
                ? shortDur
                : longDur
          );
          setModeState(modeFromDuration);
          setMinutes(mins);
          setSeconds(0);
          setRunning(false);
          setPaused(false);
        }
        await refreshStatus();
      } catch {
        /* ignore */
      } finally {
        if (!cancelled) setTimerReady(true);
      }
    }
    sync();
    return () => {
      cancelled = true;
    };
  }, [refreshStatus]);

  // Re-sync when tab becomes visible (e.g. user switched from another tab where timer was started)
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      api.getPomodoroStatus().then((st) => {
        const s = settingsRef.current;
        const workDur = s.work_duration_minutes;
        const shortDur = s.short_break_minutes;
        const longDur = s.long_break_minutes;
        if (st.running || st.paused) {
          const mins = Math.floor(st.remaining_ms / 60000);
          const secs = Math.floor((st.remaining_ms % 60000) / 1000);
          setMinutes(mins);
          setSeconds(secs);
          setRunning(st.running);
          setPaused(st.paused);
          const modeFromDuration: Mode =
            st.duration_minutes === longDur
              ? "long"
              : st.duration_minutes === shortDur
                ? "short"
                : "work";
          setModeState(modeFromDuration);
          setProject(st.project || "");
        } else if (!st.running && !st.paused) {
          setRunning(false);
          setPaused(false);
          const modeFromDuration: Mode =
            st.mode === "short" ? "short" : st.mode === "long" ? "long" : "work";
          const mins =
            modeFromDuration === "work"
              ? workDur
              : modeFromDuration === "short"
                ? shortDur
                : longDur;
          setModeState(modeFromDuration);
          setMinutes(mins);
          setSeconds(0);
        }
      }).catch(() => { });
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  // SSE connection for real-time timer completion
  useEffect(() => {
    const url = api.getPomodoroEventsUrl();
    const eventSource = new EventSource(url);

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "ping") return;

        const typeName = data.type_name || data.type;
        const s = settingsRef.current;
        if (typeName === "pomodoro_complete") {
          playCompletionSound();
          setRunning(false);
          setPaused(false);
          const phase = data.data?.phase;
          const project = data.data?.project;
          if (phase === "work" && project) {
            setPendingDifficultyPrompt({ project });
          }
          const mins =
            phase === "work"
              ? s.work_duration_minutes
              : phase === "long"
                ? s.long_break_minutes
                : s.short_break_minutes;
          setMinutes(mins);
          setSeconds(0);
          refreshStatus();
          refreshAnalytics();
        } else if (typeName === "pomodoro_cancel") {
          setRunning(false);
          setPaused(false);
          setMinutes(s.work_duration_minutes);
          setSeconds(0);
          refreshStatus();
          refreshAnalytics();
        }
      } catch {
        /* ignore */
      }
    };

    return () => {
      eventSource.close();
    };
  }, [refreshStatus, refreshAnalytics]);

  // Local countdown (runs while layout is mounted)
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => {
      setSeconds((s) => {
        if (s > 0) return s - 1;
        setMinutes((m) => {
          if (m > 0) return m - 1;
          setRunning(false);
          return 0;
        });
        return 59;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [running]);

  // Poll backend while running to stay in sync (fixes "needs refresh" when local state lags)
  useEffect(() => {
    if (!running) return;
    const poll = () => {
      api.getPomodoroStatus().then((st) => {
        if (st.running || st.paused) {
          const backendMins = Math.floor(st.remaining_ms / 60000);
          const backendSecs = Math.floor((st.remaining_ms % 60000) / 1000);
          setMinutes(backendMins);
          setSeconds(backendSecs);
          setPaused(st.paused);
        }
      }).catch(() => { });
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, [running]);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    refreshStreak();
  }, [refreshStreak]);

  useEffect(() => {
    refreshAnalytics();
  }, [refreshAnalytics, completedToday]);

  const runPomodoro = useCallback(
    async (action: "start" | "pause" | "resume" | "stop") => {
      setPomodoroLoading(true);
      setError(null);
      try {
        if (action === "start") {
          const mins =
            mode === "work"
              ? effectiveWorkMinutes
              : mode === "short"
                ? settings.short_break_minutes
                : settings.long_break_minutes;
          startInProgressRef.current = true;
          try {
            await api.pomodoroStart({
              duration_minutes: mins,
              project: mode === "work" ? (project.trim() || undefined) : undefined,
            });
            const st = await api.getPomodoroStatus();
            if (st.running || st.paused) {
              const backendMins = Math.floor(st.remaining_ms / 60000);
              const backendSecs = Math.floor((st.remaining_ms % 60000) / 1000);
              setMinutes(Math.max(1, backendMins));
              setSeconds(backendMins > 0 ? backendSecs : 0);
              setRunning(st.running);
              setPaused(st.paused);
            } else {
              setMinutes(Math.max(1, mins));
              setSeconds(0);
              setRunning(true);
              setPaused(false);
          }
          } finally {
            // Delay clearing so any in-flight sync (started before our setState) sees the ref and skips overwriting
            setTimeout(() => { startInProgressRef.current = false; }, 2000);
          }
        } else if (action === "pause") {
          await api.pomodoroPause();
          setRunning(false);
          setPaused(true);
        } else if (action === "resume") {
          await api.pomodoroResume();
          setRunning(true);
          setPaused(false);
          const st = await api.getPomodoroStatus();
          if (st.running || st.paused) {
            setMinutes(Math.floor(st.remaining_ms / 60000));
            setSeconds(Math.floor((st.remaining_ms % 60000) / 1000));
          }
        } else {
          await api.pomodoroStop();
          setRunning(false);
          setPaused(false);
          const mins =
            mode === "work"
              ? effectiveWorkMinutes
              : mode === "short"
                ? settings.short_break_minutes
                : settings.long_break_minutes;
          setMinutes(mins);
          setSeconds(0);
        }
        await refreshStatus();
        await refreshAnalytics();
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed";
        setError(msg);
        if (msg.includes("already running")) {
          api.getPomodoroStatus().then((st) => {
            if (st.running || st.paused) {
              const mins = Math.floor(st.remaining_ms / 60000);
              const secs = Math.floor((st.remaining_ms % 60000) / 1000);
              setMinutes(mins);
              setSeconds(secs);
              setRunning(st.running);
              setPaused(st.paused);
              const modeFromDuration: Mode =
                st.duration_minutes === settings.long_break_minutes
                  ? "long"
                  : st.duration_minutes === settings.short_break_minutes
                    ? "short"
                    : "work";
              setModeState(modeFromDuration);
              setProject(st.project || "");
              setError(null);
            }
          }).catch(() => { });
        }
      } finally {
        setPomodoroLoading(false);
      }
    },
    [mode, project, settings, effectiveWorkMinutes, refreshStatus, refreshAnalytics]
  );

  const value: PomodoroContextValue = {
    mode,
    minutes,
    seconds,
    running,
    paused,
    completedToday,
    project,
    error,
    loading: pomodoroLoading,
    analyticsTab,
    timerReady,
    effectiveWorkMinutes,
    streak,
    pendingDifficultyPrompt,
    todayData,
    weekData,
    monthData,
    historyData,
    analyticsLoading,
    settings,
    setMode,
    setProject,
    setWorkDurationOverride,
    setAnalyticsTab,
    runPomodoro,
    refreshStatus,
    refreshAnalytics,
    refreshStreak,
    saveSettings,
    submitDifficulty,
    dismissDifficultyPrompt,
  };

  return (
    <PomodoroContext.Provider value={value}>{children}</PomodoroContext.Provider>
  );
}

export function usePomodoro() {
  const ctx = useContext(PomodoroContext);
  if (!ctx) throw new Error("usePomodoro must be used within PomodoroProvider");
  return ctx;
}
