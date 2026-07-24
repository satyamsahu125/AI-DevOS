import { useEffect, useState } from "react"
import { Bot, CheckCircle2 } from "lucide-react"

import { api, type AgentInfo } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

export function AgentsPage() {
  const [agents, setAgents] = useState<AgentInfo[] | null>(null)

  useEffect(() => {
    api.listAgents().then(setAgents).catch(() => setAgents([]))
  }, [])

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <header className="mb-6">
        <h1 className="text-xl font-semibold">Agents</h1>
        <p className="text-sm text-muted-foreground">
          Every registered agent in the pipeline, and whether it's genuinely LLM-backed.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {agents?.map((agent) => (
          <Card key={agent.agent}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Bot className="size-3.5" />
                  </div>
                  <CardTitle>{agent.agent}</CardTitle>
                </div>
                {agent.llm_backed && (
                  <Badge variant="success">
                    <CheckCircle2 className="size-3" /> LLM-backed
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-1.5 text-xs text-muted-foreground">
              <p>
                <span className="font-medium text-foreground">Stage:</span> {agent.stage}
              </p>
              <p>
                <span className="font-medium text-foreground">Prompt builder:</span> {agent.prompt_builder}
              </p>
              <p>
                <span className="font-medium text-foreground">Output schema:</span> {agent.output_schema}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
