"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import BrandLockup from "@/components/branding/BrandLockup";
import { useAuthStore } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Users,
  Wallet,
  Handshake,
  CreditCard,
  ArrowDownLeft,
  BarChart3,
  Settings,
  Shield,
  ChevronDown,
  ChevronRight,
  PlusCircle,
  List,
  Copy,
  CircleDollarSign,
  MessageCircle,
  X,
} from "lucide-react";

interface NavChild {
  label: string;
  href: string;
  icon: React.ReactNode;
  permission?: string;
}

interface NavItem {
  label: string;
  href?: string;
  icon: React.ReactNode;
  children?: NavChild[];
  group?: string;
  permission?: string;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: <LayoutDashboard size={20} />, group: "OVERVIEW" },
  { label: "Customers", href: "/customers", icon: <Users size={20} />, group: "CUSTOMERS", permission: "customers:read" },
  {
    label: "Finance",
    icon: <Wallet size={20} />,
    group: "FINANCE",
    permission: "finance:read",
    children: [
      { label: "Dashboard", href: "/finance/dashboard", icon: <LayoutDashboard size={16} />, permission: "finance:read" },
      { label: "All Finances", href: "/finance", icon: <List size={16} />, permission: "finance:read" },
      { label: "Collections", href: "/finance/collections", icon: <CircleDollarSign size={16} />, permission: "finance:read" },
    ],
  },
  {
    label: "Chittis",
    icon: <Handshake size={20} />,
    group: "CHITTI",
    children: [
      { label: "Dashboard", href: "/chitti", icon: <LayoutDashboard size={16} />, permission: "chitti:read" },
      { label: "Analytics", href: "/chitti/analytics", icon: <BarChart3 size={16} />, permission: "chitti:read" },
      { label: "All Chittis", href: "/chitti/all", icon: <List size={16} />, permission: "chitti:read" },
      { label: "Plans", href: "/chitti/plans", icon: <List size={16} />, permission: "chitti:read" },
      { label: "Create Chitti", href: "/chitti/new", icon: <PlusCircle size={16} />, permission: "chitti:create" },
    ],
  },
  { label: "Payments", href: "/payments", icon: <CreditCard size={20} />, group: "TRANSACTIONS", permission: "payments:read" },
  { label: "Collections", href: "/collections/today", icon: <List size={20} />, group: "TRANSACTIONS", permission: "payments:read" },
  { label: "Collect Payment", href: "/payments/collect", icon: <CircleDollarSign size={20} />, group: "TRANSACTIONS", permission: "payments:create" },
  { label: "Reports", href: "/reports", icon: <BarChart3 size={20} />, group: "ANALYTICS", permission: "reports:read" },
  { label: "WhatsApp", href: "/whatsapp", icon: <MessageCircle size={20} />, group: "COMMUNICATION", permission: "whatsapp:read" },
  { label: "Users", href: "/users", icon: <Shield size={20} />, group: "ADMIN", permission: "users:read" },
  { label: "Settings", href: "/settings", icon: <Settings size={20} />, group: "ADMIN", permission: "settings:read" },
  { label: "Audit Logs", href: "/audit", icon: <List size={20} />, group: "ADMIN", permission: "audit:read" },
];

export default function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void }) {
  const pathname = usePathname();
  const user = useAuthStore((state) => state.user);
  const permissions = useMemo(() => new Set(user?.permissions ?? []), [user]);
  const visibleNavItems = useMemo(
    () => navItems
      .map((item) => item.children
        ? {
            ...item,
            children: item.children.filter(
              (child) => !child.permission || permissions.has(child.permission)
            ),
          }
        : item)
      .filter((item) => item.children ? item.children.length > 0 : true)
      .filter((item) => !item.permission || permissions.has(item.permission)),
    [permissions]
  );
  const isChildRouteActive = (href: string) => {
    if (pathname === href) return true;
    // Detail and plan routes belong to the list view, not to the sibling
    // "Dashboard" child whose prefix would otherwise also match them.
    if (href === "/chitti/all" && pathname.startsWith("/chitti/")) {
      return !["/chitti/analytics", "/chitti/new", "/chitti/plans"].some(
        (prefix) => pathname.startsWith(prefix)
      );
    }
    if (href === "/chitti/plans" && pathname.startsWith("/chitti/plans/")) return true;
    // /finance/{uuid} is an account detail view, so it belongs to "All Finances",
    // not to the Dashboard child whose prefix would otherwise match it.
    if (href === "/finance" && pathname.startsWith("/finance/")) {
      return !["/finance/dashboard", "/finance/collections"].some(
        (prefix) => pathname.startsWith(prefix)
      );
    }
    return false;
  };

  const [openSections, setOpenSections] = useState<Set<string>>(() => {
    const active = navItems
      .filter((item) => item.children?.some((child) => isChildRouteActive(child.href)))
      .map((item) => item.label);
    return new Set(active);
  });

  // The drawer must not scroll the app behind it on phones. The scrollable
  // region is now the main panel, not the document body.
  useEffect(() => {
    if (typeof document === "undefined") return;
    const scrollContainer = document.querySelector<HTMLElement>("[data-app-scroll]");
    const previousBodyOverflow = document.body.style.overflow;
    const previousContainerOverflow = scrollContainer?.style.overflow ?? "";
    if (open) {
      document.body.style.overflow = "hidden";
      if (scrollContainer) scrollContainer.style.overflow = "hidden";
    }
    return () => {
      document.body.style.overflow = previousBodyOverflow;
      if (scrollContainer) scrollContainer.style.overflow = previousContainerOverflow;
    };
  }, [open]);

  const toggleSection = (label: string) => {
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  // Group items
  const groups: { label: string; items: NavItem[] }[] = [];
  let currentGroup = "";
  for (const item of visibleNavItems) {
    const g = item.group || "";
    if (g !== currentGroup) {
      groups.push({ label: g, items: [] });
      currentGroup = g;
    }
    groups[groups.length - 1].items.push(item);
  }

  return (
    <>
      {/* Mobile scrim */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-surface-900/40 backdrop-blur-sm transition-opacity lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-[100dvh] w-72 max-w-[85vw] select-none flex-col border-r border-surface-100 bg-white transition-transform duration-200 ease-out lg:w-64 lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        {/* Logo */}
        <div className="flex h-14 flex-shrink-0 items-center border-b border-surface-100 px-4 sm:h-16 sm:px-5">
          <BrandLockup variant="sidebar" />
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded-lg p-2 text-surface-400 hover:bg-surface-100 hover:text-surface-600 lg:hidden"
            aria-label="Close navigation menu"
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto overscroll-contain px-3 py-4 space-y-1">
          {groups.map((group) => (
            <div key={group.label} className="mb-4">
              <p className="px-3 mb-2 text-[10px] font-bold uppercase tracking-widest text-surface-400">
                {group.label}
              </p>
              {group.items.map((item) => {
                if (item.children) {
                  const isChildActive = item.children.some(
                    (child) => isChildRouteActive(child.href)
                  );
                  const isOpen = openSections.has(item.label);

                  return (
                    <div key={item.label}>
                      <button
                        onClick={() => toggleSection(item.label)}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-150",
                          isChildActive
                            ? "bg-brand-50 text-brand-700"
                            : "text-surface-500 hover:bg-surface-50 hover:text-surface-700"
                        )}
                      >
                        <span className={cn(isChildActive ? "text-brand-600" : "text-surface-400")}>{item.icon}</span>
                        {item.label}
                        <span className="ml-auto text-surface-400 transition-transform duration-200">
                          {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        </span>
                      </button>
                      {isOpen && (
                        <div className="ml-5 mt-1 space-y-0.5 border-l border-surface-100 pl-3 animate-slide-down">
                          {item.children.map((child) => {
                            const isActive = isChildRouteActive(child.href);
                            return (
                              <Link
                                key={child.href}
                                href={child.href}
                                onClick={onClose}
                                aria-current={isActive ? "page" : undefined}
                                className={cn(
                                  "flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-[13px] transition-all duration-150",
                                  isActive
                                    ? "bg-brand-50 text-brand-700 font-medium"
                                    : "text-surface-500 hover:bg-surface-50 hover:text-surface-700"
                                )}
                              >
                                <span className={cn(isActive ? "text-brand-500" : "text-surface-400")}>{child.icon}</span>
                                {child.label}
                              </Link>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                }

                const isActive = pathname === item.href || (item.href && pathname.startsWith(item.href + "/"));
                return (
                  <Link
                    key={item.href}
                    href={item.href!}
                    onClick={onClose}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-150",
                      isActive
                        ? "bg-brand-50 text-brand-700"
                        : "text-surface-500 hover:bg-surface-50 hover:text-surface-700"
                    )}
                  >
                    <span className={cn(isActive ? "text-brand-600" : "text-surface-400")}>{item.icon}</span>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-surface-100 px-5 py-4 flex-shrink-0 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <p className="text-[10px] text-surface-400 text-center">
            Aadhya Micro Finance · v1.0
          </p>
        </div>
      </aside>
    </>
  );
}
