"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api-client";
import { useAppStore } from "@/stores/app-store";
import type {
  MasterConfigCreate,
  FollowerCreate,
  Follower,
  DasServer,
} from "@/lib/types";

// --- Reusable input field component ---
function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  required,
}: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <input
        type={type}
        className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
      />
    </div>
  );
}

// --- Broker dropdown populated from DAS_SERVERS config ---
function BrokerSelect({
  dasServers,
  value,
  onSelect,
}: {
  dasServers: DasServer[];
  value: string; // lowercase broker_id currently set on the form
  onSelect: (server: DasServer) => void;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">
        Broker
      </label>
      <select
        className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
        value={value}
        onChange={(e) => {
          const server = dasServers.find(
            (s) => s.broker_id.toLowerCase() === e.target.value,
          );
          if (server) onSelect(server);
        }}
      >
        <option value="">Select broker…</option>
        {dasServers.map((s) => (
          <option key={s.broker_id} value={s.broker_id.toLowerCase()}>
            {s.broker_id}
          </option>
        ))}
      </select>
    </div>
  );
}

// --- Account dropdown (falls back to free-text when no accounts available) ---
function AccountSelect({
  accounts,
  value,
  onChange,
}: {
  accounts: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  if (accounts.length === 0) {
    return (
      <Field label="Account ID" value={value} onChange={onChange} required />
    );
  }
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">
        Account ID
      </label>
      <select
        className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
      >
        <option value="">Select account…</option>
        {accounts.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>
    </div>
  );
}

// --- Locate routes toggle editor ---
function LocateRoutesEditor({
  routes,
}: {
  routes: Record<string, number> | null | undefined;
}) {
  if (!routes || Object.keys(routes).length === 0) return null;

  return (
    <div className="col-span-full space-y-2">
      <label className="text-xs font-medium text-muted-foreground">
        Locate Routes{" "}
        <span className="text-muted-foreground/60">
          ({Object.keys(routes).length} routes loaded)
        </span>
      </label>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(routes).map(([route, type]) => (
          <span
            key={route}
            className="rounded border border-border bg-muted px-2 py-0.5 text-xs font-mono text-muted-foreground"
            title={`Type ${type}`}
          >
            {route}
            <span className="ml-1 opacity-50">{type}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// Master Config Form
// ============================================================
function MasterConfigForm() {
  const masterConfig = useAppStore((s) => s.masterConfig);
  const setMasterConfig = useAppStore((s) => s.setMasterConfig);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [dasServers, setDasServers] = useState<DasServer[]>([]);

  const [form, setForm] = useState<MasterConfigCreate>({
    broker_id: "",
    host: "127.0.0.1",
    port: 9910,
    username: "",
    password: "",
    account_id: "",
  });

  useEffect(() => {
    api.getDasServers().then(setDasServers).catch(() => {});
  }, []);

  useEffect(() => {
    if (masterConfig) {
      setForm((prev) => ({
        ...prev,
        broker_id: masterConfig.broker_id,
        host: masterConfig.host,
        port: masterConfig.port,
        username: masterConfig.username,
        account_id: masterConfig.account_id,
      }));
    }
  }, [masterConfig]);

  const handleBrokerSelect = (server: DasServer) => {
    setForm((prev) => ({
      ...prev,
      broker_id: server.broker_id.toLowerCase(),
      host: server.host,
      port: server.port,
      username: server.username,
      password: server.password,
      account_id: "",
      locate_routes: server.locate_routes,
    }));
  };

  const selectedServer = dasServers.find(
    (s) => s.broker_id.toLowerCase() === form.broker_id,
  );

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const saved = await api.updateMaster(form);
      setMasterConfig(saved);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const set = (key: keyof MasterConfigCreate) => (v: string) =>
    setForm((f) => ({ ...f, [key]: key === "port" ? Number(v) : v }));

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="text-base font-semibold mb-4">Master Account</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <BrokerSelect
          dasServers={dasServers}
          value={form.broker_id}
          onSelect={handleBrokerSelect}
        />
        <Field
          label="Host"
          value={form.host}
          onChange={set("host")}
          placeholder="127.0.0.1"
          required
        />
        <Field
          label="Port"
          value={form.port}
          onChange={set("port")}
          type="number"
          required
        />
        <Field
          label="Username"
          value={form.username}
          onChange={set("username")}
          required
        />
        <Field
          label="Password"
          value={form.password}
          onChange={set("password")}
          type="password"
          required
        />
        <AccountSelect
          accounts={selectedServer?.accounts ?? []}
          value={form.account_id}
          onChange={set("account_id")}
        />
        <LocateRoutesEditor routes={form.locate_routes} />
      </div>
      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      {success && <p className="mt-3 text-sm text-success">Saved!</p>}
      <button
        onClick={handleSave}
        disabled={saving}
        className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/80 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Save Master Config"}
      </button>
    </div>
  );
}

// ============================================================
// Follower Form
// ============================================================
const DEFAULT_FOLLOWER: FollowerCreate = {
  id: "",
  name: "",
  broker_id: "",
  host: "127.0.0.1",
  port: 9910,
  username: "",
  password: "",
  account_id: "",
  base_multiplier: 1,
  max_locate_price: 0.10,
  locate_retry_timeout: 15,
  auto_accept_locates: false,
  enabled: true,
  locate_routes: null,
};

function FollowerForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Follower;
  onSave: () => void;
  onCancel?: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dasServers, setDasServers] = useState<DasServer[]>([]);

  const [form, setForm] = useState<FollowerCreate>(() => {
    if (initial) {
      return {
        ...DEFAULT_FOLLOWER,
        id: initial.id,
        name: initial.name,
        broker_id: initial.broker_id,
        host: initial.host,
        port: initial.port,
        username: initial.username,
        password: "",
        account_id: initial.account_id,
        base_multiplier: initial.base_multiplier,
        max_locate_price: initial.max_locate_price,
        locate_retry_timeout: initial.locate_retry_timeout,
        auto_accept_locates: initial.auto_accept_locates,
        enabled: initial.enabled,
        locate_routes: initial.locate_routes ?? null,
      };
    }
    return { ...DEFAULT_FOLLOWER };
  });

  useEffect(() => {
    api.getDasServers().then(setDasServers).catch(() => {});
  }, []);

  const handleBrokerSelect = (server: DasServer) => {
    setForm((prev) => ({
      ...prev,
      broker_id: server.broker_id.toLowerCase(),
      host: server.host,
      port: server.port,
      username: server.username,
      password: server.password,
      account_id: "",
      locate_routes: server.locate_routes,
    }));
  };

  const selectedServer = dasServers.find(
    (s) => s.broker_id.toLowerCase() === form.broker_id,
  );

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      if (initial) {
        await api.updateFollower(initial.id, {
          ...form,
        } as unknown as Partial<Follower>);
      } else {
        await api.createFollower(form);
      }
      onSave();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const set = (key: keyof FollowerCreate) => (v: string) =>
    setForm((f) => ({
      ...f,
      [key]: [
        "port",
        "base_multiplier",
        "max_locate_price",
        "locate_retry_timeout",
      ].includes(key)
        ? Number(v)
        : v,
    }));

  return (
    <div className="rounded-lg border border-border bg-card/50 p-4">
      <h3 className="text-sm font-semibold mb-3">
        {initial ? `Edit: ${initial.name}` : "Add Follower Account"}
      </h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field
          label="ID (unique)"
          value={form.id}
          onChange={set("id")}
          placeholder="follower1"
          required
        />
        <Field
          label="Display Name"
          value={form.name}
          onChange={set("name")}
          placeholder="Follower 1"
          required
        />
        <BrokerSelect
          dasServers={dasServers}
          value={form.broker_id}
          onSelect={handleBrokerSelect}
        />
        <Field label="Host" value={form.host} onChange={set("host")} required />
        <Field
          label="Port"
          value={form.port}
          onChange={set("port")}
          type="number"
          required
        />
        <Field
          label="Username"
          value={form.username}
          onChange={set("username")}
          required
        />
        <Field
          label="Password"
          value={form.password}
          onChange={set("password")}
          type="password"
          required
        />
        <AccountSelect
          accounts={selectedServer?.accounts ?? []}
          value={form.account_id}
          onChange={set("account_id")}
        />
        <LocateRoutesEditor routes={form.locate_routes} />
        <Field
          label="Base Multiplier"
          value={form.base_multiplier ?? 1}
          onChange={set("base_multiplier")}
          type="number"
        />
        <Field
          label="Max Locate ($)"
          value={form.max_locate_price ?? 0.10}
          onChange={set("max_locate_price")}
          type="number"
        />
        <Field
          label="Locate Retry (s)"
          value={form.locate_retry_timeout ?? 15}
          onChange={set("locate_retry_timeout")}
          type="number"
        />
        <div className="flex items-end gap-2 pb-1">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="rounded"
              checked={form.auto_accept_locates ?? false}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  auto_accept_locates: e.target.checked,
                }))
              }
            />
            Auto-accept locates
          </label>
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
      <div className="mt-3 flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/80 disabled:opacity-50"
        >
          {saving ? "Saving..." : initial ? "Update" : "Add Follower"}
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            className="rounded-md border border-border px-4 py-2 text-sm hover:bg-card"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Follower List Item
// ============================================================
function FollowerCard({
  follower,
  onEdit,
  onReload,
}: {
  follower: Follower;
  onEdit: () => void;
  onReload: () => void;
}) {
  const systemStatus = useAppStore((s) => s.systemStatus);
  const connected = systemStatus?.followers?.[follower.id]?.connected ?? false;
  const systemRunning = systemStatus?.running ?? false;
  const [deleting, setDeleting] = useState(false);
  const [toggling, setToggling] = useState(false);

  const handleDelete = async () => {
    if (!confirm(`Delete follower "${follower.name}"?`)) return;
    setDeleting(true);
    try {
      await api.deleteFollower(follower.id);
      onReload();
    } catch {
      alert("Failed to delete follower");
    } finally {
      setDeleting(false);
    }
  };

  const handleToggle = async () => {
    setToggling(true);
    try {
      await api.toggleFollower(follower.id);
      onReload();
    } catch {
      alert("Failed to toggle follower");
    } finally {
      setToggling(false);
    }
  };

  // Status: connected (green), enabled but not connected (yellow), disabled (gray)
  const statusColor = connected
    ? "bg-success"
    : follower.enabled
      ? "bg-warning"
      : "bg-muted-foreground";

  const statusText = connected
    ? "Connected"
    : follower.enabled
      ? systemRunning
        ? "Disconnected"
        : "Enabled · Not running"
      : "Disabled";

  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-card p-4">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${statusColor}`} />
          <span className="font-medium">{follower.name}</span>
          {follower.id && (
            <span className="text-xs text-muted-foreground font-mono">
              {follower.id}
            </span>
          )}
          <span className="text-xs text-muted-foreground">·</span>
          <span className="text-xs text-muted-foreground">{statusText}</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>Broker: {follower.broker_id.toUpperCase()}</span>
          <span>Account: {follower.account_id}</span>
          <span>User: {follower.username}</span>
          <span>Multiplier: {follower.base_multiplier}×</span>
          <span>Max Locate: ${follower.max_locate_price}</span>
          <span>
            {follower.host}:{follower.port}
          </span>
        </div>
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleToggle}
          disabled={toggling}
          className={`rounded-md px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${
            follower.enabled
              ? "bg-success/20 text-success hover:bg-success/30"
              : "bg-muted text-muted-foreground hover:bg-muted/80"
          }`}
        >
          {toggling ? "..." : follower.enabled ? "Enabled" : "Disabled"}
        </button>
        <button
          onClick={onEdit}
          className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-card/80"
        >
          Edit
        </button>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="rounded-md border border-destructive/50 px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10 disabled:opacity-50"
        >
          Delete
        </button>
      </div>
    </div>
  );
}

// ============================================================
// Settings Page
// ============================================================
export default function SettingsPage() {
  const followers = useAppStore((s) => s.followers);
  const setFollowers = useAppStore((s) => s.setFollowers);
  const setMasterConfig = useAppStore((s) => s.setMasterConfig);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [master, followers] = await Promise.all([
        api.getMaster(),
        api.getFollowers(),
      ]);
      setMasterConfig(master);
      setFollowers(followers);
    } catch {
      // silently continue — the connection status indicators already signal issues
    }
  }, [setMasterConfig, setFollowers]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure master and follower accounts
        </p>
      </div>

      <MasterConfigForm />

      {/* Follower list */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Follower Accounts</h2>
          {!showAdd && (
            <button
              onClick={() => setShowAdd(true)}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/80"
            >
              + Add Follower
            </button>
          )}
        </div>

        {showAdd && (
          <FollowerForm
            onSave={() => {
              setShowAdd(false);
              loadData();
            }}
            onCancel={() => setShowAdd(false)}
          />
        )}

        {followers.map((f) =>
          editingId === f.id ? (
            <FollowerForm
              key={f.id}
              initial={f}
              onSave={() => {
                setEditingId(null);
                loadData();
              }}
              onCancel={() => setEditingId(null)}
            />
          ) : (
            <FollowerCard
              key={f.id}
              follower={f}
              onEdit={() => setEditingId(f.id)}
              onReload={loadData}
            />
          ),
        )}

        {followers.length === 0 && !showAdd && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No follower accounts configured yet.
          </p>
        )}
      </div>
    </div>
  );
}
