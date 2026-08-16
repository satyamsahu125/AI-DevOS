import { useEffect, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { motion, useInView, useAnimation } from "framer-motion"
import { useAuth } from "../lib/auth"

// ── Agent data ──────────────────────────────────────────────────────────────
const AGENTS = [
  { n: "01", name: "Strategic\nReview", icon: "🎯", sub: "Vision & scope"    },
  { n: "02", name: "Product\nOwner",    icon: "📋", sub: "Requirements"      },
  { n: "03", name: "Architect",         icon: "🏗️", sub: "System design"     },
  { n: "04", name: "Designer",          icon: "🎨", sub: "UI & UX"           },
  { n: "05", name: "Security",          icon: "🛡️", sub: "Threat model"      },
  { n: "06", name: "File\nPlanner",     icon: "📁", sub: "Project structure" },
  { n: "07", name: "Backend\nDev",      icon: "⚙️", sub: "Server & API"      },
  { n: "08", name: "Frontend\nDev",     icon: "🖥️", sub: "Interface code"    },
  { n: "09", name: "QA",                icon: "🧪", sub: "Tests & quality"   },
  { n: "10", name: "Docs",              icon: "📝", sub: "Documentation"     },
  { n: "11", name: "DevOps",            icon: "🚀", sub: "Deploy & infra"    },
  { n: "12", name: "Retrospective",     icon: "🔁", sub: "Quality review"    },
]

const AGENT_NAMES = AGENTS.map(a => a.name.replace("\n", " "))

const PROMPTS = [
  "Build a SaaS invoicing platform with team workspaces, recurring billing, and a real-time dashboard.",
  "Create a project management tool with sprints, roadmaps, and real-time collaboration.",
  "Make a developer portfolio CMS with a blog, dark mode, and one-click Vercel deploy.",
  "Build an e-commerce store with inventory management, Stripe checkout, and an admin panel.",
]

const STATS = [
  { value: "20", label: "Pipeline Stages" },
  { value: "12", label: "AI Agents" },
  { value: "65+", label: "API Endpoints" },
  { value: "100%", label: "Autonomous" },
  { value: "0", label: "Boilerplate" },
  { value: "∞", label: "Scalability" },
]

// ── Animation variants ────────────────────────────────────────────────────────
const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: "easeOut", delay: i * 0.08 },
  }),
}

const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
}

const cardVariant = {
  hidden: { opacity: 0, y: 20, scale: 0.96 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring" as const, stiffness: 260, damping: 22 },
  },
}

// ── ScrollSection wrapper ─────────────────────────────────────────────────────
function ScrollSection({ children, className, style }: {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: "-80px" })
  return (
    <motion.div
      ref={ref}
      variants={stagger}
      initial="hidden"
      animate={inView ? "visible" : "hidden"}
      className={className}
      style={style}
    >
      {children}
    </motion.div>
  )
}

function AgentCard({ agent, rtl }: { agent: (typeof AGENTS)[number]; rtl?: boolean }) {
  const lines = agent.name.split("\n")
  return (
    <motion.div
      variants={cardVariant}
      whileHover={{ scale: 1.04, y: -4 }}
      transition={{ type: "spring", stiffness: 300, damping: 24 }}
      className="agent-card"
      style={rtl ? { direction: "ltr" } : undefined}
    >
      <div className="agent-card-glow" />
      <div className="agent-n">{agent.n}</div>
      <span className="agent-ico">{agent.icon}</span>
      <div className="agent-nm">
        {lines[0]}{lines[1] ? <><br />{lines[1]}</> : null}
      </div>
      <div className="agent-sub">{agent.sub}</div>
    </motion.div>
  )
}

export function LandingPage() {
  const navigate       = useNavigate()
  const navRef         = useRef<HTMLElement>(null)
  const typedRef       = useRef<HTMLSpanElement>(null)
  const statusLabelRef = useRef<HTMLSpanElement>(null)
  const { user, loading } = useAuth()

  // Redirect already-authenticated users straight to their projects (only if not anonymous)
  useEffect(() => {
    if (!loading && user && !user.anonymous) {
      navigate("/projects", { replace: true })
    }
  }, [user, loading, navigate])

  // Nav scroll
  useEffect(() => {
    const el = navRef.current
    if (!el) return
    const onScroll = () => el.classList.toggle("stuck", window.scrollY > 12)
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  // Agent highlight cycle
  useEffect(() => {
    const cards = Array.from(document.querySelectorAll<HTMLElement>(".agent-card"))
    if (!cards.length) return
    let idx = 0
    cards[0].classList.add("lit")
    if (statusLabelRef.current) statusLabelRef.current.textContent = AGENT_NAMES[0]
    const iv = setInterval(() => {
      cards[idx].classList.remove("lit")
      idx = (idx + 1) % cards.length
      cards[idx].classList.add("lit")
      if (statusLabelRef.current) statusLabelRef.current.textContent = AGENT_NAMES[idx]
    }, 1350)
    return () => clearInterval(iv)
  }, [])

  // Typing animation
  useEffect(() => {
    let cancelled = false
    let pIdx = 0
    let timer = 0

    function typeChars(text: string, i = 0) {
      if (cancelled || !typedRef.current) return
      typedRef.current.textContent = text.slice(0, i)
      if (i < text.length) {
        timer = window.setTimeout(() => typeChars(text, i + 1), 22)
      } else {
        timer = window.setTimeout(() => eraseChars(text), 2600)
      }
    }

    function eraseChars(text: string) {
      if (cancelled || !typedRef.current) return
      const len = typedRef.current.textContent?.length ?? 0
      if (len > 0) {
        typedRef.current.textContent = text.slice(0, len - 1)
        timer = window.setTimeout(() => eraseChars(text), 10)
      } else {
        pIdx = (pIdx + 1) % PROMPTS.length
        timer = window.setTimeout(() => typeChars(PROMPTS[pIdx]), 380)
      }
    }

    timer = window.setTimeout(() => typeChars(PROMPTS[0]), 700)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [])

  return (
    <div className="land-page">

      {/* Nav */}
      <nav ref={navRef} className="land-nav">
        <div className="land-nav-inner">
          <a href="/" className="land-logo">
            <div className="land-logo-mark">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 1L14.928 5V11L8 15L1.072 11V5L8 1Z" fill="white" fillOpacity=".9" />
                <path d="M8 4.5L11.5 6.5V10.5L8 12.5L4.5 10.5V6.5L8 4.5Z" fill="white" fillOpacity=".3" />
              </svg>
            </div>
            AI DevOS
          </a>
          <button className="land-btn" onClick={() => navigate(user ? "/projects" : "/login")}>
            {user ? "Go to Projects" : "Start Building"} <i className="arr">→</i>
          </button>
        </div>
      </nav>

      {/* Hero — Framer Motion entrance */}
      <section className="land-hero">
        <div className="land-hero-grid" />
        <div className="land-hero-glow" />

        <motion.div
          className="land-badge"
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <div className="land-badge-dot" />
          12 agents · Zero developers needed
        </motion.div>

        <motion.h1
          className="land-headline"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2, ease: "easeOut" }}
        >
          Software<br />builds itself.
        </motion.h1>

        <motion.p
          className="land-sub"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.35, ease: "easeOut" }}
        >
          Describe your project in plain English. A coordinated team of AI agents handles architecture, design, code, testing, and deployment — end to end.
        </motion.p>

        <motion.div
          className="land-terminal"
          initial={{ opacity: 0, y: 24, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.5, ease: "easeOut" }}
        >
          <div className="land-term-chrome">
            <div className="land-tchr-dot" style={{ background: "#ff5f57" }} />
            <div className="land-tchr-dot" style={{ background: "#febc2e" }} />
            <div className="land-tchr-dot" style={{ background: "#28c840" }} />
            <span className="land-tchr-title">AI DevOS — New Project</span>
          </div>
          <div className="land-term-body">
            <div className="land-prompt-row">
              <span className="land-sigil">›</span>
              <span className="land-typed">
                <span ref={typedRef} />
                <span className="land-caret" />
              </span>
            </div>
          </div>
          <div className="land-term-status">
            <span className="land-spinning">◌</span>
            <span>Agents running</span>
            <div className="land-progress-track">
              <div className="land-progress-fill" />
            </div>
            <span className="land-status-agent" ref={statusLabelRef}>Architect</span>
          </div>
        </motion.div>

        <motion.button
          className="land-btn land-btn-lg"
          onClick={() => navigate("/projects")}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.7 }}
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
        >
          Start Building <i className="arr">→</i>
        </motion.button>
      </section>

      {/* Stats bar */}
      <ScrollSection
        style={{
          borderTop: "1px solid var(--color-divider, rgba(255,255,255,0.07))",
          borderBottom: "1px solid var(--color-divider, rgba(255,255,255,0.07))",
          padding: "20px 0",
          display: "flex",
          justifyContent: "center",
        }}
      >
        <div style={{
          display: "flex",
          gap: 0,
          flexWrap: "wrap",
          justifyContent: "center",
          maxWidth: 900,
          width: "100%",
        }}>
          {STATS.map((stat, i) => (
            <motion.div
              key={stat.label}
              variants={fadeUp}
              custom={i}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                padding: "8px 32px",
                borderRight: i < STATS.length - 1 ? "1px solid rgba(255,255,255,0.07)" : "none",
              }}
            >
              <span style={{
                fontSize: 24,
                fontWeight: 700,
                background: "linear-gradient(135deg, #8B5CF6, #06B6D4)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                letterSpacing: "-0.03em",
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
              }}>
                {stat.value}
              </span>
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginTop: 2, whiteSpace: "nowrap" }}>
                {stat.label}
              </span>
            </motion.div>
          ))}
        </div>
      </ScrollSection>

      {/* Steps */}
      <div className="land-steps-band">
        <div className="land-wrap">
          <ScrollSection>
            <motion.div className="land-steps-head" variants={fadeUp}>
              <div className="land-eyebrow">How it works</div>
              <h2>Three steps. One finished product.</h2>
            </motion.div>
          </ScrollSection>
          <ScrollSection>
            <div className="land-steps-grid">
              <motion.div className="land-step" variants={fadeUp} custom={0}>
                <div className="land-step-orb">
                  ✏️<span className="land-step-num">1</span>
                </div>
                <h3>Describe</h3>
                <p>Write what you want to build in plain English. Be brief or exhaustive — the agents read everything and ask if they need more.</p>
              </motion.div>
              <motion.div className="land-step-arrow" variants={fadeUp} custom={1}>→</motion.div>
              <motion.div className="land-step" variants={fadeUp} custom={2}>
                <div className="land-step-orb">
                  👁<span className="land-step-num">2</span>
                </div>
                <h3>Watch</h3>
                <p>A pipeline of 12 specialized agents kicks off in sequence — planning, designing, building, testing, and shipping, all autonomously.</p>
              </motion.div>
              <motion.div className="land-step-arrow" variants={fadeUp} custom={3}>→</motion.div>
              <motion.div className="land-step" variants={fadeUp} custom={4}>
                <div className="land-step-orb">
                  📦<span className="land-step-num">3</span>
                </div>
                <h3>Download</h3>
                <p>Receive a complete, production-ready project — documented, tested, and deployable. Built without you writing a single line of code.</p>
              </motion.div>
            </div>
          </ScrollSection>
        </div>
      </div>

      {/* Pipeline */}
      <section className="land-pipeline">
        <div className="land-wrap">
          <ScrollSection>
            <motion.div className="land-pipeline-head" variants={fadeUp}>
              <div className="land-eyebrow">The team</div>
              <h2>12 agents. One shared goal.</h2>
              <p>Each agent owns a specific discipline and hands off to the next. Every stage is reviewed before the next begins.</p>
            </motion.div>
          </ScrollSection>

          <div>
            <ScrollSection className="land-agents-row">
              {AGENTS.slice(0, 6).map(a => <AgentCard key={a.n} agent={a} />)}
            </ScrollSection>

            <div className="land-row-bridge">
              <svg className="land-bridge-path" viewBox="0 0 100 48" preserveAspectRatio="none" fill="none">
                <path d="M 100 0 L 100 24 Q 100 48 75 48 L 0 48"
                  stroke="rgba(145,132,217,0.3)" strokeWidth="1.5" strokeDasharray="5 4" fill="none" />
                <polygon points="6,44 0,48 6,52" fill="rgba(145,132,217,0.5)" />
              </svg>
            </div>

            <ScrollSection className="land-agents-row" style={{ direction: "rtl" }}>
              {AGENTS.slice(6).map(a => <AgentCard key={a.n} agent={a} rtl />)}
            </ScrollSection>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="land-cta">
        <div className="land-cta-glow" />
        <div className="land-wrap">
          <ScrollSection>
            <motion.div className="land-eyebrow" variants={fadeUp}>Ready when you are</motion.div>
            <motion.h2 variants={fadeUp} custom={1}>Your next build starts<br />with one sentence.</motion.h2>
            <motion.p className="land-cta-sub" variants={fadeUp} custom={2}>No infrastructure. No hiring. No setup required.</motion.p>
            <motion.button
              className="land-btn land-btn-lg"
              variants={fadeUp}
              custom={3}
              onClick={() => navigate("/projects")}
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
            >
              Start Building <i className="arr">→</i>
            </motion.button>
          </ScrollSection>
        </div>
      </section>

      {/* Footer */}
      <footer className="land-footer">
        <span className="land-footer-brand">AI DevOS</span>
      </footer>
    </div>
  )
}
