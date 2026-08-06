import { useEffect, useState } from "react"
import { api, type AdminUser } from "../lib/api"
import { useAuth } from "../lib/auth"
import { Spinner } from "../components/ui/Spinner"

const ROLES = ["admin", "developer", "viewer"] as const
type Role = (typeof ROLES)[number]

const ROLE_COLORS: Record<Role, string> = {
  admin:     "rgba(145,132,217,.9)",
  developer: "rgba(16,185,129,.9)",
  viewer:    "rgba(100,116,139,.9)",
}

function UserRow({ user, onRoleChange, onDelete, currentUserId }: {
  user: AdminUser
  onRoleChange: (id: string, role: Role) => Promise<void>
  onDelete: (id: string) => Promise<void>
  currentUserId: string
}) {
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const isSelf = user.user_id === currentUserId

  async function changeRole(role: Role) {
    if (role === user.role) return
    setSaving(true)
    try { await onRoleChange(user.user_id, role) } finally { setSaving(false) }
  }

  async function del() {
    if (!confirm(`Delete user "${user.email}"? This cannot be undone.`)) return
    setDeleting(true)
    try { await onDelete(user.user_id) } finally { setDeleting(false) }
  }

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 14,
      padding: "12px 16px", borderRadius: 10,
      background: "var(--color-surface)", border: "1px solid var(--color-divider)",
    }}>
      {/* Avatar */}
      <div style={{
        width: 34, height: 34, borderRadius: "50%", background: "var(--color-accent-dim)",
        border: "1px solid var(--color-accent-border)",
        display: "grid", placeItems: "center", flexShrink: 0,
        fontSize: 13, fontWeight: 700, color: "var(--color-accent)",
      }}>
        {user.email[0].toUpperCase()}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {user.email}
          {isSelf && <span style={{ marginLeft: 6, fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "rgba(145,132,217,.15)", color: "var(--color-accent)" }}>you</span>}
        </div>
        <div style={{ fontSize: 11, color: "var(--color-muted)" }}>
          Joined {new Date(user.created_at).toLocaleDateString()}
        </div>
      </div>

      {/* Role selector */}
      <div style={{ display: "flex", gap: 4 }}>
        {ROLES.map(r => (
          <button
            key={r}
            onClick={() => changeRole(r)}
            disabled={saving || isSelf}
            title={isSelf ? "Cannot change your own role" : `Set role to ${r}`}
            style={{
              padding: "4px 10px", borderRadius: 6, border: "1px solid",
              borderColor: user.role === r ? ROLE_COLORS[r] : "var(--color-divider)",
              background: user.role === r ? `${ROLE_COLORS[r]}20` : "transparent",
              color: user.role === r ? ROLE_COLORS[r] : "var(--color-muted)",
              fontSize: 11, fontWeight: user.role === r ? 600 : 400,
              cursor: isSelf ? "not-allowed" : "pointer",
              fontFamily: "var(--font-sans)", opacity: isSelf ? .5 : 1,
              transition: "all .12s",
            }}
          >
            {r}
          </button>
        ))}
      </div>

      {/* Delete */}
      <button
        onClick={del}
        disabled={deleting || isSelf}
        title={isSelf ? "Cannot delete yourself" : "Delete user"}
        style={{
          width: 30, height: 30, borderRadius: 7, border: "1px solid var(--color-divider)",
          background: "transparent", cursor: isSelf ? "not-allowed" : "pointer",
          display: "grid", placeItems: "center", color: "var(--color-muted)",
          opacity: isSelf ? .3 : 1, transition: "all .12s",
        }}
        onMouseEnter={e => { if (!isSelf) { e.currentTarget.style.borderColor = "var(--color-error)"; e.currentTarget.style.color = "var(--color-error)" }}}
        onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--color-divider)"; e.currentTarget.style.color = "var(--color-muted)" }}
      >
        {deleting ? <Spinner size={12} /> : (
          <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        )}
      </button>
    </div>
  )
}

export function AdminPage() {
  const { user } = useAuth()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const load = () => {
    setLoading(true)
    api.adminListUsers()
      .then(r => setUsers(r.users))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  async function handleRoleChange(user_id: string, role: string) {
    await api.adminUpdateRole(user_id, role)
    setUsers(u => u.map(x => x.user_id === user_id ? { ...x, role: role as Role } : x))
  }

  async function handleDelete(user_id: string) {
    await api.adminDeleteUser(user_id)
    setUsers(u => u.filter(x => x.user_id !== user_id))
  }

  const roleCounts = { admin: 0, developer: 0, viewer: 0 }
  users.forEach(u => { if (u.role in roleCounts) roleCounts[u.role as Role]++ })

  return (
    <div style={{ height: "100%", overflowY: "auto", padding: "28px 32px" }}>
      <div style={{ maxWidth: 760, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-.03em", margin: 0 }}>User Management</h1>
          <p style={{ color: "var(--color-muted)", fontSize: 13, margin: "6px 0 0" }}>
            Manage team members and their access levels
          </p>
        </div>

        {/* Summary chips */}
        {!loading && users.length > 0 && (
          <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
            {(["admin", "developer", "viewer"] as Role[]).map(r => (
              <div key={r} style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "5px 12px", borderRadius: 100,
                border: `1px solid ${ROLE_COLORS[r]}40`,
                background: `${ROLE_COLORS[r]}12`, fontSize: 12,
                color: ROLE_COLORS[r],
              }}>
                <span style={{ fontWeight: 700 }}>{roleCounts[r]}</span>
                <span style={{ opacity: .8 }}>{r}{roleCounts[r] !== 1 ? "s" : ""}</span>
              </div>
            ))}
          </div>
        )}

        {loading && (
          <div style={{ display: "flex", justifyContent: "center", paddingTop: 60 }}>
            <Spinner size={24} className="text-indigo-500" />
          </div>
        )}

        {error && (
          <div style={{ padding: "14px 18px", borderRadius: 10, background: "rgba(244,63,94,.08)", border: "1px solid rgba(244,63,94,.2)", color: "var(--color-error)", fontSize: 13 }}>
            {error}
          </div>
        )}

        {!loading && !error && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {users.length === 0 ? (
              <div style={{ textAlign: "center", padding: 48, color: "var(--color-muted)", fontSize: 13 }}>
                No users found
              </div>
            ) : users.map(u => (
              <UserRow
                key={u.user_id}
                user={u}
                onRoleChange={handleRoleChange}
                onDelete={handleDelete}
                currentUserId={user?.user_id ?? ""}
              />
            ))}
          </div>
        )}

        {/* Auth disabled notice */}
        {!loading && !error && users.length === 0 && (
          <div style={{ marginTop: 24, padding: "14px 18px", borderRadius: 10, background: "rgba(145,132,217,.08)", border: "1px solid var(--color-accent-border)", fontSize: 13, color: "var(--color-muted)" }}>
            <strong style={{ color: "var(--color-accent)" }}>Tip:</strong> Set <code style={{ fontFamily: "var(--font-mono)" }}>AUTH_ENABLED=true</code> in <code style={{ fontFamily: "var(--font-mono)" }}>.env</code> to enable multi-user authentication.
          </div>
        )}
      </div>
    </div>
  )
}
