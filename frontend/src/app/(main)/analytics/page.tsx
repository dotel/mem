"use client";

import { useState } from "react";
import { BarChart3 } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { usePomodoro } from "@/contexts/PomodoroContext";

function formatShortDate(dateStr: string) {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatWeekday(dateStr: string) {
  return new Date(dateStr + "T12:00:00").toLocaleDateString("en-US", {
    weekday: "short",
  });
}

type AnalyticsTab = "day" | "week" | "month";

export default function AnalyticsPage() {
  const {
    todayData,
    weekData,
    monthData,
    historyData,
    analyticsLoading,
    refreshAnalytics,
  } = usePomodoro();

  const [analyticsTab, setAnalyticsTab] = useState<AnalyticsTab>("day");

  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-8 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800">
          <BarChart3 size={22} />
          Analytics
        </h1>
        <button
          onClick={refreshAnalytics}
          className="rounded-lg px-3 py-2 text-sm text-stone-600 hover:bg-stone-100 hover:text-stone-800"
        >
          Refresh
        </button>
      </div>

      <div className="mb-6 flex gap-2">
        {(["day", "week", "month"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setAnalyticsTab(tab)}
            className={`flex-1 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              analyticsTab === tab
                ? "bg-stone-800 text-white"
                : "bg-stone-100 text-stone-600 hover:bg-stone-200"
            }`}
          >
            {tab === "day" ? "Day" : tab === "week" ? "Week" : "Month"}
          </button>
        ))}
      </div>

      {analyticsLoading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-stone-300 border-t-stone-600" />
        </div>
      ) : analyticsTab === "day" ? (
        todayData ? (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2">
              {(todayData.total_work_minutes ?? 0) + (todayData.total_break_minutes ?? 0) > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-medium text-stone-600">Work vs Break</h3>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={[
                            {
                              name: "Work",
                              value: todayData.total_work_minutes ?? 0,
                              fill: "#44403c",
                            },
                            {
                              name: "Break",
                              value: todayData.total_break_minutes ?? 0,
                              fill: "#a8a29e",
                            },
                          ].filter((d) => d.value > 0)}
                          cx="50%"
                          cy="50%"
                          innerRadius={40}
                          outerRadius={64}
                          paddingAngle={2}
                          dataKey="value"
                          nameKey="name"
                          label={({ name, value }) => `${name}: ${value}m`}
                        >
                          {[
                            {
                              name: "Work",
                              value: todayData.total_work_minutes ?? 0,
                              fill: "#44403c",
                            },
                            {
                              name: "Break",
                              value: todayData.total_break_minutes ?? 0,
                              fill: "#a8a29e",
                            },
                          ]
                            .filter((d) => d.value > 0)
                            .map((entry, i) => (
                              <Cell key={i} fill={entry.fill} />
                            ))}
                        </Pie>
                        <Tooltip formatter={(v: number | undefined) => [`${v ?? 0} min`, ""]} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
              <div className="flex flex-col justify-center space-y-2">
                <p className="text-stone-700">
                  <span className="font-medium">Focus time:</span>{" "}
                  {todayData.total_work_minutes ?? 0} min
                </p>
                <p className="text-stone-700">
                  <span className="font-medium">Sessions:</span>{" "}
                  {todayData.completed_sessions ?? 0}
                </p>
                <p className="text-stone-700">
                  <span className="font-medium">Focus score:</span>{" "}
                  <span className="font-semibold text-stone-800">
                    {(todayData.total_focus_score ?? 0).toFixed(0)}%
                  </span>
                </p>
              </div>
            </div>
          </div>
        ) : (
          <p className="py-6 text-center text-stone-500">
            No productivity data for today yet. Start a pomodoro to begin tracking!
          </p>
        )
      ) : analyticsTab === "week" ? (
        weekData && weekData.total_sessions > 0 ? (
          <div className="space-y-6">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={[...historyData.slice(0, 7)].reverse().map((e) => ({
                    date: formatWeekday(e.date),
                    fullDate: e.date,
                    minutes: e.data?.total_work_minutes ?? 0,
                  }))}
                  margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#78716c" />
                  <YAxis tick={{ fontSize: 11 }} stroke="#78716c" />
                  <Tooltip
                    formatter={(v: number | undefined) => [`${v ?? 0} min`, "Work"]}
                    labelFormatter={(_, p) =>
                      p?.[0]?.payload?.fullDate
                        ? formatShortDate(p[0].payload.fullDate)
                        : ""
                    }
                  />
                  <Bar dataKey="minutes" name="Work" fill="#44403c" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="grid gap-2 text-sm text-stone-700 sm:grid-cols-2">
              <p>
                <span className="font-medium">Total:</span> {weekData.total_minutes} min (
                {(weekData.total_minutes / 60).toFixed(1)} hrs)
              </p>
              <p>
                <span className="font-medium">Sessions:</span> {weekData.total_sessions}
              </p>
              <p>
                <span className="font-medium">Daily avg:</span>{" "}
                {weekData.avg_daily_minutes.toFixed(0)} min
              </p>
              <p>
                <span className="font-medium">Best day:</span> {weekData.best_day_minutes} min
              </p>
            </div>
          </div>
        ) : (
          <p className="py-6 text-center text-stone-500">
            No productivity data for this week yet.
          </p>
        )
      ) : monthData && monthData.total_sessions > 0 ? (
        <div className="space-y-6">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[...historyData.slice(0, 30)].reverse().map((e) => ({
                  date: formatShortDate(e.date),
                  fullDate: e.date,
                  minutes: e.data?.total_work_minutes ?? 0,
                }))}
                margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10 }}
                  stroke="#78716c"
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fontSize: 11 }} stroke="#78716c" />
                <Tooltip
                  formatter={(v: number | undefined) => [`${v ?? 0} min`, "Work"]}
                  labelFormatter={(_, p) => p?.[0]?.payload?.fullDate ?? ""}
                />
                <Bar dataKey="minutes" name="Work" fill="#44403c" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="grid gap-2 text-sm text-stone-700 sm:grid-cols-2">
            <p>
              <span className="font-medium">Total:</span> {monthData.total_minutes} min (
              {(monthData.total_minutes / 60).toFixed(1)} hrs)
            </p>
            <p>
              <span className="font-medium">Sessions:</span> {monthData.total_sessions}
            </p>
            <p>
              <span className="font-medium">Active days:</span> {monthData.active_days}/30
            </p>
          </div>
        </div>
      ) : (
        <p className="py-6 text-center text-stone-500">
          No productivity data for this month yet.
        </p>
      )}
    </div>
  );
}
