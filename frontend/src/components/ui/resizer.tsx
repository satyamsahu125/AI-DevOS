import { cn } from "@/lib/utils"

interface ResizerProps {
  direction: "vertical" | "horizontal"
  onPointerDown: (event: React.PointerEvent) => void
  className?: string
}

/** A thin draggable divider: "vertical" resizes the panel beside it horizontally, "horizontal" resizes it vertically. */
export function Resizer({ direction, onPointerDown, className }: ResizerProps) {
  return (
    <div
      onPointerDown={onPointerDown}
      className={cn(
        "group shrink-0 touch-none select-none bg-transparent",
        direction === "vertical" ? "w-1.5 cursor-col-resize" : "h-1.5 cursor-row-resize",
        className,
      )}
    >
      <div
        className={cn(
          "bg-border transition-colors group-hover:bg-primary/60 group-active:bg-primary",
          direction === "vertical" ? "mx-auto h-full w-px" : "my-auto h-px w-full",
        )}
      />
    </div>
  )
}
