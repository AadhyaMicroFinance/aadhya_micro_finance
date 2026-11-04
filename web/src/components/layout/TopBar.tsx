"use client";

import { useAuthStore } from "@/hooks/useAuth";
import { getInitials } from "@/lib/utils";
import { LogOut, Bell } from "lucide-react";

export default function TopBar() {
  const { user, logout } = useAuthStore();

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-surface-100 bg-white/80 backdrop-blur-xl px-8">
      <div className="flex items-center gap-3">
        <div>
          <h1 className="text-sm font-semibold text-surface-900">Finance & Chitti</h1>
          <p className="text-[11px] text-surface-400">Management Dashboard</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Notification Bell */}
        <button className="relative rounded-xl p-2.5 text-surface-400 transition-colors hover:bg-surface-100 hover:text-surface-600">
          <Bell size={18} />
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-danger-500" />
        </button>

        {/* Divider */}
        <div className="h-8 w-px bg-surface-200" />

        {/* User Profile */}
        <div className="flex items-center gap-3">
          <div className="text-right hidden sm:block">
            <p className="text-sm font-medium text-surface-900">{user?.full_name || "User"}</p>
            <p className="text-[11px] text-surface-400 capitalize">{user?.role?.replace("_", " ") || ""}</p>
          </div>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-brand-700 text-xs font-bold">
            {user?.full_name ? getInitials(user.full_name) : "U"}
          </div>
        </div>

        {/* Logout */}
        <button
          onClick={logout}
          className="rounded-xl p-2.5 text-surface-400 transition-colors hover:bg-danger-50 hover:text-danger-600"
          title="Sign out"
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}
