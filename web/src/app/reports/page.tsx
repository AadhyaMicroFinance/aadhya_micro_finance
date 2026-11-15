"use client";

import { useState } from "react";
import BrandLockup from "@/components/branding/BrandLockup";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { reportApi, type RangeReport } from "@/services/reports";
import { formatCurrency } from "@/lib/utils";
import { Calendar, Download, FileText } from "lucide-react";

const reportTypes = [
  { id: "daily", label: "Daily Collection" }, { id: "weekly", label: "Weekly Collection" },
  { id: "monthly", label: "Monthly Collection" }, { id: "outstanding", label: "Outstanding Report" },
  { id: "overdue", label: "Overdue Report" }, { id: "finance", label: "Finance Report" },
  { id: "chitti", label: "Chitti Report" }, { id: "collector", label: "Collector Report" },
  { id: "payment-method", label: "Payment Method Report" },
];

function today() { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); }

export default function ReportsPage() {
  const [selectedReport, setSelectedReport] = useState("daily");
  const [startDate, setStartDate] = useState(today());
  const [endDate, setEndDate] = useState(today());
  const [report, setReport] = useState<RangeReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const generate = async () => {
    setLoading(true); setError("");
    try { setReport(await reportApi.getRangeReport(startDate, endDate, selectedReport)); }
    catch (e) { setError("Could not retrieve this report. Check the date range and try again."); setReport(null); }
    finally { setLoading(false); }
  };

  const exportFile = async (format: "csv" | "xlsx") => {
    try {
      const blob = await reportApi.exportRangeReport(startDate, endDate, selectedReport, format);
      const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `${selectedReport}-${startDate}-${endDate}.${format}`; anchor.click(); URL.revokeObjectURL(url);
    } catch { setError("Could not export this report."); }
  };

  const value = (key: string, raw: unknown) => /amount|total|pending|expected|paid/i.test(key) && typeof raw === "number" ? formatCurrency(raw) : String(raw ?? "—");
  const renderTable = (title: string, rows: Array<Record<string, string | number | boolean | null>>) => {
    const columns = rows.length ? Object.keys(rows[0]) : [];
    return <section key={title} className="space-y-2"><h3 className="text-sm font-semibold">{title} ({rows.length})</h3>{rows.length ? <div className="table-container"><table className="table"><thead><tr>{columns.map((col) => <th key={col}>{col.replaceAll("_", " ")}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={String(row.id || row.transaction_id || row.reference_id || index)}>{columns.map((col) => <td key={col}>{value(col, row[col])}</td>)}</tr>)}</tbody></table></div> : <p className="rounded-xl bg-surface-50 p-4 text-center text-sm text-surface-500">No matching records.</p>}</section>;
  };

  return <DashboardLayout><div className="space-y-6">
    <header><h1 className="text-2xl font-bold text-surface-900">Reports</h1><p className="mt-1 text-sm text-surface-500">Generate reports from Finance and Chitti ledger data.</p></header>
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
      <aside className="card space-y-1"><h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-surface-500">Report type</h2>{reportTypes.map((r) => <button key={r.id} onClick={() => { setSelectedReport(r.id); setReport(null); }} className={`w-full rounded-xl p-3 text-left text-sm ${selectedReport === r.id ? "bg-brand-50 font-semibold text-brand-700" : "text-surface-600 hover:bg-surface-50"}`}>{r.label}</button>)}</aside>
      <section className="card report-print space-y-5 lg:col-span-3">
        <div className="hidden border-b pb-4 print:block"><BrandLockup variant="document" /><p className="mt-2 text-xs">H.No: 10-2-41/1, Sainagar, Sircilla · CIN: U64990TS2025PTC199452</p><p className="text-xs">9182838496 · 9886232471</p></div>
        <h2 className="text-sm font-semibold">{reportTypes.find((r) => r.id === selectedReport)?.label}</h2>
        <div className="flex flex-wrap items-end gap-4"><div><label className="input-label">From</label><input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input-field" /></div><div><label className="input-label">To</label><input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="input-field" /></div><button className="btn-primary" onClick={generate} disabled={loading || !startDate || !endDate}><Calendar size={16} />{loading ? "Generating…" : "Generate"}</button></div>
        {error && <div role="alert" className="rounded-xl border border-danger-100 bg-danger-50 p-3 text-sm text-danger-700">{error}</div>}
        {report && <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3"><div className="rounded-xl bg-surface-50 p-4"><p className="text-xs text-surface-500">Net collections</p><p className="text-lg font-bold">{formatCurrency(report.collected_total)}</p></div><div className="rounded-xl bg-brand-50 p-4"><p className="text-xs text-surface-500">Finance collected</p><p className="text-lg font-bold">{formatCurrency(report.finance_collected)}</p><p className="text-xs text-surface-500">Pending {formatCurrency(report.finance_pending)}</p></div><div className="rounded-xl bg-purple-50 p-4"><p className="text-xs text-surface-500">Chitti collected</p><p className="text-lg font-bold">{formatCurrency(report.chitti_collected)}</p><p className="text-xs text-surface-500">Pending {formatCurrency(report.chitti_pending)}</p></div></div>
          <div className="space-y-5">{report.breakdown?.length ? renderTable(selectedReport === "collector" ? "Collector breakdown" : "Payment method breakdown", report.breakdown) : null}{renderTable("Transactions", report.transactions)}{renderTable("Pending dues", report.pending_details)}</div>
          <div className="flex flex-wrap gap-3 print:hidden"><button className="btn-secondary btn-sm" onClick={() => exportFile("csv")}><Download size={14} /> Export CSV</button><button className="btn-secondary btn-sm" onClick={() => exportFile("xlsx")}><Download size={14} /> Export Excel</button><button className="btn-secondary btn-sm" onClick={() => window.print()}><FileText size={14} /> Print / Save PDF</button></div>
        </>}
        {!report && !loading && <p className="rounded-xl bg-surface-50 p-6 text-center text-sm text-surface-500">Choose a report and date range, then generate it.</p>}
      </section>
    </div>
  </div></DashboardLayout>;
}
