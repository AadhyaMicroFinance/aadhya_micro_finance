"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
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
  FileText,
  Copy,
  CircleDollarSign,
  MessageCircle,
  X,
} from "lucide-react";

interface NavChild {
  label: string;
  href: string;
  icon: React.ReactNode;
}

interface NavItem {
  label: string;
  href?: string;
  icon: React.ReactNode;
  children?: NavChild[];
  group?: string;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: <LayoutDashboard size={20} />, group: "OVERVIEW" },
  { label: "Customers", href: "/customers", icon: <Users size={20} />, group: "CUSTOMERS" },
  { label: "Finance", href: "/finance", icon: <Wallet size={20} />, group: "FINANCE" },
  {
    label: "Chittis",
    icon: <Handshake size={20} />,
    group: "CHITTI",
    children: [
      { label: "Dashboard", href: "/chitti", icon: <LayoutDashboard size={16} /> },
      { label: "Analytics", href: "/chitti/analytics", icon: <BarChart3 size={16} /> },
      { label: "Plans", href: "/chitti/plans", icon: <FileText size={16} /> },
      { label: "All Chittis", href: "/chitti/all", icon: <List size={16} /> },
      { label: "Create Chitti", href: "/chitti/new", icon: <PlusCircle size={16} /> },
    ],
  },
  { label: "Payments", href: "/payments", icon: <CreditCard size={20} />, group: "TRANSACTIONS" },
  { label: "Collect Payment", href: "/payments/collect", icon: <CircleDollarSign size={20} />, group: "TRANSACTIONS" },
  { label: "Collections", href: "/collections/today", icon: <ArrowDownLeft size={20} />, group: "TRANSACTIONS" },
  { label: "Reports", href: "/reports", icon: <BarChart3 size={20} />, group: "ANALYTICS" },
  { label: "WhatsApp", href: "/whatsapp", icon: <MessageCircle size={20} />, group: "COMMUNICATION" },
  { label: "Users", href: "/users", icon: <Shield size={20} />, group: "ADMIN" },
  { label: "Settings", href: "/settings", icon: <Settings size={20} />, group: "ADMIN" },
  { label: "Audit Logs", href: "/audit", icon: <List size={20} />, group: "ADMIN" },
];

export default function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void }) {
  const pathname = usePathname();
  const [openSections, setOpenSections] = useState<Set<string>>(() => {
    const active = navItems
      .filter((item) => item.children?.some((child) => pathname === child.href || pathname.startsWith(child.href + "/")))
      .map((item) => item.label);
    return new Set(active);
  });

  // The drawer must not scroll the page behind it on phones.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
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
  for (const item of navItems) {
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
          "fixed left-0 top-0 z-50 flex h-[100dvh] w-72 max-w-[85vw] flex-col border-r border-surface-100 bg-white transition-transform duration-200 ease-out lg:w-64 lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        {/* Logo */}
        <div className="flex h-14 flex-shrink-0 items-center gap-3 border-b border-surface-100 px-4 sm:h-16 sm:px-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600">
            <span className="text-sm font-bold text-white">₹</span>
          </div>
          <div className="min-w-0">
            <span className="block truncate text-sm font-bold tracking-tight text-surface-900">
              Aadhya Micro Finance
            </span>
            <span className="block text-[10px] text-surface-400">Powered by Vayu</span>
          </div>
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
                    (child) => pathname === child.href || pathname.startsWith(child.href + "/")
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
                            const isActive = pathname === child.href || pathname.startsWith(child.href + "/");
                            return (
                              <Link
                                key={child.href}
                                href={child.href}
                                onClick={onClose}
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
