const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`API error ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string | null } = {}
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(response.status, data);
  }
  return data as T;
}

export const api = {
  requestMagicLink: (email: string, purpose: "organiser_login" | "volunteer_login", raceId?: number) =>
    request<{ detail: string; magic_link_url: string }>("/auth/magic-link/request", {
      method: "POST",
      body: { email, purpose, race_id: raceId },
    }),

  consumeMagicLink: (token: string) =>
    request("/auth/magic-link/consume", { method: "POST", body: { token } }),

  bulkSyncTimings: (
    token: string,
    deviceId: string,
    items: Array<{
      client_event_id: string;
      bib_number: string;
      timestamp: string;
      mode: "qr" | "manual";
      success: boolean;
      notes: string;
    }>
  ) =>
    request<{
      results: Array<{ client_event_id: string; status: string; matched: boolean; is_duplicate?: boolean }>;
    }>("/timings/bulk-sync", {
      method: "POST",
      token,
      body: { device_id: deviceId, items },
    }),
};

export { API_BASE_URL };
