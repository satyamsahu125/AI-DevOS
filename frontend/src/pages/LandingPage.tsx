import { useEffect, useRef } from "react"
import { useNavigate } from "react-router-dom"

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

function AgentCard({ agent, rtl }: { agent: (typeof AGENTS)[number]; rtl?: boolean }) {
  const lines = agent.name.split("\n")
  return (
    <div className="agent-card" style={rtl ? { direction: "ltr" } : undefined}>
      <div className="agent-card-glow" />
      <div className="agent-n">{agent.n}</div>
      <span className="agent-ico">{agent.icon}</span>
      <div className="agent-nm">
        {lines[0]}{lines[1] ? <><br />{lines[1]}</> : null}
      </div>
      <div className="agent-sub">{agent.sub}</div>
    </div>
  )
}

export function LandingPage() {
  const navigate       = useNavigate()
  const navRef         = useRef<HTMLElement>(null)
  const typedRef       = useRef<HTMLSpanElement>(null)
  const statusLabelRef = useRef<HTMLSpanElement>(null)

  // Nav scroll
  useEffect(() => {
    const el = navRef.current
    if (!el) return
    const onScroll = () => el.classList.toggle("stuck", window.scrollY > 12)
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  // Scroll reveal
  useEffect(() => {
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target) }
      })
    }, { threshold: 0.1 })
    document.querySelectorAll(".fu").forEach(el => io.observe(el))
    return () => io.disconnect()
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
          <button className="land-btn" onClick={() => navigate("/projects")}>
            Start Building <i className="arr">→</i>
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section className="land-hero">
        <div className="land-hero-grid" />
        <div className="land-hero-glow" />

        <div className="land-badge">
          <div className="land-badge-dot" />
          12 agents · Zero developers needed
        </div>

        <h1 className="land-headline">
          Software<br />builds itself.
        </h1>

        <p className="land-sub">
          Describe your project in plain English. A coordinated team of AI agents handles architecture, design, code, testing, and deployment — end to end.
        </p>

        <div className="land-terminal">
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
        </div>

        <button className="land-btn land-btn-lg" onClick={() => navigate("/projects")}>
          Start Building <i className="arr">→</i>
        </button>
      </section>

      <hr style={{ border: "none", borderTop: "1px solid var(--color-divider)" }} />

      {/* Steps */}
      <div className="land-steps-band">
        <div className="land-wrap">
          <div className="land-steps-head fu">
            <div className="land-eyebrow">How it works</div>
            <h2>Three steps. One finished product.</h2>
          </div>
          <div className="land-steps-grid">
            <div className="land-step fu d1">
              <div className="land-step-orb">
                ✏️<span className="land-step-num">1</span>
              </div>
              <h3>Describe</h3>
              <p>Write what you want to build in plain English. Be brief or exhaustive — the agents read everything and ask if they need more.</p>
            </div>
            <div className="land-step-arrow fu">→</div>
            <div className="land-step fu d2">
              <div className="land-step-orb">
                👁<span className="land-step-num">2</span>
              </div>
              <h3>Watch</h3>
              <p>A pipeline of 12 specialized agents kicks off in sequence — planning, designing, building, testing, and shipping, all autonomously.</p>
            </div>
            <div className="land-step-arrow fu d1">→</div>
            <div className="land-step fu d3">
              <div className="land-step-orb">
                📦<span className="land-step-num">3</span>
              </div>
              <h3>Download</h3>
              <p>Receive a complete, production-ready project — documented, tested, and deployable. Built without you writing a single line of code.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline */}
      <section className="land-pipeline">
        <div className="land-wrap">
          <div className="land-pipeline-head fu">
            <div className="land-eyebrow">The team</div>
            <h2>12 agents. One shared goal.</h2>
            <p>Each agent owns a specific discipline and hands off to the next. Every stage is reviewed before the next begins.</p>
          </div>

          <div>
            <div className="land-agents-row fu">
              {AGENTS.slice(0, 6).map(a => <AgentCard key={a.n} agent={a} />)}
            </div>

            <div className="land-row-bridge">
              <svg className="land-bridge-path" viewBox="0 0 100 48" preserveAspectRatio="none" fill="none">
                <path d="M 100 0 L 100 24 Q 100 48 75 48 L 0 48"
                  stroke="rgba(145,132,217,0.3)" strokeWidth="1.5" strokeDasharray="5 4" fill="none" />
                <polygon points="6,44 0,48 6,52" fill="rgba(145,132,217,0.5)" />
              </svg>
            </div>

            <div className="land-agents-row fu" style={{ direction: "rtl" }}>
              {AGENTS.slice(6).map(a => <AgentCard key={a.n} agent={a} rtl />)}
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="land-cta">
        <div className="land-cta-glow" />
        <div className="land-wrap">
          <div className="land-eyebrow fu">Ready when you are</div>
          <h2 className="fu d1">Your next build starts<br />with one sentence.</h2>
          <p className="land-cta-sub fu d2">No infrastructure. No hiring. No setup required.</p>
          <button className="land-btn land-btn-lg fu d3" onClick={() => navigate("/projects")}>
            Start Building <i className="arr">→</i>
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="land-footer">
        <span className="land-footer-brand">AI DevOS</span>
      </footer>
    </div>
  )
}
