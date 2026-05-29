import { Brand } from "./brand";
import { SidebarBody } from "./sidebar-body";

// Desktop sidebar (hidden on mobile — the mobile sheet covers that breakpoint).
export function AppSidebar() {
  return (
    <aside className="hidden w-64 shrink-0 flex-col gap-6 border-r border-sidebar-border bg-sidebar p-4 md:flex">
      <Brand className="px-1 pt-1" />
      <SidebarBody />
    </aside>
  );
}
