import { useEffect, useState } from "react"
import { api, type AdminUser } from "../lib/api"
import { useAuth } from "../lib/auth"

const ROLES = ["admin", "developer", "viewer"] as const
type Role = typeof ROLES[number]

const ROLE_CONFIG: Record<Role, { label: string; cls: string }> = {
  admin:     { label: "Admin",     cls: "badge-error"   },
  developer: { label: "Developer", cls: "badge-accent"  },
  viewer:    { label: "Viewer",    cls: "badge-neutral" },
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString()
}

export default function AdminPage() {
  const { user } = useAuth()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionUser, setActionUser] = useState<string | null>(null)

  const load = async () => {
    try {
      const r = await api.adminListUsers()
      setUsers(r.users)
      setLoading(false)
    } catch (err: any) {
      setError(err.message ?? "Failed to load users")
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleRoleChange = async (userId: string, role: string) => {
    setActionUser(userId)
    try {
      await api.adminUpdateRole(userId, role)
      await load()
    } catch { }
    finally { setActionUser(null) }
  }

  const handleDelete = async (userId: string, email: string) => {
    if (!confirm(`Delete user "${email}"? This cannot be undone.`)) return
    setActionUser(userId)
    try {
      await api.adminDeleteUser(userId)
      await load()
    } catch { }
    finally { setActionUser(null) }
  }

  // Summary
  const counts = { admin: 0, developer: 0, viewer: 0 }
  users.forEach(u => { if (u.role in counts) counts[u.role as Role]++ })

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div className="page-header">
        <div>
          <div className="page-title">User Management</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
            {users.length} user{users.length !== 1 ? "s" : ""} total
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {ROLES.map(role => (
            <span key={role} className={`badge ${ROLE_CONFIG[role].cls}`}>
              {counts[role]} {ROLE_CONFIG[role].label}{counts[role] !== 1 ? "s" : ""}
            </span>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
        {loading && (
          <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
            <div className="spinner spinner-lg" />
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}

        {!loading && users.length === 0 && (
          <div className="empty-state">No users found.</div>
        )}

        {users.length > 0 && (
          <div className="surface" style={{ overflow: "hidden" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => {
                  const isSelf = u.user_id === user?.user_id
                  const isActioning = actionUser === u.user_id
                  return (
                    <tr key={u.user_id} style={{ opacity: isActioning ? 0.5 : 1 }}>
                      <td className="td-primary">
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <div style={{
                            width: 26, height: 26, borderRadius: "50%",
                            background: "var(--accent-lo)", border: "1px solid var(--accent-border)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 10, fontWeight: 700, color: "var(--accent-hi)", flexShrink: 0,
                          }}>
                            {u.email.slice(0, 1).toUpperCase()}
                          </div>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text)" }}>{u.email}</div>
                            <div style={{ fontSize: 10, color: "var(--text-dim)", fontFamily: "monospace" }}>{u.user_id.slice(0, 12)}…</div>
                          </div>
                          {isSelf && <span className="badge badge-neutral" style={{ fontSize: 10 }}>You</span>}
                        </div>
                      </td>
                      <td>
                        {isSelf ? (
                          <span className={`badge ${ROLE_CONFIG[u.role]?.cls ?? "badge-neutral"}`}>
                            {ROLE_CONFIG[u.role]?.label ?? u.role}
                          </span>
                        ) : (
                          <select
                            value={u.role}
                            onChange={e => handleRoleChange(u.user_id, e.target.value)}
                            disabled={isActioning}
                            style={{
                              background: "var(--surface-3)",
                              border: "1px solid var(--border)",
                              borderRadius: "var(--radius-sm)",
                              color: "var(--text)",
                              fontSize: 12,
                              padding: "3px 6px",
                              cursor: "pointer",
                            }}
                          >
                            {ROLES.map(r => (
                              <option key={r} value={r}>{ROLE_CONFIG[r].label}</option>
                            ))}
                          </select>
                        )}
                      </td>
                      <td style={{ fontFamily: "monospace", fontSize: 12 }}>{formatDate(u.created_at)}</td>
                      <td>
                        <span className={`badge ${u.is_active ? "badge-success" : "badge-neutral"}`}>
                          {u.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td>
                        {!isSelf && (
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={() => handleDelete(u.user_id, u.email)}
                            disabled={isActioning}
                          >
                            {isActioning ? <div className="spinner spinner-sm" /> : "Delete"}
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        <div style={{ marginTop: 16, fontSize: 12, color: "var(--text-dim)" }}>
          To enable multi-user authentication, set <code style={{ fontFamily: "monospace", color: "var(--text-muted)" }}>AUTH_ENABLED=true</code> in your environment.
        </div>
      </div>
    </div>
  )
}
