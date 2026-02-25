"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api-client";
import { useAppStore } from "@/stores/app-store";
import type { BlacklistEntry, Follower } from "@/lib/types";

// ============================================================
// Add Blacklist Entry Form
// ============================================================
function AddEntryForm({
  followers,
  onAdded,
}: {
  followers: Follower[];
  onAdded: () => void;
}) {
  const [followerId, setFollowerId] = useState("");
  const [symbol, setSymbol] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!followerId || !symbol.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.addBlacklist(
        followerId,
        symbol.trim().toUpperCase(),
        reason || undefined,
      );
      setSymbol("");
      setReason("");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg border border-border bg-card p-4"
    >
      <h2 className="text-sm font-semibold mb-3">Add Blacklist Entry</h2>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Follower</label>
          <select
            value={followerId}
            onChange={(e) => setFollowerId(e.target.value)}
            className="w-44 rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
            required
          >
            <option value="">Select...</option>
            {followers.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} ({f.id})
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Symbol</label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="AAPL"
            className="w-28 rounded-md border border-border bg-card px-3 py-2 text-sm uppercase outline-none focus:ring-1 focus:ring-primary"
            required
          />
        </div>
        <div className="space-y-1 flex-1 min-w-[120px]">
          <label className="text-xs text-muted-foreground">
            Reason (optional)
          </label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. hard to borrow"
            className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/80 disabled:opacity-50"
        >
          {saving ? "Adding..." : "Add"}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
    </form>
  );
}

// ============================================================
// Blacklist Table
// ============================================================
function BlacklistTable({
  entries,
  followers,
  onDelete,
}: {
  entries: BlacklistEntry[];
  followers: Follower[];
  onDelete: (id: number) => void;
}) {
  const [filterFollower, setFilterFollower] = useState("");
  const [filterSymbol, setFilterSymbol] = useState("");

  const filtered = entries.filter((e) => {
    if (filterFollower && e.follower_id !== filterFollower) return false;
    if (filterSymbol && !e.symbol.includes(filterSymbol.toUpperCase()))
      return false;
    return true;
  });

  const followerName = (id: string) =>
    followers.find((f) => f.id === id)?.name || id;

  return (
    <div className="rounded-lg border border-border bg-card">
      {/* Filters */}
      <div className="flex items-center gap-3 border-b border-border p-3">
        <select
          value={filterFollower}
          onChange={(e) => setFilterFollower(e.target.value)}
          className="rounded-md border border-border bg-card px-2 py-1.5 text-sm outline-none"
        >
          <option value="">All followers</option>
          {followers.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={filterSymbol}
          onChange={(e) => setFilterSymbol(e.target.value)}
          placeholder="Filter by symbol..."
          className="rounded-md border border-border bg-card px-2 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary"
        />
        <span className="text-xs text-muted-foreground ml-auto">
          {filtered.length} of {entries.length} entries
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th className="px-4 py-2 text-left">Follower</th>
              <th className="px-4 py-2 text-left">Symbol</th>
              <th className="px-4 py-2 text-left">Reason</th>
              <th className="px-4 py-2 text-left">Added</th>
              <th className="px-4 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="py-8 text-center text-muted-foreground"
                >
                  No blacklist entries found.
                </td>
              </tr>
            )}
            {filtered.map((entry) => (
              <tr
                key={entry.id}
                className="border-b border-border/50 hover:bg-card/80"
              >
                <td className="px-4 py-2">
                  <span className="font-medium">
                    {followerName(entry.follower_id)}
                  </span>
                  <span className="ml-1 text-xs text-muted-foreground">
                    ({entry.follower_id})
                  </span>
                </td>
                <td className="px-4 py-2 font-medium">{entry.symbol}</td>
                <td className="px-4 py-2 text-muted-foreground">
                  {entry.reason || "—"}
                </td>
                <td className="px-4 py-2 text-xs text-muted-foreground">
                  {new Date(entry.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => onDelete(entry.id)}
                    className="rounded px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================
// Blacklist Page
// ============================================================
export default function BlacklistPage() {
  const followers = useAppStore((s) => s.followers);
  const setFollowers = useAppStore((s) => s.setFollowers);
  const [entries, setEntries] = useState<BlacklistEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [followersData, blacklist] = await Promise.all([
        api.getFollowers(),
        api.getBlacklist(),
      ]);
      setFollowers(followersData);
      setEntries(blacklist);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [setFollowers]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = async (id: number) => {
    try {
      await api.removeBlacklist(id);
      setEntries((prev) => prev.filter((e) => e.id !== id));
    } catch {
      alert("Failed to remove entry");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Blacklist</h1>
        <p className="text-sm text-muted-foreground">
          Manage per-follower per-symbol trade restrictions
        </p>
      </div>

      <AddEntryForm followers={followers} onAdded={load} />

      <BlacklistTable
        entries={entries}
        followers={followers}
        onDelete={handleDelete}
      />
    </div>
  );
}
