import { useEffect, useState } from "react"
import { api, type ProjectFiles } from "../../lib/api"
import { Spinner } from "../ui/Spinner"

interface FileExplorerProps {
  projectId: string
}

export function FileExplorer({ projectId }: FileExplorerProps) {
  const [files, setFiles] = useState<ProjectFiles>({ backend: [], frontend: [] })
  const [selected, setSelected] = useState<{ area: string; path: string } | null>(null)
  const [content, setContent] = useState<string>("")
  const [loadingContent, setLoadingContent] = useState(false)
  const [loadingFiles, setLoadingFiles] = useState(true)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ backend: true, frontend: true })

  useEffect(() => {
    setLoadingFiles(true)
    api.getFiles(projectId)
      .then(setFiles)
      .catch(() => {})
      .finally(() => setLoadingFiles(false))

    const id = setInterval(() => {
      api.getFiles(projectId).then(setFiles).catch(() => {})
    }, 8000)
    return () => clearInterval(id)
  }, [projectId])

  async function openFile(area: string, path: string) {
    setSelected({ area, path })
    setLoadingContent(true)
    try {
      const res = await api.getFileContent(projectId, area, path)
      setContent(res.content)
    } catch {
      setContent("// Could not load file content")
    } finally {
      setLoadingContent(false)
    }
  }

  if (loadingFiles) return (
    <div className="flex h-full items-center justify-center">
      <Spinner size={20} className="text-indigo-500" />
    </div>
  )

  const hasFiles = files.backend.length > 0 || files.frontend.length > 0

  return (
    <div className="flex h-full">
      {/* Tree */}
      <div className="w-48 shrink-0 overflow-y-auto border-r border-zinc-800/60 py-2 text-xs">
        {!hasFiles ? (
          <p className="px-4 py-6 text-center text-zinc-600">No files yet</p>
        ) : (
          (["backend", "frontend"] as const).map(area => {
            const list = files[area]
            if (list.length === 0) return null
            return (
              <div key={area} className="mb-1">
                <button
                  onClick={() => setExpanded(e => ({ ...e, [area]: !e[area] }))}
                  className="flex w-full items-center gap-1.5 px-3 py-1.5 font-medium text-zinc-400 hover:text-zinc-200"
                >
                  <span>{expanded[area] ? "▾" : "▸"}</span>
                  <span className="capitalize">{area}/</span>
                  <span className="ml-auto text-zinc-700">{list.length}</span>
                </button>
                {expanded[area] && list.map(f => (
                  <button
                    key={f}
                    onClick={() => openFile(area, f)}
                    className={`block w-full truncate px-5 py-1 text-left transition ${
                      selected?.area === area && selected?.path === f
                        ? "bg-indigo-600/20 text-indigo-300"
                        : "text-zinc-500 hover:bg-zinc-800/40 hover:text-zinc-300"
                    }`}
                  >
                    {f.split("/").pop()}
                  </button>
                ))}
              </div>
            )
          })
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {selected ? (
          <>
            <div className="shrink-0 flex items-center justify-between border-b border-zinc-800/60 px-4 py-2">
              <span className="text-[11px] text-zinc-500 font-mono truncate">{selected.area}/{selected.path}</span>
              <a
                href={`/api/projects/${projectId}/files/${selected.area}/${selected.path}`}
                target="_blank" rel="noreferrer"
                className="shrink-0 text-[10px] text-zinc-600 hover:text-zinc-400"
              >raw ↗</a>
            </div>
            {loadingContent ? (
              <div className="flex flex-1 items-center justify-center"><Spinner size={18} className="text-zinc-600" /></div>
            ) : (
              <pre className="flex-1 overflow-auto p-4 text-[11px] leading-relaxed text-zinc-300 font-mono whitespace-pre-wrap">
                {content}
              </pre>
            )}
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-xs text-zinc-600">
            Select a file to view
          </div>
        )}
      </div>
    </div>
  )
}
