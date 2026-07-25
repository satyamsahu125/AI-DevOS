import * as React from "react"
import { cn } from "@/lib/utils"

function Avatar({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="avatar"
      className={cn("relative flex size-8 shrink-0 overflow-hidden rounded-full border border-violet-500/30 bg-aurora-subtle font-bold text-xs text-violet-300 items-center justify-center cursor-pointer hover:border-violet-400 transition-all", className)}
      {...props}
    />
  )
}

function AvatarImage({ className, src, alt, ...props }: React.ComponentProps<"img">) {
  if (!src) return null
  return (
    <img
      data-slot="avatar-image"
      src={src}
      alt={alt}
      className={cn("aspect-square size-full object-cover", className)}
      {...props}
    />
  )
}

function AvatarFallback({ className, children, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="avatar-fallback"
      className={cn("flex size-full items-center justify-center rounded-full bg-violet-600/20 text-violet-300 font-semibold", className)}
      {...props}
    >
      {children}
    </div>
  )
}

export { Avatar, AvatarImage, AvatarFallback }
