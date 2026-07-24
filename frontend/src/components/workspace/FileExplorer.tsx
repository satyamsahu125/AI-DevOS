import { useState } from "react"
import { ChevronRight, Download, File, FolderOpen, Loader2, PlayCircle } from "lucide-react"

import { api, type ProjectFiles } from "@/lib/api"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"

interface TreeNode {
  name: string
  path: string
  children: Map<string, TreeNode>
  isFile: boolean
}

function buildTree(paths: string[]): TreeNode {
  const root: TreeNode = { name: "", path: "", children: new Map(), isFile: false }
  for (const filePath of paths) {
    const parts = filePath.split("/")
    let node = root
    let acc = ""
    parts.forEach((part, i) => {
      acc = acc ? `${acc}/${part}` : part
      const isFile = i === parts.length - 1
      if (!node.children.has(part)) {
        node.children.set(part, { name: part, path: acc, children: new Map(), isFile })
      }
      node = node.children.get(part)!
    })
  }
  return root
}

function TreeView({
  node,
  area,
  depth,
  onSelect,
  selectedPath,
}: {
  node: TreeNode
  area: string
  depth: number
  onSelect: (area: string, path: string) => void
  selectedPath: string | null
}) {
  const [collapsed, setCollapsed] = useState(false)
  const entries = Array.from(node.children.values())

  return (
    <div>
      {entries.map((child) => (
        <div key={child.path}>
          <button
            onClick={() => (child.isFile ? onSelect(area, child.path) : setCollapsed((c) => !c))}
            style={{ paddingLeft: `${depth * 14 + 8}px` }}
            className={cn(
              "flex w-full items-center gap-1.5 rounded py-1 text-left text-xs hover:bg-accent/60",
              selectedPath === child.path && child.isFile && "bg-accent text-accent-foreground",
            )}
          >
            {!child.isFile && (
              <ChevronRight className={cn("size-3 shrink-0 transition-transform", !collapsed && "rotate-90")} />
            )}
            {child.isFile ? (
              <File className="size-3 shrink-0 text-muted-foreground" />
            ) : (
              <FolderOpen className="size-3 shrink-0 text-primary/70" />
            )}
            <span className="truncate">{child.name}</span>
          </button>
          {!child.isFile && !collapsed && (
            <TreeView node={child} area={area} depth={depth + 1} onSelect={onSelect} selectedPath={selectedPath} />
          )}
        </div>
      ))}
    </div>
  )
}

interface FileExplorerProps {
  projectId: string
  files: ProjectFiles
}

export function FileExplorer({ projectId, files }: FileExplorerProps) {
  const [selected, setSelected] = useState<{ area: string; path: string } | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [runInstructionsOpen, setRunInstructionsOpen] = useState(false)
  const [runInstructions, setRunInstructions] = useState<string | null>(null)

  async function handleOpenRunInstructions() {
    setRunInstructionsOpen(true)
    setRunInstructions(null)
    try {
      const result = await api.getRunInstructions(projectId)
      setRunInstructions(result.markdown)
    } catch {
      setRunInstructions("Failed to load run instructions.")
    }
  }

  async function handleSelect(area: string, path: string) {
    setSelected({ area, path })
    setLoading(true)
    setContent(null)
    try {
      const result = await api.getFileContent(projectId, area, path)
      setContent(result.content)
    } catch {
      setContent("// Failed to load file content")
    } finally {
      setLoading(false)
    }
  }

  const backendTree = buildTree(files.backend)
  const frontendTree = buildTree(files.frontend)
  const totalFiles = files.backend.length + files.frontend.length

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Project Files</h2>
        <span className="text-[11px] text-muted-foreground">{totalFiles} files</span>
      </div>

      {totalFiles > 0 && (
        <div className="flex items-center gap-1.5 border-b border-border px-2 py-2">
          <Button size="sm" variant="outline" className="h-7 flex-1 text-xs" onClick={handleOpenRunInstructions}>
            <PlayCircle className="size-3.5" /> How to Run
          </Button>
          <Button asChild size="sm" variant="outline" className="h-7 flex-1 text-xs">
            <a href={api.downloadUrl(projectId)} download>
              <Download className="size-3.5" /> Download
            </a>
          </Button>
        </div>
      )}

      <ScrollArea className="flex-1">
        <div className="p-2">
          {totalFiles === 0 && (
            <p className="p-3 text-xs text-muted-foreground">
              No files generated yet -- they'll appear here live once Backend/Frontend Developer stages run.
            </p>
          )}
          {files.backend.length > 0 && (
            <div className="mb-2">
              <p className="px-2 py-1 text-[11px] font-semibold text-muted-foreground">backend/</p>
              <TreeView node={backendTree} area="backend" depth={0} onSelect={handleSelect} selectedPath={selected?.path ?? null} />
            </div>
          )}
          {files.frontend.length > 0 && (
            <div>
              <p className="px-2 py-1 text-[11px] font-semibold text-muted-foreground">frontend/</p>
              <TreeView node={frontendTree} area="frontend" depth={0} onSelect={handleSelect} selectedPath={selected?.path ?? null} />
            </div>
          )}
        </div>
      </ScrollArea>

      {selected && (
        <div className="max-h-72 shrink-0 border-t border-border">
          <div className="flex items-center justify-between px-3 py-2">
            <p className="truncate text-[11px] font-mono text-muted-foreground">{selected.path}</p>
          </div>
          <ScrollArea className="h-56 px-3 pb-3">
            {loading ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="size-3 animate-spin" /> Loading…
              </div>
            ) : (
              <pre className="text-[11px] leading-relaxed whitespace-pre-wrap">
                <code>{content}</code>
              </pre>
            )}
          </ScrollArea>
        </div>
      )}

      <Dialog open={runInstructionsOpen} onOpenChange={setRunInstructionsOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>How to Run</DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh]">
            {runInstructions === null ? (
              <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading…
              </div>
            ) : (
              <pre className="text-xs leading-relaxed whitespace-pre-wrap">{runInstructions}</pre>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  )
}
