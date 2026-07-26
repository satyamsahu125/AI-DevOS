import { useEffect, useState } from "react"

import { api, type ProjectFiles } from "@/lib/api"

/** Fetches initial GET /projects/{projectId}/files without periodic polling. */
export function useProjectFiles(projectId: string | null) {
  const [files, setFiles] = useState<ProjectFiles>({ backend: [], frontend: [] })

  useEffect(() => {
    if (!projectId) return
    let cancelled = false

    async function fetchFiles() {
      try {
        const next = await api.getFiles(projectId!)
        if (!cancelled) setFiles(next)
      } catch {
        // ignore network error
      }
    }

    fetchFiles()
    return () => {
      cancelled = true
    }
  }, [projectId])

  return files
}
