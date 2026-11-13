"use client";

import { useAuthStore } from "@/hooks/useAuth";
import { getInitials } from "@/lib/utils";
import { LogOut, Bell, Menu } from "lucide-react";

export default function TopBar({ onMenu }: { onMenu?: () => void }) {
  const { user, logout } = useAuthStore();

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-2 border-b border-surface-100 bg-white/90 px-3 backdrop-blur-xl sm:h-16 sm:px-5 lg:px-8">
      <div className="flex min-w-0 items-center gap-2">
        <button
          type="button"
          onClick={onMenu}
          className="rounded-xl p-2 text-surface-500 transition-colors hover:bg-surface-100 hover:text-surface-700 lg:hidden"
          aria-label="Open navigation menu"
        >
          <Menu size={22} />
        </button>
        <div className="min-w-0">
          <h1 className="truncate text-[11px] font-bold uppercase leading-tight tracking-wide text-surface-900 sm:text-sm">
            Aadhya Micro Finance
          </h1>
          <p className="truncate text-[10px] leading-tight text-surface-400 sm:text-[11px]">
            Powered by Vayu
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1.5 sm:gap-3">
        {/* Notification Bell */}
        <button className="relative rounded-xl p-2 text-surface-400 transition-colors hover:bg-surface-100 hover:text-surface-600 sm:p-2.5">
          <Bell size={18} />
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-danger-500" />
        </button>

        {/* Divider */}
        <div className="hidden h-8 w-px bg-surface-200 sm:block" />

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
          className="rounded-xl p-2 text-surface-400 transition-colors hover:bg-danger-50 hover:text-danger-600 sm:p-2.5"
          title="Sign out"
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}
