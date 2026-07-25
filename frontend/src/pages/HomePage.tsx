import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Sparkles, Clock, ArrowRight, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ProjectCard, type ProjectCardData } from "@/components/projects/ProjectCard"
import { NewProjectModal } from "@/components/projects/NewProjectModal"

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08 },
  },
}

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
}

export function HomePage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectCardData[]>([])
  const [showNewProject, setShowNewProject] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/projects")
      .then((r) => r.json())
      .then((data) => {
        setProjects(Array.isArray(data) ? data : [])
        setLoading(false)
      })
      .catch((err) => {
        console.error("Failed to fetch projects:", err)
        setLoading(false)
      })
  }, [])

  const stats = {
    total: projects.length,
    active: projects.filter((p) => p.status === "active" || p.state === "sprint_in_progress").length,
    complete: projects.filter((p) => p.state === "done").length,
  }

  return (
    <div className="h-full overflow-y-auto bg-[#0A0A14] text-white">
      <div className="max-w-5xl mx-auto px-8 py-10">
        {/* Hero section */}
        <motion.div variants={containerVariants} initial="hidden" animate="visible" className="mb-12">
          <motion.div variants={itemVariants} className="mb-2">
            <Badge className="bg-violet-500/15 text-violet-300 border-violet-500/30 text-xs">
              <Sparkles size={10} className="mr-1" />
              AI Engineering Studio
            </Badge>
          </motion.div>

          <motion.h1 variants={itemVariants} className="text-4xl font-bold mt-3 mb-2">
            <span className="aurora-text">Build software</span>
            <br />
            <span className="text-white/90">with your AI team</span>
          </motion.h1>

          <motion.p variants={itemVariants} className="text-white/50 text-lg max-w-lg">
            Describe what you want to build. Your AI engineering team handles the rest — from requirements to deployed code.
          </motion.p>

          {/* Quick start input */}
          <motion.div variants={itemVariants} className="mt-8">
            <div className="glass-card aurora-border p-1 max-w-2xl flex items-center gap-3">
              <input
                className="flex-1 bg-transparent px-4 py-3 text-white placeholder:text-white/30 outline-none text-sm"
                placeholder="Describe what you want to build... e.g. 'A task manager with team collaboration'"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && e.currentTarget.value) {
                    setShowNewProject(true)
                  }
                }}
              />
              <Button
                onClick={() => setShowNewProject(true)}
                className="bg-aurora hover:opacity-90 text-white rounded-lg px-5 py-2.5 font-medium shadow-glow-purple transition-all cursor-pointer"
              >
                <Zap size={14} className="mr-2" />
                Build it
              </Button>
            </div>

            {/* Quick suggestions */}
            <div className="flex gap-2 mt-3 flex-wrap">
              {["Todo app with auth", "E-commerce store", "SaaS dashboard", "REST API + docs"].map((s) => (
                <button
                  key={s}
                  className="text-xs px-3 py-1.5 rounded-full border border-white/10 text-white/40 hover:border-violet-500/40 hover:text-violet-300 hover:bg-violet-500/5 transition-all duration-200 cursor-pointer"
                  onClick={() => setShowNewProject(true)}
                >
                  {s}
                </button>
              ))}
            </div>
          </motion.div>
        </motion.div>

        {/* Stats row */}
        <motion.div variants={containerVariants} initial="hidden" animate="visible" className="grid grid-cols-3 gap-4 mb-10">
          {[
            { label: "Total Projects", value: stats.total, color: "text-violet-400" },
            { label: "Active Builds", value: stats.active, color: "text-cyan-400" },
            { label: "Completed", value: stats.complete, color: "text-emerald-400" },
          ].map((stat) => (
            <motion.div key={stat.label} variants={itemVariants} className="glass-card p-4">
              <p className="text-white/40 text-xs font-medium uppercase tracking-wider">{stat.label}</p>
              <p className={`text-3xl font-bold mt-1 ${stat.color}`}>{stat.value}</p>
            </motion.div>
          ))}
        </motion.div>

        {/* Recent projects */}
        <motion.div variants={containerVariants} initial="hidden" animate="visible">
          <motion.div variants={itemVariants} className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Clock size={14} className="text-white/40" />
              <h2 className="text-sm font-semibold text-white/70 uppercase tracking-wider">Recent Projects</h2>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="text-white/40 hover:text-white text-xs cursor-pointer"
              onClick={() => navigate("/projects")}
            >
              View all
              <ArrowRight size={12} className="ml-1" />
            </Button>
          </motion.div>

          {loading ? (
            <div className="grid grid-cols-2 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="glass-card h-32 shimmer rounded-xl" />
              ))}
            </div>
          ) : projects.length === 0 ? (
            <motion.div variants={itemVariants} className="glass-card p-12 text-center">
              <div className="w-14 h-14 rounded-2xl bg-aurora-subtle border border-violet-500/20 flex items-center justify-center mx-auto mb-4 animate-float">
                <Sparkles size={24} className="text-violet-400" />
              </div>
              <p className="text-white/60 font-medium">No projects yet</p>
              <p className="text-white/30 text-sm mt-1">Start your first project above</p>
            </motion.div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              {projects.slice(0, 6).map((project) => (
                <motion.div key={project.project_id} variants={itemVariants}>
                  <ProjectCard
                    project={project}
                    onClick={() => navigate(`/projects/${project.project_id}`)}
                  />
                </motion.div>
              ))}
            </div>
          )}
        </motion.div>
      </div>

      <NewProjectModal open={showNewProject} onClose={() => setShowNewProject(false)} />
    </div>
  )
}
export default HomePage
