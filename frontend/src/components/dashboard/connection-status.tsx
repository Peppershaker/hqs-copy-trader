"use client";

import { useAppStore } from "@/stores/app-store";
import { cn } from "@/lib/utils";
import { Power, PowerOff } from "lucide-react";
import { api } from "@/lib/api-client";
import { useState } from "react";

export function ConnectionStatus() {
  const systemStatus = useAppStore((s) => s.systemStatus);
  const [loading, setLoading] = useState(false);

  const isRunning = systemStatus?.running ?? false;

  const handleToggle = async () => {
    setLoading(true);
    try {
      if (isRunning) {
        await api.stopSystem();
      } else {
        await api.startSystem();
      }
    } catch (e) {
      console.error("Failed to toggle system:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleToggle}
        disabled={loading}
        className={cn(
          "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition-colors",
          isRunning
            ? "bg-destructive/10 text-destructive hover:bg-destructive/20"
            : "bg-success/10 text-success hover:bg-success/20",
          loading && "opacity-50 cursor-not-allowed",
        )}
      >
        {isRunning ? (
          <>
            <PowerOff className="h-4 w-4" />
            Stop
          </>
        ) : (
          <>
            <Power className="h-4 w-4" />
            Start
          </>
        )}
      </button>
    </div>
  );
}
