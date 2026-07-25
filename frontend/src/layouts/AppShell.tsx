import { Outlet } from "react-router-dom"
import { AppLayout } from "@/components/layout/AppLayout"

export function AppShell() {
  return (
    <AppLayout>
      <Outlet />
    </AppLayout>
  )
}
