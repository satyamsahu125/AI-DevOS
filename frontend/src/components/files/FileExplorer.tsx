import { useState, useEffect, useCallback } from "react"
import {
  Folder, FolderOpen, File, FileCode,
  Download, Play, RefreshCw
} from "lucide-react"
import { RunInstructionsModal } from "./RunInstructionsModal"

const FILE_ICONS: Record<string, { icon: any; color: string }> = {
  ".py":   { icon: FileCode, color: "text-blue-400"   },
  ".ts":   { icon: FileCode, color: "text-cyan-400"   },
  ".tsx":  { icon: FileCode, color: "text-cyan-400"   },
  ".js":   { icon: FileCode, color: "text-yellow-400" },
  ".jsx":  { icon: FileCode, color: "text-yellow-400" },
  ".json": { icon: File,     color: "text-amber-400"  },
  ".md":   { icon: File,     color: "text-white/50"   },
  ".yml":  { icon: File,     color: "text-pink-400"   },
  ".yaml": { icon: File,     color: "text-pink-400"   },
  ".css":  { icon: FileCode, color: "text-purple-400" },
  ".env":  { icon: File,     color: "text-rose-400"   },
}

interface FileExplorerProps {
  projectId: string
  files?: any
}

export function FileExplorer({ projectId }: FileExplorerProps) {
  const [fileList, setFileList] = useState<any[]>([])
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string>("")
  const [loading, setLoading] = useState<boolean>(false)
  const [totalFiles, setTotalFiles] = useState<number>(0)
  const [expanded, setExpanded] = useState<Set<string>>(new Set(["backend", "frontend"]))
  const [showRun, setShowRun] = useState<boolean>(false)

  const fetchFiles = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await fetch(`/api/projects/${projectId}/files`)
      if (res.ok) {
        const data = await res.json()
        // API returns { backend: [...], frontend: [...] } or { files: [...], total_files: ... }
        let combined: string[] = []
        if (data.backend || data.frontend) {
          const b = (data.backend || []).map((p: string) => (p.startsWith("backend/") ? p : `backend/${p}`))
          const f = (data.frontend || []).map((p: string) => (p.startsWith("frontend/") ? p : `frontend/${p}`))
          combined = [...b, ...f]
        } else if (Array.isArray(data.files)) {
          combined = data.files.map((item: any) => (typeof item === "string" ? item : item.path || ""))
        }
        setFileList(combined)
        setTotalFiles(combined.length)
      }
    } catch {
      // ignore network glitch
    }
  }, [projectId])

  useEffect(() => {
    fetchFiles()
  }, [fetchFiles])

  const loadFileContent = async (filePath: string) => {
    setLoading(true)
    try {
      // Handle backend/ or frontend/ prefix in API request URL
      let url = `/api/projects/${projectId}/files/${filePath}`
      if (filePath.startsWith("backend/") || filePath.startsWith("frontend/")) {
        const parts = filePath.split("/")
        const area = parts[0]
        const rest = parts.slice(1).join("/")
        url = `/api/projects/${projectId}/files/${area}/${rest}`
      }
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        setFileContent(data.content || "")
        setSelectedFile(filePath)
      } else {
        setFileContent("Error loading file content")
      }
    } catch {
      setFileContent("Error loading file content")
    }
    setLoading(false)
  }

  const handleDownload = () => {
    window.open(`/api/projects/${projectId}/download`, "_blank")
  }

  const tree = buildTree(fileList)

  return (
    <div className="flex flex-col h-full bg-slate-950/60">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-white/10 bg-slate-900/60">
        <div className="flex items-center gap-2">
          <span className="text-xs text-white/50 font-medium">
            {totalFiles} files generated
          </span>
          <button
            onClick={fetchFiles}
            className="text-white/30 hover:text-white/70 transition-colors p-1 rounded hover:bg-white/5 cursor-pointer"
            title="Refresh file tree"
          >
            <RefreshCw size={12} />
          </button>
        </div>
        {totalFiles > 0 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowRun(true)}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all font-medium cursor-pointer"
            >
              <Play size={12} />
              How to Run
            </button>
            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-violet-500/20 text-violet-300 border border-violet-500/30 hover:bg-violet-500/30 transition-all font-medium cursor-pointer"
            >
              <Download size={12} />
              Download ZIP
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* File tree */}
        <div className="w-52 border-r border-white/10 overflow-y-auto p-2 flex-shrink-0 bg-slate-900/40">
          {totalFiles === 0 ? (
            <div className="text-center py-12 px-2">
              <FileCode size={24} className="text-white/15 mx-auto mb-2" />
              <p className="text-xs text-white/40 leading-relaxed">
                Backend and Frontend stages<br />will generate files here
              </p>
            </div>
          ) : (
            <FileTree
              tree={tree}
              expanded={expanded}
              onToggle={(dir) => {
                const next = new Set(expanded)
                if (next.has(dir)) {
                  next.delete(dir)
                } else {
                  next.add(dir)
                }
                setExpanded(next)
              }}
              onSelectFile={loadFileContent}
              selectedFile={selectedFile}
            />
          )}
        </div>

        {/* File content */}
        <div className="flex-1 overflow-auto p-3 bg-slate-950/80">
          {selectedFile ? (
            <div>
              <div className="flex items-center gap-2 mb-3 pb-2 border-b border-white/5">
                <span className="text-xs font-mono text-indigo-300 font-medium">
                  {selectedFile}
                </span>
              </div>
              {loading ? (
                <div className="animate-pulse space-y-2">
                  {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div key={i} className="h-3 bg-white/5 rounded w-full" />
                  ))}
                </div>
              ) : (
                <pre className="text-xs text-white/80 font-mono whitespace-pre-wrap leading-relaxed overflow-auto">
                  {fileContent}
                </pre>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-xs text-white/30">
                Click a file to view its contents
              </p>
            </div>
          )}
        </div>
      </div>

      <RunInstructionsModal
        projectId={projectId}
        open={showRun}
        onClose={() => setShowRun(false)}
      />
    </div>
  )
}

function buildTree(paths: string[]) {
  const tree: Record<string, any> = {}
  for (const path of paths) {
    if (!path) continue
    const parts = path.split("/")
    let node = tree
    for (const part of parts.slice(0, -1)) {
      if (!node[part]) node[part] = {}
      node = node[part]
    }
    node[parts[parts.length - 1]] = null
  }
  return tree
}

function FileTree({
  tree,
  prefix = "",
  expanded,
  onToggle,
  onSelectFile,
  selectedFile,
}: {
  tree: Record<string, any>
  prefix?: string
  expanded: Set<string>
  onToggle: (dir: string) => void
  onSelectFile: (filePath: string) => void
  selectedFile: string | null
}) {
  return (
    <div className="space-y-0.5">
      {Object.entries(tree).map(([name, children]) => {
        const fullPath = prefix ? `${prefix}/${name}` : name
        const isDir = children !== null
        const isExpanded = expanded.has(fullPath)
        const ext = name.includes(".") ? `.${name.split(".").pop()}` : ""
        const fileMeta = FILE_ICONS[ext] || {
          icon: File,
          color: "text-white/40",
        }
        const FileIcon = fileMeta.icon

        if (isDir) {
          return (
            <div key={name}>
              <button
                onClick={() => onToggle(fullPath)}
                className="flex items-center gap-1.5 w-full text-left px-2 py-1 rounded hover:bg-white/5 text-white/60 hover:text-white/90 transition-colors cursor-pointer"
              >
                {isExpanded ? (
                  <FolderOpen size={13} className="text-amber-400/80 flex-shrink-0" />
                ) : (
                  <Folder size={13} className="text-amber-400/60 flex-shrink-0" />
                )}
                <span className="text-xs truncate font-medium">{name}</span>
              </button>
              {isExpanded && (
                <div className="ml-3 pl-1 border-l border-white/5">
                  <FileTree
                    tree={children}
                    prefix={fullPath}
                    expanded={expanded}
                    onToggle={onToggle}
                    onSelectFile={onSelectFile}
                    selectedFile={selectedFile}
                  />
                </div>
              )}
            </div>
          )
        }

        const isSelected = selectedFile === fullPath
        return (
          <button
            key={name}
            onClick={() => onSelectFile(fullPath)}
            className={`flex items-center gap-1.5 w-full text-left px-2 py-1 rounded text-xs transition-colors truncate cursor-pointer ${
              isSelected
                ? "bg-indigo-500/20 text-indigo-300 font-medium border border-indigo-500/30"
                : "text-white/50 hover:text-white/80 hover:bg-white/5"
            }`}
          >
            <FileIcon size={12} className={`flex-shrink-0 ${fileMeta.color}`} />
            <span className="truncate">{name}</span>
          </button>
        )
      })}
    </div>
  )
}
