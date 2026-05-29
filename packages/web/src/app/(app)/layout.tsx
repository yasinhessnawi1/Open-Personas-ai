import { UserButton } from "@clerk/nextjs";
import { AppSidebar } from "@/components/shell/app-sidebar";
import { MobileNav } from "@/components/shell/mobile-nav";
import { ThemeToggle } from "@/components/theme-toggle";

// Authenticated app shell: persistent sidebar (desktop) / sheet (mobile),
// sticky header with theme toggle + Clerk user menu.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-svh">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur">
          <MobileNav />
          <div className="flex-1" />
          <ThemeToggle />
          <UserButton />
        </header>
        <main className="flex flex-1 flex-col">{children}</main>
      </div>
    </div>
  );
}
