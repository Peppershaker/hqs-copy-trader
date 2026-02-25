"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Settings,
  ShieldBan,
  Users,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/app-store";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/management", label: "Management", icon: Users },
  { href: "/blacklist", label: "Blacklist", icon: ShieldBan },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const wsConnected = useAppStore((s) => s.wsConnected);
  const systemStatus = useAppStore((s) => s.systemStatus);

  const masterConnected = systemStatus?.master?.connected ?? false;
  const followerCount = Object.keys(systemStatus?.followers ?? {}).length;
  const connectedFollowers = Object.values(
    systemStatus?.followers ?? {},
  ).filter((f) => f.connected).length;

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-border bg-card">
      {/* Logo */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-4">
        <Activity className="h-6 w-6 text-primary" />
        <span className="text-sm font-bold tracking-tight">
          DAS Copy Trader
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2 py-4">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Status footer */}
      <div className="border-t border-border px-4 py-3 text-xs space-y-1">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              wsConnected ? "bg-success" : "bg-destructive",
            )}
          />
          <span className="text-muted-foreground">
            WS: {wsConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              masterConnected ? "bg-success" : "bg-muted-foreground",
            )}
          />
          <span className="text-muted-foreground">
            Master: {masterConnected ? "Online" : "Offline"}
          </span>
        </div>
        {followerCount > 0 && (
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                connectedFollowers === followerCount
                  ? "bg-success"
                  : connectedFollowers > 0
                    ? "bg-warning"
                    : "bg-muted-foreground",
              )}
            />
            <span className="text-muted-foreground">
              Followers: {connectedFollowers}/{followerCount}
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
