import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { useAuth } from "../lib/auth"

type Tab = "signin" | "register"

// ── Animation variants ────────────────────────────────────────────────────────
const formVariant = {
  hidden: { opacity: 0, x: 18 },
  visible: { opacity: 1, x: 0, transition: { duration: 0.28, ease: "easeOut" } },
  exit:   { opacity: 0, x: -18, transition: { duration: 0.2 } },
}

const shakeVariant = {
  shake: {
    x: [0, -10, 10, -8, 8, -4, 4, 0],
    transition: { duration: 0.45, ease: "easeInOut" },
  },
}

export default function LoginPage({ initialTab = "signin" }: { initialTab?: Tab }) {
  const { login, register, authEnabled } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>(initialTab)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shakeKey, setShakeKey] = useState(0)
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (tab === "register" && password !== confirm) {
      setError("Passwords don't match")
      setShakeKey(k => k + 1)
      return
    }

    setLoading(true)
    try {
      if (tab === "signin") {
        await login(email.trim(), password)
      } else {
        await register(email.trim(), password)
      }
      navigate("/projects", { replace: true })
    } catch (err: any) {
      setError(err?.message ?? "Authentication failed")
      setShakeKey(k => k + 1)
    } finally {
      setLoading(false)
    }
  }

  // Track previous tab to trigger form animation on tab change
  const [prevTab, setPrevTab] = useState<Tab>(initialTab)
  useEffect(() => {
    setPrevTab(tab)
  }, [tab])

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      background: "var(--bg)",
    }}>
      {/* Left panel — branding + aurora */}
      <motion.div
        initial={{ opacity: 0, x: -40 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        style={{
          flex: "0 0 42%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "48px 56px",
          background: "rgba(10, 10, 20, 0.95)",
          borderRight: "1px solid rgba(255,255,255,0.07)",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Aurora glow backdrop */}
        <div style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(ellipse at 30% 40%, rgba(124,58,237,0.18) 0%, transparent 60%), radial-gradient(ellipse at 70% 70%, rgba(6,182,212,0.10) 0%, transparent 50%)",
          pointerEvents: "none",
        }} />

        {/* Logo */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 48, position: "relative" }}
        >
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: "linear-gradient(135deg, #7C3AED, #06B6D4)",
            display: "grid", placeItems: "center",
          }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 1L14.928 5V11L8 15L1.072 11V5L8 1Z" fill="white" fillOpacity=".9" />
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#f0f0f2" }}>AI DevOS</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>AI Development Operating System</div>
          </div>
        </motion.div>

        {/* Tagline */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.55 }}
          style={{ position: "relative" }}
        >
          <h2 style={{
            fontSize: 32,
            fontWeight: 700,
            lineHeight: 1.2,
            color: "#f0f0f2",
            marginBottom: 16,
            letterSpacing: "-0.03em",
          }}>
            Software that<br />
            <span style={{
              background: "linear-gradient(135deg, #8B5CF6, #06B6D4)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}>
              builds itself.
            </span>
          </h2>
          <p style={{ fontSize: 14, color: "rgba(255,255,255,0.45)", lineHeight: 1.65, maxWidth: 300 }}>
            Describe your project in plain English. A pipeline of AI agents handles everything — architecture, code, tests, and deployment.
          </p>
        </motion.div>

        {/* Pipeline stage dots */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6, duration: 0.5 }}
          style={{ display: "flex", gap: 6, marginTop: 40, flexWrap: "wrap", maxWidth: 280, position: "relative" }}
        >
          {["Research", "Plan", "Design", "Build", "Test", "Deploy"].map((stage, i) => (
            <div key={stage} style={{
              fontSize: 10,
              padding: "3px 8px",
              borderRadius: 4,
              background: i < 4 ? "rgba(124,58,237,0.2)" : "rgba(255,255,255,0.06)",
              border: i < 4 ? "1px solid rgba(124,58,237,0.35)" : "1px solid rgba(255,255,255,0.08)",
              color: i < 4 ? "#a78bfa" : "rgba(255,255,255,0.3)",
              fontFamily: "monospace",
            }}>
              {stage}
            </div>
          ))}
        </motion.div>
      </motion.div>

      {/* Right panel — form */}
      <div style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
      }}>
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15, ease: "easeOut" }}
          style={{ width: "100%", maxWidth: 380 }}
        >

          {/* Tab switcher */}
          <div style={{
            display: "flex",
            gap: 0,
            marginBottom: 28,
            background: "var(--surface-2)",
            borderRadius: "var(--radius-md)",
            padding: 3,
          }}>
            {(["signin", "register"] as Tab[]).map(t => (
              <motion.button
                key={t}
                className="btn"
                onClick={() => { setTab(t); setError(null) }}
                layoutId="active-tab"
                style={{
                  flex: 1,
                  justifyContent: "center",
                  fontSize: 13,
                  padding: "7px",
                  borderRadius: "var(--radius-sm)",
                  background: tab === t ? "var(--surface-1)" : "transparent",
                  color: tab === t ? "var(--text)" : "var(--text-muted)",
                  border: tab === t ? "1px solid var(--border-md)" : "1px solid transparent",
                  boxShadow: tab === t ? "0 1px 3px rgba(0,0,0,0.2)" : "none",
                  transition: "background 150ms, color 150ms, border-color 150ms",
                }}
              >
                {t === "signin" ? "Sign In" : "Register"}
              </motion.button>
            ))}
          </div>

          {/* Form */}
          <div className="surface" style={{ padding: "28px 28px 24px" }}>
            <motion.form
              variants={formVariant}
              initial={false}
              animate={tab}
              onSubmit={handleSubmit}
              style={{ display: "flex", flexDirection: "column", gap: 14 }}
            >
              <div>
                <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)", display: "block", marginBottom: 5 }}>
                  Email
                </label>
                <input
                  id="login-email"
                  className="input"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required
                  placeholder="you@example.com"
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)", display: "block", marginBottom: 5 }}>
                  Password
                </label>
                <input
                  id="login-password"
                  className="input"
                  type="password"
                  autoComplete={tab === "signin" ? "current-password" : "new-password"}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  placeholder="••••••••"
                />
              </div>

              {tab === "register" && (
                <motion.div
                  key="confirm"
                  variants={formVariant}
                  initial="hidden"
                  animate="visible"
                  exit="exit"
                >
                  <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)", display: "block", marginBottom: 5 }}>
                    Confirm Password
                  </label>
                  <input
                    id="login-confirm"
                    className="input"
                    type="password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={e => setConfirm(e.target.value)}
                    required
                    placeholder="••••••••"
                  />
                </motion.div>
              )}

              <AnimatePresence>
                {error && (
                  <motion.div
                    key={shakeKey}
                    className="error-banner"
                    initial={{ opacity: 0, y: -6 }}
                    animate={{ opacity: 1, y: 0, ...shakeVariant.shake }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.25 }}
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><circle cx="8" cy="8" r="7"/><path d="M8 5v3M8 11v0"/></svg>
                    {error}
                  </motion.div>
                )}
              </AnimatePresence>

              <motion.button
                id="login-submit"
                className="btn btn-primary btn-lg"
                type="submit"
                disabled={loading || !email.trim() || !password}
                whileHover={{ scale: loading ? 1 : 1.02 }}
                whileTap={{ scale: loading ? 1 : 0.98 }}
                style={{ justifyContent: "center", marginTop: 4 }}
              >
                {loading && <div className="spinner spinner-sm" style={{ borderTopColor: "#fff" }} />}
                {tab === "signin" ? "Sign In" : "Create Account"}
              </motion.button>
            </motion.form>
          </div>

          {/* Hints */}
          {!authEnabled && (
            <div style={{ marginTop: 14, fontSize: 11, color: "var(--text-dim)", textAlign: "center" }}>
              Auth is disabled — set <span style={{ fontFamily: "monospace", color: "var(--text-muted)" }}>AUTH_ENABLED=true</span> to enable login.
            </div>
          )}

          {tab === "signin" && (
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-dim)", textAlign: "center" }}>
              Default: <span style={{ fontFamily: "monospace", color: "var(--text-muted)" }}>admin@devos.local</span>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  )
}
