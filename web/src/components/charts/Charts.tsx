"use client";

/**
 * Lightweight SVG chart primitives — no external chart dependency.
 * Each chart is responsive, hover-interactive and styled with the design tokens.
 */

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";

export interface SeriesDef {
  key: string;
  label: string;
  color: string;
  fill?: boolean;
  dashed?: boolean;
}

interface ChartProps {
  data: Record<string, any>[];
  series: SeriesDef[];
  height?: number;
  formatter?: (value: number) => string;
  xLabel?: (row: Record<string, any>, index: number) => string;
}

const W = 800;
const PAD_L = 56;
const PAD_R = 16;
const PAD_T = 16;
const PAD_B = 30;

function niceMax(value: number): number {
  if (value <= 0) return 10;
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  const normalized = value / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

function shortMoney(v: number): string {
  if (Math.abs(v) >= 10000000) return `₹${(v / 10000000).toFixed(1)}Cr`;
  if (Math.abs(v) >= 100000) return `₹${(v / 100000).toFixed(1)}L`;
  if (Math.abs(v) >= 1000) return `₹${(v / 1000).toFixed(0)}k`;
  return `₹${Math.round(v)}`;
}

// ---------------------------------------------------------------------------
// Line / area chart
// ---------------------------------------------------------------------------

export function LineChart({
  data,
  series,
  height = 240,
  formatter = shortMoney,
  xLabel,
}: ChartProps) {
  const H = height;
  const [hover, setHover] = useState<number | null>(null);

  const max = useMemo(() => {
    let m = 0;
    for (const row of data) {
      for (const s of series) m = Math.max(m, Number(row[s.key] || 0));
    }
    return niceMax(m);
  }, [data, series]);

  const n = data.length;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;
  const x = (i: number) => PAD_L + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => PAD_T + (1 - v / max) * innerH;

  const gridLines = [0, 0.25, 0.5, 0.75, 1];
  const labelEvery = Math.max(1, Math.ceil(n / 7));

  const handleMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!n) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
    const svgX = ratio * W;
    const idx = Math.round(((svgX - PAD_L) / innerW) * (n - 1));
    setHover(Math.min(Math.max(idx, 0), n - 1));
  };

  if (!n) {
    return (
      <div className="flex h-[220px] items-center justify-center text-sm text-surface-400">
        No data for this period
      </div>
    );
  }

  const hoverRow = hover !== null ? data[hover] : null;

  return (
    <div className="relative w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Collection trend chart"
      >
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity="0.28" />
              <stop offset="100%" stopColor={s.color} stopOpacity="0.02" />
            </linearGradient>
          ))}
        </defs>

        {gridLines.map((g) => (
          <g key={g}>
            <line
              x1={PAD_L}
              x2={W - PAD_R}
              y1={PAD_T + (1 - g) * innerH}
              y2={PAD_T + (1 - g) * innerH}
              stroke="#e2e8f0"
              strokeWidth="1"
              strokeDasharray={g === 0 ? "0" : "3 5"}
            />
            <text
              x={PAD_L - 8}
              y={PAD_T + (1 - g) * innerH + 4}
              textAnchor="end"
              className="fill-surface-400"
              style={{ fontSize: 10 }}
            >
              {formatter(max * g)}
            </text>
          </g>
        ))}

        {series.map((s) => {
          const points = data.map((row, i) => `${x(i)},${y(Number(row[s.key] || 0))}`);
          const line = `M ${points.join(" L ")}`;
          const area = `${line} L ${x(n - 1)},${PAD_T + innerH} L ${x(0)},${PAD_T + innerH} Z`;
          return (
            <g key={s.key}>
              {s.fill && <path d={area} fill={`url(#grad-${s.key})`} />}
              <path
                d={line}
                fill="none"
                stroke={s.color}
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeDasharray={s.dashed ? "6 5" : undefined}
              />
            </g>
          );
        })}

        {data.map((row, i) =>
          i % labelEvery === 0 || i === n - 1 ? (
            <text
              key={i}
              x={x(i)}
              y={H - 8}
              textAnchor="middle"
              className="fill-surface-400"
              style={{ fontSize: 10 }}
            >
              {xLabel ? xLabel(row, i) : row.label ?? row.date ?? ""}
            </text>
          ) : null
        )}

        {hover !== null && (
          <g>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={PAD_T}
              y2={PAD_T + innerH}
              stroke="#94a3b8"
              strokeWidth="1"
              strokeDasharray="4 4"
            />
            {series.map((s) => (
              <circle
                key={s.key}
                cx={x(hover)}
                cy={y(Number(data[hover][s.key] || 0))}
                r="4.5"
                fill="#fff"
                stroke={s.color}
                strokeWidth="2.5"
              />
            ))}
          </g>
        )}
      </svg>

      {hoverRow && (
        <div
          className="pointer-events-none absolute top-2 z-10 min-w-[150px] rounded-xl border border-surface-100 bg-white/95 px-3 py-2 shadow-elevated backdrop-blur"
          style={{
            left: `${Math.min(Math.max((hover! / Math.max(n - 1, 1)) * 100, 4), 72)}%`,
          }}
        >
          <p className="mb-1 text-[11px] font-semibold text-surface-500">
            {xLabel ? xLabel(hoverRow, hover!) : hoverRow.label ?? hoverRow.date}
          </p>
          {series.map((s) => (
            <div key={s.key} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-[11px] text-surface-500">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />
                {s.label}
              </span>
              <span className="text-[11px] font-bold text-surface-900">
                {formatter(Number(hoverRow[s.key] || 0))}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="mt-1 flex flex-wrap items-center gap-4">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5 text-xs text-surface-500">
            <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Grouped bar chart
// ---------------------------------------------------------------------------

export function GroupedBarChart({
  data,
  series,
  height = 240,
  formatter = shortMoney,
  xLabel,
}: ChartProps) {
  const H = height;
  const [hover, setHover] = useState<number | null>(null);

  const max = useMemo(() => {
    let m = 0;
    for (const row of data) {
      for (const s of series) m = Math.max(m, Number(row[s.key] || 0));
    }
    return niceMax(m);
  }, [data, series]);

  const n = data.length;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;
  const groupW = n ? innerW / n : innerW;
  const barW = Math.max(4, (groupW * 0.62) / series.length);
  const labelEvery = Math.max(1, Math.ceil(n / 7));

  if (!n) {
    return (
      <div className="flex h-[220px] items-center justify-center text-sm text-surface-400">
        No data for this period
      </div>
    );
  }

  return (
    <div className="relative w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Comparison bar chart">
        {[0, 0.25, 0.5, 0.75, 1].map((g) => (
          <g key={g}>
            <line
              x1={PAD_L}
              x2={W - PAD_R}
              y1={PAD_T + (1 - g) * innerH}
              y2={PAD_T + (1 - g) * innerH}
              stroke="#e2e8f0"
              strokeWidth="1"
              strokeDasharray={g === 0 ? "0" : "3 5"}
            />
            <text
              x={PAD_L - 8}
              y={PAD_T + (1 - g) * innerH + 4}
              textAnchor="end"
              className="fill-surface-400"
              style={{ fontSize: 10 }}
            >
              {formatter(max * g)}
            </text>
          </g>
        ))}

        {data.map((row, i) => {
          const groupX = PAD_L + i * groupW;
          return (
            <g
              key={i}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              <rect
                x={groupX}
                y={PAD_T}
                width={groupW}
                height={innerH}
                fill={hover === i ? "#f8fafc" : "transparent"}
              />
              {series.map((s, si) => {
                const value = Number(row[s.key] || 0);
                const barH = (value / max) * innerH;
                return (
                  <rect
                    key={s.key}
                    x={groupX + groupW * 0.19 + si * barW}
                    y={PAD_T + innerH - barH}
                    width={barW}
                    height={Math.max(barH, value > 0 ? 2 : 0)}
                    rx="3"
                    fill={s.color}
                    opacity={hover === null || hover === i ? 1 : 0.45}
                  />
                );
              })}
              {(i % labelEvery === 0 || i === n - 1) && (
                <text
                  x={groupX + groupW / 2}
                  y={H - 8}
                  textAnchor="middle"
                  className="fill-surface-400"
                  style={{ fontSize: 10 }}
                >
                  {xLabel ? xLabel(row, i) : row.label ?? ""}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {hover !== null && (
        <div
          className="pointer-events-none absolute top-2 z-10 min-w-[150px] rounded-xl border border-surface-100 bg-white/95 px-3 py-2 shadow-elevated backdrop-blur"
          style={{ left: `${Math.min(Math.max((hover / Math.max(n - 1, 1)) * 100, 4), 70)}%` }}
        >
          <p className="mb-1 text-[11px] font-semibold text-surface-500">
            {xLabel ? xLabel(data[hover], hover) : data[hover].label ?? data[hover].date}
          </p>
          {series.map((s) => (
            <div key={s.key} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-[11px] text-surface-500">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />
                {s.label}
              </span>
              <span className="text-[11px] font-bold text-surface-900">
                {formatter(Number(data[hover][s.key] || 0))}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="mt-1 flex flex-wrap items-center gap-4">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5 text-xs text-surface-500">
            <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Donut chart
// ---------------------------------------------------------------------------

export interface DonutSlice {
  label: string;
  value: number;
  color: string;
}

export function DonutChart({
  data,
  size = 190,
  thickness = 26,
  formatter = shortMoney,
  centerLabel = "Total",
}: {
  data: DonutSlice[];
  size?: number;
  thickness?: number;
  formatter?: (value: number) => string;
  centerLabel?: string;
}) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const [hover, setHover] = useState<number | null>(null);

  let offset = 0;
  const arcs = data.map((d, i) => {
    const fraction = total > 0 ? d.value / total : 0;
    const arc = {
      ...d,
      fraction,
      dash: fraction * circumference,
      offset,
      index: i,
    };
    offset += fraction * circumference;
    return arc;
  });

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:gap-6">
      <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="#f1f5f9"
            strokeWidth={thickness}
          />
          <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
            {arcs.map((arc) => (
              <circle
                key={arc.label}
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke={arc.color}
                strokeWidth={hover === arc.index ? thickness + 6 : thickness}
                strokeDasharray={`${arc.dash} ${circumference - arc.dash}`}
                strokeDashoffset={-arc.offset}
                strokeLinecap="butt"
                onMouseEnter={() => setHover(arc.index)}
                onMouseLeave={() => setHover(null)}
                style={{ transition: "stroke-width 150ms ease" }}
              />
            ))}
          </g>
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-surface-400">
            {hover !== null ? data[hover].label : centerLabel}
          </p>
          <p className="text-lg font-bold text-surface-900">
            {formatter(hover !== null ? data[hover].value : total)}
          </p>
        </div>
      </div>

      <div className="w-full space-y-2">
        {data.map((d, i) => (
          <button
            key={d.label}
            type="button"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            className={cn(
              "flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1 text-left transition-colors",
              hover === i ? "bg-surface-50" : ""
            )}
          >
            <span className="flex items-center gap-2 text-xs text-surface-600">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: d.color }} />
              {d.label}
            </span>
            <span className="text-xs font-semibold text-surface-900">
              {formatter(d.value)}
              <span className="ml-1.5 font-normal text-surface-400">
                {total > 0 ? Math.round((d.value / total) * 100) : 0}%
              </span>
            </span>
          </button>
        ))}
        {data.length === 0 && (
          <p className="py-6 text-center text-xs text-surface-400">No payments yet</p>
        )}
      </div>
    </div>
  );
}
