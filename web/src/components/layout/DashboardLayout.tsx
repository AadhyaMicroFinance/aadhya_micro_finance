"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/hooks/useAuth";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, initialize } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    initialize();
  }, [initialize]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  // Any navigation closes the mobile drawer.
  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-50">
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-600 animate-pulse">
            <span className="text-lg font-bold text-white">₹</span>
          </div>
          <div className="space-y-2 text-center">
            <div className="h-4 w-32 skeleton rounded-lg mx-auto" />
            <div className="h-3 w-20 skeleton rounded-lg mx-auto" />
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <div className="min-h-screen bg-surface-50">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="lg:ml-64">
        <TopBar onMenu={() => setNavOpen(true)} />
        <main className="p-3 pb-12 sm:p-5 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
