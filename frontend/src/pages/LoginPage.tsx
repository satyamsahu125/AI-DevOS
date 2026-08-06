import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../lib/auth"

export function LoginPage() {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState<"login" | "register">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (mode === "register" && password !== confirm) {
      setError("Passwords don't match")
      return
    }
    setLoading(true)
    setError("")
    try {
      if (mode === "login") {
        await login(email.trim(), password)
      } else {
        await register(email.trim(), password)
      }
      navigate("/projects", { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--color-bg)", padding: 24, position: "relative", overflow: "hidden",
    }}>
      {/* Grid background */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: "radial-gradient(rgba(233,233,237,.07) 1px, transparent 1px)",
        backgroundSize: "26px 26px",
        WebkitMaskImage: "radial-gradient(ellipse 80% 80% at 50% 50%, black 10%, transparent 75%)",
        maskImage: "radial-gradient(ellipse 80% 80% at 50% 50%, black 10%, transparent 75%)",
        pointerEvents: "none",
      }} />
      {/* Glow */}
      <div style={{
        position: "absolute", top: "45%", left: "50%", width: 600, height: 400,
        transform: "translate(-50%, -50%)",
        background: "radial-gradient(ellipse at center, rgba(145,132,217,.18) 0%, transparent 70%)",
        pointerEvents: "none",
      }} />

      <div style={{ position: "relative", width: "100%", maxWidth: 400 }}>
        {/* Logo */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 32, gap: 10 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 12, background: "var(--color-accent)",
            display: "grid", placeItems: "center",
          }}>
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={2.2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-.03em", color: "var(--color-text)" }}>
            AI DevOS
          </span>
          <span style={{ fontSize: 13, color: "var(--color-muted)" }}>
            {mode === "login" ? "Sign in to your workspace" : "Create your account"}
          </span>
        </div>

        {/* Card */}
        <div style={{
          background: "var(--color-surface)", border: "1px solid var(--color-divider)",
          borderRadius: 16, padding: 32, boxShadow: "0 24px 64px rgba(0,0,0,.4)",
        }}>
          {/* Mode toggle */}
          <div style={{
            display: "flex", gap: 4, background: "var(--color-bg)",
            borderRadius: 8, padding: 4, marginBottom: 24,
          }}>
            {(["login", "register"] as const).map(m => (
              <button
                key={m}
                onClick={() => { setMode(m); setError("") }}
                style={{
                  flex: 1, padding: "7px 0", borderRadius: 6, border: "none",
                  background: mode === m ? "var(--color-accent-dim)" : "transparent",
                  color: mode === m ? "var(--color-accent)" : "var(--color-muted)",
                  fontSize: 13, fontWeight: mode === m ? 600 : 400,
                  cursor: "pointer", fontFamily: "var(--font-sans)",
                  transition: "background .12s, color .12s",
                  borderLeft: mode === m ? "1px solid var(--color-accent-border)" : "1px solid transparent",
                }}
              >
                {m === "login" ? "Sign In" : "Register"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Email */}
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "var(--color-muted)", marginBottom: 6, letterSpacing: ".04em", textTransform: "uppercase" }}>
                Email
              </label>
              <input
                autoFocus
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                style={{
                  width: "100%", padding: "10px 12px", borderRadius: 8,
                  border: "1px solid var(--color-divider)", background: "var(--color-bg)",
                  color: "var(--color-text)", fontSize: 14, fontFamily: "var(--font-sans)",
                  outline: "none", boxSizing: "border-box",
                  transition: "border-color .12s",
                }}
                onFocus={e => e.target.style.borderColor = "var(--color-accent)"}
                onBlur={e => e.target.style.borderColor = "var(--color-divider)"}
              />
            </div>

            {/* Password */}
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "var(--color-muted)", marginBottom: 6, letterSpacing: ".04em", textTransform: "uppercase" }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                minLength={8}
                style={{
                  width: "100%", padding: "10px 12px", borderRadius: 8,
                  border: "1px solid var(--color-divider)", background: "var(--color-bg)",
                  color: "var(--color-text)", fontSize: 14, fontFamily: "var(--font-sans)",
                  outline: "none", boxSizing: "border-box",
                  transition: "border-color .12s",
                }}
                onFocus={e => e.target.style.borderColor = "var(--color-accent)"}
                onBlur={e => e.target.style.borderColor = "var(--color-divider)"}
              />
            </div>

            {/* Confirm password (register only) */}
            {mode === "register" && (
              <div>
                <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "var(--color-muted)", marginBottom: 6, letterSpacing: ".04em", textTransform: "uppercase" }}>
                  Confirm Password
                </label>
                <input
                  type="password"
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  placeholder="••••••••"
                  required
                  style={{
                    width: "100%", padding: "10px 12px", borderRadius: 8,
                    border: `1px solid ${confirm && confirm !== password ? "var(--color-error)" : "var(--color-divider)"}`,
                    background: "var(--color-bg)", color: "var(--color-text)",
                    fontSize: 14, fontFamily: "var(--font-sans)", outline: "none", boxSizing: "border-box",
                  }}
                  onFocus={e => e.target.style.borderColor = "var(--color-accent)"}
                  onBlur={e => e.target.style.borderColor = confirm && confirm !== password ? "var(--color-error)" : "var(--color-divider)"}
                />
              </div>
            )}

            {/* Error */}
            {error && (
              <div style={{
                padding: "10px 12px", borderRadius: 8,
                background: "rgba(244,63,94,.08)", border: "1px solid rgba(244,63,94,.25)",
                color: "var(--color-error)", fontSize: 13,
              }}>
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !email || !password}
              style={{
                width: "100%", padding: "11px 0", borderRadius: 8,
                background: "var(--color-accent)", border: "none",
                color: "#fff", fontSize: 14, fontWeight: 600,
                fontFamily: "var(--font-sans)", cursor: loading ? "not-allowed" : "pointer",
                opacity: loading || !email || !password ? .5 : 1,
                display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                transition: "opacity .12s",
                marginTop: 4,
              }}
            >
              {loading && (
                <span style={{
                  width: 14, height: 14, borderRadius: "50%",
                  border: "2px solid rgba(255,255,255,.3)", borderTopColor: "#fff",
                  animation: "spin .8s linear infinite", display: "inline-block",
                }} />
              )}
              {mode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>
        </div>

        {/* Footer note */}
        <p style={{ textAlign: "center", fontSize: 12, color: "var(--color-muted)", marginTop: 20, opacity: .6 }}>
          Default admin: <code style={{ fontFamily: "var(--font-mono)", color: "var(--color-accent)" }}>admin@devos.local</code>
        </p>
      </div>
    </div>
  )
}
