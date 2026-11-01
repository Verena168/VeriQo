/**
 * Pure classification of editor changes into typed / pasted / bulk-inserted characters.
 * No `vscode` import, so it is unit-tested with plain Node (see src/test).
 *
 * Privacy: only lengths, line counts, file extensions and timestamps leave this module,
 * never the text itself.
 */

import { randomUUID } from "node:crypto";

export const LARGE_PASTE_CHARS = 200; // pastes/inserts this big are recorded as individual events
export const BULK_INSERT_CHARS = 30; // a single non-paste insertion this big is not "typing"
export const PASTE_WINDOW_MS = 1500; // how long after the paste command a change counts as the paste
export const IDLE_MS = 60_000; // gaps longer than this are not active time
const MAX_EVENTS_PER_BATCH = 500;

export interface Change {
  inserted: string;
  deletedLength: number;
}

export interface PasteEvent {
  ts: string;
  chars: number;
  lines: number;
  file_ext: string | null;
  source: "clipboard" | "bulk_insert";
}

export interface Metrics {
  typed_chars: number;
  pasted_chars: number;
  paste_count: number;
  deleted_chars: number;
  active_seconds: number;
  bulk_insert_chars: number;
  ai_completion_accepts: number;
  chars_by_ext: Record<string, number>;
}

export interface Batch {
  batch_id: string;
  session_id: string;
  hackathon_id: string;
  window_start: string;
  window_end: string;
  metrics: Metrics;
  paste_events: PasteEvent[];
  extension_version: string;
}

const emptyMetrics = (): Metrics => ({
  typed_chars: 0,
  pasted_chars: 0,
  paste_count: 0,
  deleted_chars: 0,
  active_seconds: 0,
  bulk_insert_chars: 0,
  ai_completion_accepts: 0,
  chars_by_ext: {},
});

/** ".PY" -> ".py" for events, "py" for chars_by_ext; null when the file has no usable extension. */
export function extOf(path: string): string | null {
  const m = /\.([A-Za-z0-9]{1,10})$/.exec(path);
  return m ? m[1].toLowerCase() : null;
}

const lineCount = (s: string) => s.split("\n").length;

export class Tracker {
  private metrics = emptyMetrics();
  private events: PasteEvent[] = [];
  private windowStart: Date;
  private lastActivity: number | null = null;
  private activeMs = 0;
  private pendingPaste: { at: number; expected: number } | null = null;
  readonly sessionId = randomUUID();

  constructor(
    readonly hackathonId: string,
    readonly version: string,
    private now: () => number = Date.now,
  ) {
    this.windowStart = new Date(this.now());
  }

  /** Called by the paste command just before the built-in paste runs. */
  markPaste(clipboardLength: number): void {
    this.pendingPaste = { at: this.now(), expected: clipboardLength };
  }

  /** Any sign of activity (edit, selection, scroll) in a tracked file. */
  touch(): void {
    const t = this.now();
    if (this.lastActivity !== null && t - this.lastActivity <= IDLE_MS) this.activeMs += t - this.lastActivity;
    this.lastActivity = t;
  }

  /** Window lost focus: the gap until the next activity is not counted. */
  pause(): void {
    this.lastActivity = null;
  }

  /** One onDidChangeTextDocument event (undo/redo must be filtered out by the caller). */
  recordChanges(changes: Change[], filePath: string): void {
    const t = this.now();
    this.touch();
    const ext = extOf(filePath);
    const inserted = changes.reduce((n, c) => n + c.inserted.length, 0);

    if (this.pendingPaste && t - this.pendingPaste.at <= PASTE_WINDOW_MS && inserted > 0) {
      this.pendingPaste = null;
      this.metrics.pasted_chars += inserted;
      this.metrics.paste_count += 1;
      for (const c of changes) this.metrics.deleted_chars += c.deletedLength;
      if (inserted >= LARGE_PASTE_CHARS) {
        const text = changes.map((c) => c.inserted).join("");
        this.addEvent({ ts: new Date(t).toISOString(), chars: inserted, lines: lineCount(text), file_ext: ext ? `.${ext}` : null, source: "clipboard" });
      }
      return;
    }

    for (const c of changes) {
      const ins = c.inserted.length;
      const del = c.deletedLength;
      // Same-size replacement (format document, rename, refactor): neither typing nor pasting.
      if (ins > BULK_INSERT_CHARS && del > 0 && Math.abs(ins - del) / Math.max(ins, del) < 0.3) continue;
      this.metrics.deleted_chars += del;
      if (c.inserted.trim().length >= BULK_INSERT_CHARS) {
        // Large insertion without a paste: inline AI completion, snippet, or generated code.
        this.metrics.bulk_insert_chars += ins;
        this.metrics.ai_completion_accepts += 1;
        if (ins >= LARGE_PASTE_CHARS) {
          this.addEvent({ ts: new Date(t).toISOString(), chars: ins, lines: lineCount(c.inserted), file_ext: ext ? `.${ext}` : null, source: "bulk_insert" });
        }
      } else if (ins > 0) {
        this.metrics.typed_chars += ins;
        if (ext) this.metrics.chars_by_ext[ext] = (this.metrics.chars_by_ext[ext] || 0) + ins;
      }
    }
  }

  private addEvent(e: PasteEvent): void {
    if (this.events.length < MAX_EVENTS_PER_BATCH) this.events.push(e);
  }

  /** Snapshot everything since the last drain into a batch, or null if nothing happened. */
  drain(): Batch | null {
    const end = new Date(this.now());
    this.metrics.active_seconds = Math.min(3600, Math.round(this.activeMs / 1000));
    const m = this.metrics;
    const empty = !m.typed_chars && !m.pasted_chars && !m.deleted_chars && !m.bulk_insert_chars && !m.active_seconds;
    const batch: Batch | null = empty
      ? null
      : {
          batch_id: randomUUID(),
          session_id: this.sessionId,
          hackathon_id: this.hackathonId,
          window_start: this.windowStart.toISOString(),
          window_end: end.toISOString(),
          metrics: m,
          paste_events: this.events,
          extension_version: this.version,
        };
    this.metrics = emptyMetrics();
    this.events = [];
    this.activeMs = 0;
    this.windowStart = end;
    return batch;
  }
}
