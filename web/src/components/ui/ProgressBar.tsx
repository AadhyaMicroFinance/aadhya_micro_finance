"use client";

import { cn } from "@/lib/utils";

interface ProgressBarProps {
  value: number; // 0-100
  size?: "sm" | "md" | "lg";
  color?: "brand" | "success" | "warning" | "danger";
  showLabel?: boolean;
  className?: string;
}

const sizeClasses = {
  sm: "h-1.5",
  md: "h-2",
  lg: "h-3",
};

const colorClasses = {
  brand: "bg-brand-600",
  success: "bg-success-500",
  warning: "bg-warning-500",
  danger: "bg-danger-500",
};

export default function ProgressBar({ value, size = "md", color = "brand", showLabel = false, className }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div className={cn("progress-bar", sizeClasses[size])}>
        <div
          className={cn("progress-fill", colorClasses[color])}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs font-medium text-surface-600 tabular-nums min-w-[3rem] text-right">
          {Math.round(clamped)}%
        </span>
      )}
    </div>
  );
}
