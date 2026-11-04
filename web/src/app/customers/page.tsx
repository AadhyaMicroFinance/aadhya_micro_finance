"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { customersApi } from "@/services/customers";
import { getStatusColor, formatDate, cn } from "@/lib/utils";
import Avatar from "@/components/ui/Avatar";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import type { Customer } from "@/types";
import { Plus, Search, X, UserPlus, ChevronRight } from "lucide-react";

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    full_name: "", mobile_number: "", alternate_mobile: "", email: "",
    date_of_birth: "", gender: "", address: "", city: "", state: "", pincode: "",
    pan_number: "", aadhar_number: "", occupation: "",
    nominee_name: "", nominee_phone: "", nominee_relation: "", notes: "",
  });

  const fetchCustomers = async () => {
    setLoading(true);
    try {
      const res = await customersApi.list({ search: search || undefined, per_page: 50 });
      setCustomers(res.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchCustomers(); }, [search]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      await customersApi.create({ ...form, date_of_birth: form.date_of_birth || undefined, gender: form.gender || undefined });
      setShowCreate(false);
      setForm({ full_name: "", mobile_number: "", alternate_mobile: "", email: "", date_of_birth: "", gender: "", address: "", city: "", state: "", pincode: "", pan_number: "", aadhar_number: "", occupation: "", nominee_name: "", nominee_phone: "", nominee_relation: "", notes: "" });
      fetchCustomers();
    } catch (e) { console.error(e); }
    finally { setCreating(false); }
  };

  const update = (field: string, value: string) => setForm({ ...form, [field]: value });

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Customers</h1>
            <p className="mt-1 text-sm text-surface-500">Register customers before adding them to chittis</p>
          </div>
          <button onClick={() => setShowCreate(true)} className="btn-primary"><Plus size={16} /> Register Customer</button>
        </div>

        {/* Search */}
        <div className="relative max-w-md">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-surface-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, code, mobile, PAN..."
            className="input-field pl-10"
          />
        </div>

        {/* Table */}
        {loading ? (
          <TableSkeleton rows={5} cols={7} />
        ) : customers.length === 0 ? (
          <EmptyState icon="👥" title="No customers yet" description="Register your first customer to get started." action={<button onClick={() => setShowCreate(true)} className="btn-primary"><UserPlus size={16} /> Register Customer</button>} />
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Mobile</th>
                  <th>PAN</th>
                  <th>City</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {customers.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <div className="flex items-center gap-3">
                        <Avatar name={c.full_name} size="sm" />
                        <div>
                          <Link href={`/customers/${c.id}`} className="text-sm font-semibold text-surface-900 hover:text-brand-600 transition-colors">{c.full_name}</Link>
                          <p className="text-xs text-surface-400">{c.customer_code}</p>
                        </div>
                      </div>
                    </td>
                    <td className="text-sm text-surface-600">{c.mobile_number}</td>
                    <td className="text-sm font-mono text-surface-500">{c.pan_number || "—"}</td>
                    <td className="text-sm text-surface-500">{c.city || "—"}</td>
                    <td><span className={cn("badge", getStatusColor(c.status))}>{c.status}</span></td>
                    <td className="text-sm text-surface-500">{formatDate(c.created_at)}</td>
                    <td>
                      <Link href={`/customers/${c.id}`} className="text-brand-600 hover:text-brand-700">
                        <ChevronRight size={16} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ===== Create Customer Modal ===== */}
      {showCreate && (
        <div className="modal-backdrop" onClick={() => setShowCreate(false)}>
          <div className="modal-content max-w-2xl max-h-[90vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-lg font-bold text-surface-900">Register Customer</h2>
                <p className="text-sm text-surface-500">Fill in customer details for onboarding</p>
              </div>
              <button onClick={() => setShowCreate(false)} className="rounded-lg p-2 text-surface-400 hover:bg-surface-100 transition-colors"><X size={18} /></button>
            </div>

            <form onSubmit={handleCreate} className="space-y-6">
              {/* Personal */}
              <div>
                <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-surface-500">Personal Information</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div><label className="input-label">Full Name *</label><input type="text" value={form.full_name} onChange={(e) => update("full_name", e.target.value)} className="input-field" required /></div>
                  <div><label className="input-label">Gender</label><select value={form.gender} onChange={(e) => update("gender", e.target.value)} className="input-field"><option value="">Select</option><option value="MALE">Male</option><option value="FEMALE">Female</option><option value="OTHER">Other</option></select></div>
                  <div><label className="input-label">Date of Birth</label><input type="date" value={form.date_of_birth} onChange={(e) => update("date_of_birth", e.target.value)} className="input-field" /></div>
                  <div><label className="input-label">Occupation</label><input type="text" value={form.occupation} onChange={(e) => update("occupation", e.target.value)} className="input-field" placeholder="e.g., Business" /></div>
                </div>
              </div>

              {/* Contact */}
              <div>
                <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-surface-500">Contact Details</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div><label className="input-label">Mobile Number *</label><input type="text" value={form.mobile_number} onChange={(e) => update("mobile_number", e.target.value)} className="input-field" required placeholder="10-digit mobile" /></div>
                  <div><label className="input-label">Alternate Mobile</label><input type="text" value={form.alternate_mobile} onChange={(e) => update("alternate_mobile", e.target.value)} className="input-field" /></div>
                  <div className="col-span-2"><label className="input-label">Email</label><input type="email" value={form.email} onChange={(e) => update("email", e.target.value)} className="input-field" /></div>
                </div>
              </div>

              {/* Address */}
              <div>
                <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-surface-500">Address</h4>
                <div className="space-y-4">
                  <div><label className="input-label">Address</label><input type="text" value={form.address} onChange={(e) => update("address", e.target.value)} className="input-field" /></div>
                  <div className="grid grid-cols-3 gap-4">
                    <div><label className="input-label">City</label><input type="text" value={form.city} onChange={(e) => update("city", e.target.value)} className="input-field" /></div>
                    <div><label className="input-label">State</label><input type="text" value={form.state} onChange={(e) => update("state", e.target.value)} className="input-field" /></div>
                    <div><label className="input-label">Pincode</label><input type="text" value={form.pincode} onChange={(e) => update("pincode", e.target.value)} className="input-field" maxLength={6} /></div>
                  </div>
                </div>
              </div>

              {/* KYC */}
              <div>
                <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-surface-500">KYC Documents</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div><label className="input-label">PAN Number</label><input type="text" value={form.pan_number} onChange={(e) => update("pan_number", e.target.value.toUpperCase())} className="input-field font-mono" maxLength={10} placeholder="ABCDE1234F" /></div>
                  <div><label className="input-label">Aadhar Number</label><input type="text" value={form.aadhar_number} onChange={(e) => update("aadhar_number", e.target.value)} className="input-field font-mono" maxLength={12} placeholder="123456789012" /></div>
                </div>
              </div>

              {/* Nominee */}
              <div>
                <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-surface-500">Nominee Details</h4>
                <div className="grid grid-cols-3 gap-4">
                  <div><label className="input-label">Nominee Name</label><input type="text" value={form.nominee_name} onChange={(e) => update("nominee_name", e.target.value)} className="input-field" /></div>
                  <div><label className="input-label">Nominee Phone</label><input type="text" value={form.nominee_phone} onChange={(e) => update("nominee_phone", e.target.value)} className="input-field" /></div>
                  <div><label className="input-label">Relation</label><select value={form.nominee_relation} onChange={(e) => update("nominee_relation", e.target.value)} className="input-field"><option value="">Select</option><option value="SPOUSE">Spouse</option><option value="CHILD">Child</option><option value="PARENT">Parent</option><option value="SIBLING">Sibling</option><option value="OTHER">Other</option></select></div>
                </div>
              </div>

              {/* Notes */}
              <div><label className="input-label">Notes</label><textarea value={form.notes} onChange={(e) => update("notes", e.target.value)} className="input-field" rows={2} placeholder="Any additional notes..." /></div>

              <div className="flex justify-end gap-3 border-t border-surface-100 pt-4">
                <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
                <button type="submit" disabled={creating} className="btn-primary">{creating ? "Registering..." : "Register Customer"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
