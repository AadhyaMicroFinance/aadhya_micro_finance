"use client";

import { useState, useEffect } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { usersApi } from "@/services/users";
import { cn, getStatusColor } from "@/lib/utils";
import Avatar from "@/components/ui/Avatar";
import EmptyState from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import type { User } from "@/types";
import { Plus, X, Shield } from "lucide-react";

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ username: "", email: "", password: "", full_name: "", role: "STAFF" });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const load = async () => {
      try { const res = await usersApi.list({ per_page: 50 }); setUsers(res.data); }
      catch (e) { console.error(e); }
      finally { setLoading(false); }
    };
    load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      await usersApi.create(form);
      setShowCreate(false);
      setForm({ username: "", email: "", password: "", full_name: "", role: "STAFF" });
      const res = await usersApi.list({ per_page: 50 });
      setUsers(res.data);
    } catch (e) { console.error(e); }
    finally { setCreating(false); }
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

        {loading ? <TableSkeleton rows={5} cols={5} /> : users.length === 0 ? (
          <EmptyState icon="👤" title="No users" description="Add your first user to get started." action={<button onClick={() => setShowCreate(true)} className="btn-primary"><Plus size={16} /> Add User</button>} />
        ) : (
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
