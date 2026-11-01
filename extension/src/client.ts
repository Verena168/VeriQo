import type { Batch } from "./tracker";

export class AuthError extends Error {}

export interface Hackathon {
  id: string;
  event_name: string;
  phase: "upcoming" | "live" | "ended";
  start_date: string;
  end_date: string;
}

/** Minimal VERIQO API client. Uses the fetch built into the VS Code extension host. */
export class VeriqoClient {
  constructor(
    private baseUrl: () => string,
    private token: () => Promise<string | undefined>,
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<{ status: number; body: T }> {
    const token = await this.token();
    const res = await fetch(this.baseUrl().replace(/\/$/, "") + path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers || {}),
      },
      signal: AbortSignal.timeout(15_000),
    });
    if (res.status === 401) throw new AuthError("Not signed in to VERIQO");
    const body = (await res.json().catch(() => null)) as T;
    if (!res.ok && res.status !== 409) {
      const detail = (body as { detail?: unknown })?.detail;
      throw Object.assign(new Error(typeof detail === "string" ? detail : `VERIQO API error ${res.status}`), { status: res.status });
    }
    return { status: res.status, body };
  }

  async login(email: string, password: string): Promise<{ access_token: string; user: { name: string; role: string } }> {
    return (await this.request<{ access_token: string; user: { name: string; role: string } }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    })).body;
  }

  async myHackathons(): Promise<Hackathon[]> {
    return (await this.request<Hackathon[]>("/hackathons/mine")).body;
  }

  async summary(hackathonId: string): Promise<Record<string, number | string | null>> {
    return (await this.request<Record<string, number | string | null>>(`/telemetry/summary?hackathon_id=${hackathonId}`)).body;
  }

  async send(batch: Batch): Promise<void> {
    await this.request("/telemetry", { method: "POST", body: JSON.stringify(batch) });
  }
}

/**
 * Batches waiting to be sent, persisted so nothing is lost offline or across restarts.
 * Retries are safe: the server ignores a batch_id it has already stored.
 */
export class BatchQueue {
  static readonly MAX = 500;

  constructor(
    private load: () => Batch[],
    private save: (q: Batch[]) => Thenable<void>,
  ) {}

  get size(): number {
    return this.load().length;
  }

  async push(b: Batch): Promise<void> {
    const q = [...this.load(), b];
    await this.save(q.slice(-BatchQueue.MAX));
  }

  /** Send in order; stop at the first network failure and keep the rest for later. */
  async flush(client: VeriqoClient, onDrop: (b: Batch, err: Error) => void): Promise<number> {
    let q = this.load();
    let sent = 0;
    while (q.length) {
      try {
        await client.send(q[0]);
        sent++;
      } catch (err) {
        const status = (err as { status?: number }).status;
        if (err instanceof AuthError || status === undefined || status >= 500) break; // retry later
        onDrop(q[0], err as Error); // 4xx: the server will never accept it
      }
      q = q.slice(1);
      await this.save(q);
    }
    return sent;
  }
}
