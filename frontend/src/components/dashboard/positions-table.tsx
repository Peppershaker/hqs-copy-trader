"use client";

import type { Position } from "@/lib/types";
import { cn, formatCurrency, formatNumber, formatPnL } from "@/lib/utils";

interface PositionsTableProps {
  positions: Position[];
  title: string;
  showMultiplier?: boolean;
}

export function PositionsTable({
  positions,
  title,
  showMultiplier = false,
}: PositionsTableProps) {
  const totalPnL = positions.reduce((sum, p) => sum + p.total_pnl, 0);

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span
          className={cn(
            "text-sm font-mono font-semibold",
            totalPnL > 0
              ? "text-success"
              : totalPnL < 0
                ? "text-destructive"
                : "text-muted-foreground",
          )}
        >
          {formatPnL(totalPnL)}
        </span>
      </div>

      {positions.length === 0 ? (
        <div className="px-4 py-8 text-center text-sm text-muted-foreground">
          No open positions
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-2 font-medium">Symbol</th>
                <th className="px-4 py-2 font-medium">Side</th>
                <th className="px-4 py-2 font-medium text-right">Qty</th>
                <th className="px-4 py-2 font-medium text-right">Avg Cost</th>
                <th className="px-4 py-2 font-medium text-right">Last</th>
                <th className="px-4 py-2 font-medium text-right">P&L</th>
                {showMultiplier && (
                  <th className="px-4 py-2 font-medium text-right">Mult.</th>
                )}
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => (
                <tr
                  key={pos.symbol}
                  className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                >
                  <td className="px-4 py-2 font-mono font-semibold">
                    {pos.symbol}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={cn(
                        "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold",
                        pos.side === "LONG"
                          ? "bg-success/10 text-success"
                          : "bg-destructive/10 text-destructive",
                      )}
                    >
                      {pos.side}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {formatNumber(Math.abs(pos.quantity))}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {formatCurrency(pos.avg_cost)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {pos.last_price ? formatCurrency(pos.last_price) : "—"}
                  </td>
                  <td
                    className={cn(
                      "px-4 py-2 text-right font-mono font-semibold",
                      pos.total_pnl > 0
                        ? "text-success"
                        : pos.total_pnl < 0
                          ? "text-destructive"
                          : "",
                    )}
                  >
                    {formatPnL(pos.total_pnl)}
                  </td>
                  {showMultiplier && (
                    <td className="px-4 py-2 text-right font-mono text-xs">
                      <span
                        className={cn(
                          "rounded px-1 py-0.5",
                          pos.multiplier_source === "auto_inferred"
                            ? "bg-warning/10 text-warning"
                            : pos.multiplier_source === "user_override"
                              ? "bg-accent/10 text-accent"
                              : "",
                        )}
                      >
                        {pos.effective_multiplier?.toFixed(2)}×
                      </span>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
