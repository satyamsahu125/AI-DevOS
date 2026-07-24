import { useEffect, useState } from "react"

import { api, type ProjectFiles } from "@/lib/api"

/** Polls GET /projects/{projectId}/files -- the real generated file tree, growing live as
 * Backend/Frontend stages write files. */
export function useProjectFiles(projectId: string | null, intervalMs = 4000) {
  const [files, setFiles] = useState<ProjectFiles>({ backend: [], frontend: [] })

  useEffect(() => {
    if (!projectId) return
    let cancelled = false

    async function poll() {
      try {
        const next = await api.getFiles(projectId!)
        if (!cancelled) setFiles(next)
      } catch {
        // ignore transient errors, keep last known tree
      }
    }

    poll()
    const timer = setInterval(poll, intervalMs)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [projectId, intervalMs])

  return files
}
