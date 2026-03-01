"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Clock, MessageCircle, FolderOpen, LogOut, BookOpen, BarChart3 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

export default function Nav() {
  const pathname = usePathname();
  const { logout, isAuthenticated } = useAuth();
  if (!isAuthenticated || pathname === "/login" || pathname === "/register")
    return null;

  const nav = [
    { href: "/", label: "Pomodoro", icon: Clock },
    { href: "/practice", label: "Practice", icon: BookOpen },
    { href: "/analytics", label: "Analytics", icon: BarChart3 },
    { href: "/chat", label: "Chat", icon: MessageCircle },
    { href: "/memory", label: "Memory", icon: FolderOpen },
  ];

  return (
    <header className="sticky top-0 z-10 border-b border-stone-200/80 bg-white/90 backdrop-blur">
      <nav className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
        <Link href="/" className="text-lg font-bold text-stone-800">
          PomodoroAI
        </Link>
        <div className="flex items-center gap-1">
          {nav.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-stone-800 text-white"
                    : "text-stone-600 hover:bg-stone-100 hover:text-stone-800"
                }`}
              >
                <Icon size={18} />
                {label}
              </Link>
            );
          })}
          <button
            onClick={logout}
            className="ml-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-stone-500 hover:bg-stone-100 hover:text-stone-700"
            title="Log out"
          >
            <LogOut size={18} />
          </button>
        </div>
      </nav>
    </header>
  );
}
