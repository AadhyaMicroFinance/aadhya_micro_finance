"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  totalPages: number;
  total?: number;
  perPage?: number;
  onChange: (page: number) => void;
  disabled?: boolean;
}

/** Compact, keyboard-accessible paging control for list screens. */
export default function Pagination({
  page,
  totalPages,
  total,
  perPage,
  onChange,
  disabled = false,
}: PaginationProps) {
  if (totalPages <= 1) return null;

  const rangeStart = total === undefined || perPage === undefined
    ? null
    : (page - 1) * perPage + 1;
  const rangeEnd = total === undefined || perPage === undefined
    ? null
    : Math.min(page * perPage, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-surface-100 pt-4 text-sm text-surface-500">
      <span>
        {rangeStart !== null && rangeEnd !== null
          ? `Showing ${rangeStart}–${rangeEnd} of ${total}`
          : `Page ${page} of ${totalPages}`}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="btn-secondary btn-sm"
          onClick={() => onChange(page - 1)}
          disabled={disabled || page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft size={14} /> Previous
        </button>
        <span className="min-w-16 text-center font-medium text-surface-700">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          className="btn-secondary btn-sm"
          onClick={() => onChange(page + 1)}
          disabled={disabled || page >= totalPages}
          aria-label="Next page"
        >
          Next <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
