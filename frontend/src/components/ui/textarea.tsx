import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "border-input bg-input/30 placeholder:text-muted-foreground flex min-h-16 w-full rounded-md border px-3 py-2 text-sm shadow-sm transition-colors outline-none",
        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-2",
        "disabled:pointer-events-none disabled:opacity-50 resize-none",
        className,
      )}
      {...props}
    />
  )
}

export { Textarea }
