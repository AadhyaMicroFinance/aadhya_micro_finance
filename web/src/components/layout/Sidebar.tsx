"use client";

import { useState } from "react";
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

export default function Sidebar() {
  const pathname = usePathname();
  const [openSections, setOpenSections] = useState<Set<string>>(() => {
    const active = navItems
      .filter((item) => item.children?.some((child) => pathname === child.href || pathname.startsWith(child.href + "/")))
      .map((item) => item.label);
    return new Set(active);
  });

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
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 border-r border-surface-100 bg-white flex flex-col">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-surface-100 px-5 flex-shrink-0">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600">
          <span className="text-sm font-bold text-white">₹</span>
        </div>
        <div>
          <span className="text-base font-bold text-surface-900 tracking-tight">FinChitti</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
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
                              className={cn(
                                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-all duration-150",
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
      <div className="border-t border-surface-100 px-5 py-4 flex-shrink-0">
        <p className="text-[10px] text-surface-400 text-center">FinChitti v1.0</p>
      </div>
    </aside>
  );
}
