"use client";

import { useCallback, useEffect, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { usersApi } from "@/services/users";
import { getApiErrorMessage } from "@/services/api-client";
import { cn, getStatusColor } from "@/lib/utils";
import Avatar from "@/components/ui/Avatar";
import EmptyState from "@/components/ui/EmptyState";
import Pagination from "@/components/ui/Pagination";
import { TableSkeleton } from "@/components/ui/Skeleton";
import type { User } from "@/types";
import { AlertCircle, Plus, X } from "lucide-react";

const PER_PAGE = 25;

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ username: "", email: "", password: "", full_name: "", role: "STAFF" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const load = useCallback(async (nextPage: number) => {
    setLoading(true);
    setError("");
    try {
      const res = await usersApi.list({ page: nextPage, per_page: PER_PAGE });
      setUsers(res.data ?? []);
      setTotal(res.meta?.total ?? 0);
      setTotalPages(Math.max(1, res.meta?.total_pages ?? 1));
    } catch (e) {
      setError(getApiErrorMessage(e, "Unable to load users."));
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(page);
  }, [page, load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError("");
    try {
      await usersApi.create(form);
      setShowCreate(false);
      setForm({ username: "", email: "", password: "", full_name: "", role: "STAFF" });
      setPage(1);
      await load(1);
    } catch (e) {
      setCreateError(getApiErrorMessage(e, "Could not create this user."));
    } finally {
      setCreating(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-surface-900 tracking-tight">Users</h1>
            <p className="mt-1 text-sm text-surface-500">Manage system users and roles</p>
          </div>
          <button onClick={() => setShowCreate(true)} className="btn-primary"><Plus size={16} /> Add User</button>
        </div>

        {error && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-700">
            <AlertCircle size={16} /> <span className="flex-1">{error}</span>
            <button type="button" onClick={() => void load(page)} className="btn-secondary btn-sm">Retry</button>
          </div>
        )}

        {loading ? <TableSkeleton rows={5} cols={5} /> : users.length === 0 ? (
          <EmptyState icon="👤" title="No users" description="Add your first user to get started." action={<button onClick={() => setShowCreate(true)} className="btn-primary"><Plus size={16} /> Add User</button>} />
        ) : (
          <div className="card space-y-4">
            <div className="table-container">
              <table className="table">
                <thead><tr><th>User</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td><div className="flex items-center gap-3"><Avatar name={u.full_name} size="sm" /><div><p className="text-sm font-semibold">{u.full_name}</p><p className="text-xs text-surface-400">{u.username}</p></div></div></td>
                      <td className="text-sm text-surface-500">{u.email}</td>
                      <td><span className="badge-info">{u.role.replace("_", " ")}</span></td>
                      <td><span className={cn("badge", getStatusColor(u.is_active ? "ACTIVE" : "INACTIVE"))}>{u.is_active ? "Active" : "Inactive"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} totalPages={totalPages} total={total} perPage={PER_PAGE} onChange={setPage} disabled={loading} />
          </div>
        )}
      </div>

      {showCreate && (
        <div className="modal-backdrop" onClick={() => setShowCreate(false)}>
          <div className="modal-content max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-bold text-surface-900">Add New User</h2>
              <button onClick={() => setShowCreate(false)} className="rounded-lg p-2 text-surface-400 hover:bg-surface-100"><X size={18} /></button>
            </div>
            <form onSubmit={handleCreate} className="space-y-4">
              <div><label className="input-label">Full Name *</label><input type="text" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="input-field" required /></div>
              <div><label className="input-label">Username *</label><input type="text" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="input-field" required /></div>
              <div><label className="input-label">Email *</label><input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="input-field" required /></div>
              <div><label className="input-label">Password *</label><input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="input-field" required /></div>
              <div><label className="input-label">Role *</label><select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="input-field"><option value="SUPER_ADMIN">Super Admin</option><option value="ADMIN">Admin</option><option value="STAFF">Staff</option><option value="COLLECTOR">Collector</option></select></div>
              {createError && (
                <p role="alert" className="flex items-center gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700"><AlertCircle size={15} /> {createError}</p>
              )}
              <div className="flex justify-end gap-3 border-t border-surface-100 pt-4">
                <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
                <button type="submit" disabled={creating} className="btn-primary">{creating ? "Creating..." : "Create User"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
