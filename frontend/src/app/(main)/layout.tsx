"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { useAuth } from "@/contexts/AuthContext";
import { PomodoroProvider } from "@/contexts/PomodoroContext";

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { loading, isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [loading, isAuthenticated, router]);

  if (loading || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-stone-300 border-t-stone-600" />
      </div>
    );
  }

  return (
    <PomodoroProvider>
      <div className="min-h-screen bg-white">
        <Nav />
        <main className="mx-auto max-w-3xl px-4 py-8">{children}</main>
      </div>
    </PomodoroProvider>
  );
}
