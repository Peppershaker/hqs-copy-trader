/** REST API client for the backend. */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json();
}

export const api = {
  // Master
  getMaster: () =>
    request<import("./types").MasterConfig | null>("/api/master"),
  updateMaster: (data: import("./types").MasterConfigCreate) =>
    request<import("./types").MasterConfig>("/api/master", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Followers
  getFollowers: () => request<import("./types").Follower[]>("/api/followers"),
  createFollower: (data: import("./types").FollowerCreate) =>
    request<import("./types").Follower>("/api/followers", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateFollower: (id: string, data: Partial<import("./types").Follower>) =>
    request<import("./types").Follower>(`/api/followers/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteFollower: (id: string) =>
    request<void>(`/api/followers/${id}`, { method: "DELETE" }),
  updateMultiplier: (id: string, multiplier: number) =>
    request<import("./types").Follower>(`/api/followers/${id}/multiplier`, {
      method: "PATCH",
      body: JSON.stringify({ base_multiplier: multiplier }),
    }),
  toggleFollower: (id: string) =>
    request<import("./types").Follower>(`/api/followers/${id}/toggle`, {
      method: "PATCH",
    }),

  // Blacklist
  getBlacklist: (followerId?: string) => {
    const params = followerId ? `?follower_id=${followerId}` : "";
    return request<import("./types").BlacklistEntry[]>(
      `/api/blacklist${params}`,
    );
  },
  addBlacklist: (followerId: string, symbol: string, reason?: string) =>
    request<import("./types").BlacklistEntry>("/api/blacklist", {
      method: "POST",
      body: JSON.stringify({ follower_id: followerId, symbol, reason }),
    }),
  removeBlacklist: (id: number) =>
    request<void>(`/api/blacklist/${id}`, { method: "DELETE" }),

  // Multipliers
  getMultipliers: (followerId: string) =>
    request<import("./types").SymbolMultiplier[]>(
      `/api/multipliers/${followerId}`,
    ),
  setMultiplier: (followerId: string, symbol: string, multiplier: number) =>
    request<import("./types").SymbolMultiplier>(
      `/api/multipliers/${followerId}/${symbol}`,
      {
        method: "PUT",
        body: JSON.stringify({ multiplier }),
      },
    ),
  removeMultiplier: (followerId: string, symbol: string) =>
    request<void>(`/api/multipliers/${followerId}/${symbol}`, {
      method: "DELETE",
    }),

  // Locates
  acceptLocate: (locateMapId: number) =>
    request<Record<string, unknown>>(`/api/locates/${locateMapId}/accept`, {
      method: "POST",
    }),
  rejectLocate: (locateMapId: number) =>
    request<Record<string, unknown>>(`/api/locates/${locateMapId}/reject`, {
      method: "POST",
    }),

  // System
  getStatus: () => request<import("./types").SystemStatus>("/api/status"),
  startSystem: () =>
    request<Record<string, unknown>>("/api/start", { method: "POST" }),
  stopSystem: () =>
    request<Record<string, unknown>>("/api/stop", { method: "POST" }),

  // Queued Actions
  getQueuedActions: (followerId: string) =>
    request<import("./types").QueuedAction[]>(
      `/api/queued-actions/${followerId}`,
    ),
  getAllQueuedActions: () =>
    request<Record<string, import("./types").QueuedAction[]>>(
      "/api/queued-actions",
    ),
  replayActions: (followerId: string, actionIds: string[]) =>
    request<Record<string, unknown>>(
      `/api/queued-actions/${followerId}/replay`,
      {
        method: "POST",
        body: JSON.stringify({ action_ids: actionIds }),
      },
    ),
  discardActions: (followerId: string, actionIds: string[]) =>
    request<Record<string, unknown>>(
      `/api/queued-actions/${followerId}/discard`,
      {
        method: "POST",
        body: JSON.stringify({ action_ids: actionIds }),
      },
    ),
  // DAS Server configs
  getDasServers: () =>
    request<import("./types").DasServer[]>("/api/das-servers"),

  getAuditLog: (params?: {
    limit?: number;
    offset?: number;
    category?: string;
    level?: string;
  }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    if (params?.category) query.set("category", params.category);
    if (params?.level) query.set("level", params.level);
    const qs = query.toString();
    return request<{
      entries: import("./types").AuditLogEntry[];
      limit: number;
      offset: number;
    }>(`/api/audit-log${qs ? `?${qs}` : ""}`);
  },
  // Env Config
  getEnvConfig: () =>
    request<import("./types").EnvConfigResponse>("/api/env-config"),
  saveEnvConfig: (content: string) =>
    request<import("./types").EnvConfigResponse>("/api/env-config", {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
};
