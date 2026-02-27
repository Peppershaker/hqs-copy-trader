"use client";

import { useState } from "react";
import { useAppStore } from "@/stores/app-store";
import { api } from "@/lib/api-client";
import type { QueuedAction } from "@/lib/types";

const ACTION_LABELS: Record<string, string> = {
  order_submit: "Submit order",
  order_cancel: "Cancel order",
  order_replace: "Replace order",
};

function ActionRow({
  action,
  checked,
  onToggle,
}: {
  action: QueuedAction;
  checked: boolean;
  onToggle: () => void;
}) {
  const snap = action.payload?.order_snapshot as
    | Record<string, string>
    | undefined;

  return (
    <label className="flex items-start gap-3 rounded-md border border-border p-3 hover:bg-card/80 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-accent">
            {ACTION_LABELS[action.action_type] ?? action.action_type}
          </span>
          <span className="font-medium">{action.symbol}</span>
        </div>

        {/* Extra detail for order submits */}
        {snap && (
          <div className="mt-1 text-xs text-muted-foreground">
            {snap.side} {snap.quantity} shares &middot; {snap.type}
            {snap.price ? ` @ $${snap.price}` : ""}
          </div>
        )}

        <div className="mt-0.5 text-[10px] text-muted-foreground/60">
          Queued at {new Date(action.timestamp * 1000).toLocaleTimeString()}
        </div>
      </div>
    </label>
  );
}

export function ReplayDialog() {
  const replayFollowerId = useAppStore((s) => s.replayFollowerId);
  const queuedActions = useAppStore((s) => s.queuedActions);
  const setReplayFollowerId = useAppStore((s) => s.setReplayFollowerId);
  const clearQueuedActions = useAppStore((s) => s.clearQueuedActions);
  const followers = useAppStore((s) => s.followers);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  if (!replayFollowerId) return null;

  const actions = queuedActions[replayFollowerId] ?? [];
  if (actions.length === 0) return null;

  const followerName =
    followers.find((f) => f.id === replayFollowerId)?.name ?? replayFollowerId;

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const selectAll = () => setSelected(new Set(actions.map((a) => a.id)));

  const selectNone = () => setSelected(new Set());

  const handleReplay = async () => {
    if (selected.size === 0) return;
    setSubmitting(true);
    try {
      const selectedIds = Array.from(selected);
      const discardIds = actions
        .filter((a) => !selected.has(a.id))
        .map((a) => a.id);

      // Replay selected
      await api.replayActions(replayFollowerId, selectedIds);
      // Discard the rest
      if (discardIds.length > 0) {
        await api.discardActions(replayFollowerId, discardIds);
      }
    } catch {
      // errors will surface via WS alerts
    } finally {
      setSubmitting(false);
      clearQueuedActions(replayFollowerId);
      setReplayFollowerId(null);
    }
  };

  const handleDiscardAll = async () => {
    setSubmitting(true);
    try {
      await api.discardActions(
        replayFollowerId,
        actions.map((a) => a.id),
      );
    } catch {
      // ignore
    } finally {
      setSubmitting(false);
      clearQueuedActions(replayFollowerId);
      setReplayFollowerId(null);
    }
  };

  const handleDismiss = () => {
    setReplayFollowerId(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-lg rounded-xl border border-border bg-background p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-4">
          <h2 className="text-lg font-bold">
            Follower Reconnected: {followerName}
          </h2>
          <p className="text-sm text-muted-foreground">
            {actions.length} action{actions.length !== 1 ? "s were" : " was"}{" "}
            queued while this follower was disconnected. Select which to replay.
          </p>
        </div>

        {/* Select helpers */}
        <div className="mb-2 flex gap-3 text-xs">
          <button onClick={selectAll} className="text-primary hover:underline">
            Select all
          </button>
          <button
            onClick={selectNone}
            className="text-muted-foreground hover:underline"
          >
            Deselect all
          </button>
          <span className="ml-auto text-muted-foreground">
            {selected.size} / {actions.length} selected
          </span>
        </div>

        {/* Action list */}
        <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
          {actions.map((action) => (
            <ActionRow
              key={action.id}
              action={action}
              checked={selected.has(action.id)}
              onToggle={() => toggle(action.id)}
            />
          ))}
        </div>

        {/* Buttons */}
        <div className="mt-5 flex items-center gap-2">
          <button
            onClick={handleReplay}
            disabled={submitting || selected.size === 0}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/80 disabled:opacity-50"
          >
            {submitting
              ? "Replaying..."
              : `Replay ${selected.size} action${selected.size !== 1 ? "s" : ""}`}
          </button>
          <button
            onClick={handleDiscardAll}
            disabled={submitting}
            className="rounded-md border border-destructive/50 px-4 py-2 text-sm text-destructive hover:bg-destructive/10 disabled:opacity-50"
          >
            Discard All
          </button>
          <button
            onClick={handleDismiss}
            disabled={submitting}
            className="ml-auto rounded-md border border-border px-4 py-2 text-sm hover:bg-card"
          >
            Decide Later
          </button>
        </div>
      </div>
    </div>
  );
}
