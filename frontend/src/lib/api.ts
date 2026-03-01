const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8765";

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const t = localStorage.getItem("hari_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function fetchApi<T>(
  path: string,
  options?: RequestInit & { params?: Record<string, string> }
): Promise<T> {
  const { params, ...init } = options ?? {};
  const url = new URL(path, API_BASE);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  }
  const res = await fetch(url.toString(), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...init.headers,
    } as HeadersInit,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export type StatusResponse = { status: string; message: string };
export type CommandResponse = { version?: number; status: string; message: string };
export type PomodoroResponse = { status: string; message: string; version?: number };

export const api = {
  getStatus: () => fetchApi<StatusResponse>("/api/status"),
  sendCommand: (command: string, history?: { role: string; text: string }[]) =>
    fetchApi<CommandResponse>("/api/command", {
      method: "POST",
      body: JSON.stringify({ command, ...(history?.length ? { history } : {}) }),
    }),
  /** Stream command response; calls onChunk for each token, returns final status. */
  async sendCommandStream(
    command: string,
    onChunk: (text: string) => void,
    history?: { role: string; text: string }[]
  ): Promise<{ status: string; message?: string }> {
    const url = new URL("/api/command/stream", API_BASE);
    const res = await fetch(url.toString(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ command, ...(history?.length ? { history } : {}) }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error((err as { detail?: string }).detail || res.statusText);
    }
    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");
    const decoder = new TextDecoder();
    let buffer = "";
    let finalStatus = "ok";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6)) as {
              chunk?: string;
              done?: boolean;
              status?: string;
            };
            if (data.chunk) onChunk(data.chunk);
            if (data.done && data.status) finalStatus = data.status;
          } catch {
            /* ignore parse errors */
          }
        }
      }
    }
    if (buffer.startsWith("data: ")) {
      try {
        const data = JSON.parse(buffer.slice(6)) as { done?: boolean; status?: string };
        if (data.done && data.status) finalStatus = data.status;
      } catch {
        /* ignore */
      }
    }
    return { status: finalStatus };
  },
  pomodoroStart: (body?: { duration_minutes?: number; project?: string }) =>
    fetchApi<PomodoroResponse>("/api/pomodoro/start", {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
  pomodoroPause: () =>
    fetchApi<PomodoroResponse>("/api/pomodoro/pause", { method: "POST" }),
  pomodoroResume: () =>
    fetchApi<PomodoroResponse>("/api/pomodoro/resume", { method: "POST" }),
  pomodoroStop: () =>
    fetchApi<PomodoroResponse>("/api/pomodoro/stop", { method: "POST" }),
  getPomodoroStatus: () =>
    fetchApi<PomodoroStructuredStatus>("/api/pomodoro/status"),
  getPomodoroSettings: () =>
    fetchApi<PomodoroSettings>("/api/pomodoro/settings"),
  updatePomodoroSettings: (body: {
    work_duration_minutes?: number;
    short_break_minutes?: number;
    long_break_minutes?: number;
    sessions_until_long_break?: number;
  }) =>
    fetchApi<PomodoroSettings>("/api/pomodoro/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  getPomodoroEventsUrl: () => {
    const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8765";
    const url = new URL("/api/pomodoro/events", base);
    return url.toString();
  },
};

export type PomodoroStructuredStatus = {
  phase: string;
  mode: "work" | "short" | "long" | "paused" | "idle";
  running: boolean;
  paused: boolean;
  remaining_ms: number;
  duration_minutes: number;
  session_count: number;
  project: string;
  work_duration_minutes?: number;
  short_break_minutes?: number;
  long_break_minutes?: number;
};

export type PomodoroSettings = {
  work_duration_minutes: number;
  short_break_minutes: number;
  long_break_minutes: number;
  sessions_until_long_break?: number;
};

export type DailyStats = {
  date?: string;
  total_work_minutes?: number;
  total_break_minutes?: number;
  completed_sessions?: number;
  incomplete_sessions?: number;
  total_focus_score?: number;
};
export type WeekStats = {
  week_start: string;
  week_end: string;
  total_minutes: number;
  total_sessions: number;
  avg_daily_minutes: number;
  best_day_minutes: number;
  active_days: number;
};
export type HistoryEntry = { date: string; data: DailyStats | null };

export const analyticsApi = {
  today: () =>
    fetchApi<{ date: string; data: DailyStats | null }>("/api/analytics/today"),
  week: () => fetchApi<WeekStats>("/api/analytics/week"),
  history: (days: number) =>
    fetchApi<{ history: HistoryEntry[] }>("/api/analytics/history", {
      params: { days: String(days) },
    }),
};

export type User = {
  id: number;
  name: string;
  email: string;
  created_at: string;
  updated_at: string;
};

export const usersApi = {
  list: () => fetchApi<{ users: User[] }>("/api/users"),
  get: (id: number) => fetchApi<User>(`/api/users/${id}`),
  create: (data: { name: string; email?: string }) =>
    fetchApi<User>("/api/users", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: { name?: string; email?: string }) =>
    fetchApi<User>(`/api/users/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  delete: (id: number) =>
    fetchApi<{ status: string }>(`/api/users/${id}`, { method: "DELETE" }),
};

export type AuthResponse = { user: User; token: string };
export const authApi = {
  login: (email: string, password: string) =>
    fetchApi<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (name: string, email: string, password: string) =>
    fetchApi<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    }),
  me: () => fetchApi<User>("/api/auth/me"),
};

export type KnowledgeSource = {
  id: number;
  source_type: "website" | "document";
  url: string;
  title: string;
  status: string;
  pages_crawled: number;
  created_at: string;
};
export type SRTopic = {
  id: number;
  user_id: number;
  name: string;
  estimated_minutes: number;
  created_at: string;
  last_reviewed?: string;
  next_interval_days?: number;
  skip_show_again_date?: string;
  /** Bulk-imported: pre-scheduled first due date. Manual add: null/undefined = due today. */
  first_due_date?: string | null;
};
export type SRReviewResult = {
  topic_id: number;
  reviewed_at: string;
  difficulty: string;
  next_interval_days: number;
};
export type SRSettings = { user_id: number; daily_capacity_minutes: number };

export type NeetcodeProblem = {
  title: string;
  slug: string;
  difficulty: string;
  pattern: string;
  leetcode_url: string;
};

export const srApi = {
  listTopics: () => fetchApi<{ topics: SRTopic[] }>("/api/sr/topics"),
  getNeetcode150: () =>
    fetchApi<{ problems: NeetcodeProblem[] }>("/api/sr/neetcode150"),
  importNeetcode150: (slugs: string[]) =>
    fetchApi<{ created: number; topics: SRTopic[] }>("/api/sr/import-neetcode150", {
      method: "POST",
      body: JSON.stringify({ slugs }),
    }),
  createTopic: (data: { name: string; estimated_minutes?: number }) =>
    fetchApi<SRTopic>("/api/sr/topics", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateTopic: (id: number, data: { name?: string; estimated_minutes?: number }) =>
    fetchApi<SRTopic>(`/api/sr/topics/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteTopic: (id: number) =>
    fetchApi<{ status: string }>(`/api/sr/topics/${id}`, {
      method: "DELETE",
    }),
  deleteAllTopics: () =>
    fetchApi<{ status: string; deleted: number }>("/api/sr/topics", {
      method: "DELETE",
    }),
  getDueToday: () =>
    fetchApi<{
      topics: (SRTopic & {
        last_reviewed?: string;
        next_interval_days: number;
        completed?: boolean;
      })[];
    }>("/api/sr/due-today"),
  skipToday: (topicId: number) =>
    fetchApi<{ status: string; topics: SRTopic[] }>("/api/sr/skip-today", {
      method: "POST",
      body: JSON.stringify({ topic_id: topicId }),
    }),
  skipUntil: (topicId: number, days: 1 | 3 | 7 | 14) =>
    fetchApi<{ status: string; topics: SRTopic[] }>("/api/sr/skip-until", {
      method: "POST",
      body: JSON.stringify({ topic_id: topicId, days }),
    }),
  retireTopic: (topicId: number) =>
    fetchApi<{ status: string; topics: SRTopic[] }>(`/api/sr/topics/${topicId}/retire`, {
      method: "POST",
    }),
  recordReview: (topicId: number, difficulty: "easy" | "medium" | "hard") =>
    fetchApi<SRReviewResult>("/api/sr/review", {
      method: "POST",
      body: JSON.stringify({ topic_id: topicId, difficulty }),
    }),
  getSettings: () => fetchApi<SRSettings>("/api/sr/settings"),
  updateSettings: (data: { daily_capacity_minutes?: number }) =>
    fetchApi<SRSettings>("/api/sr/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  completeTask: (project: string, difficulty?: "easy" | "medium" | "hard") =>
    fetchApi<{ status: string; streak: { current_streak: number; longest_streak: number } }>(
      "/api/sr/complete-task",
      {
        method: "POST",
        body: JSON.stringify({ project, ...(difficulty && { difficulty }) }),
      }
    ),
  getStreak: () =>
    fetchApi<{ current_streak: number; longest_streak: number }>("/api/sr/streak"),
};

export const knowledgeApi = {
  list: (sourceType?: string) =>
    fetchApi<{ sources: KnowledgeSource[] }>(
      "/api/knowledge",
      sourceType ? { params: { source_type: sourceType } } : undefined
    ),
  add: (data: { source_type?: string; url?: string; title?: string }) =>
    fetchApi<KnowledgeSource>("/api/knowledge", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  delete: (id: number) =>
    fetchApi<{ status: string }>(`/api/knowledge/${id}`, { method: "DELETE" }),
};
