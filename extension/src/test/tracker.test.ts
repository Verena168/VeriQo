import * as assert from "node:assert/strict";
import { test } from "node:test";
import { BULK_INSERT_CHARS, IDLE_MS, LARGE_PASTE_CHARS, PASTE_WINDOW_MS, Tracker, extOf } from "../tracker";

function clock(start = Date.UTC(2026, 9, 12, 10, 0, 0)) {
  let t = start;
  return { now: () => t, advance: (ms: number) => (t += ms) };
}

const type = (tr: Tracker, text: string, file = "/p/app.py") => {
  for (const ch of text) tr.recordChanges([{ inserted: ch, deletedLength: 0 }], file);
};

test("keystrokes count as typed, per extension", () => {
  const c = clock();
  const tr = new Tracker("h", "0.1.0", c.now);
  type(tr, "print('hi')");
  type(tr, "let x", "/p/ui.TSX");
  const b = tr.drain()!;
  assert.equal(b.metrics.typed_chars, 16);
  assert.deepEqual(b.metrics.chars_by_ext, { py: 11, tsx: 5 });
  assert.equal(b.metrics.pasted_chars, 0);
});

test("a change right after the paste command is a paste; large pastes become events", () => {
  const c = clock();
  const tr = new Tracker("h", "0.1.0", c.now);
  const big = "x = 1\n".repeat(60);
  tr.markPaste(big.length);
  c.advance(50);
  tr.recordChanges([{ inserted: big, deletedLength: 0 }], "/p/a.py");
  const b = tr.drain()!;
  assert.equal(b.metrics.pasted_chars, big.length);
  assert.equal(b.metrics.paste_count, 1);
  assert.equal(b.metrics.typed_chars, 0);
  assert.equal(b.paste_events.length, 1);
  assert.equal(b.paste_events[0].source, "clipboard");
  assert.equal(b.paste_events[0].lines, 61);
  assert.equal(b.paste_events[0].file_ext, ".py");
  assert.ok(big.length >= LARGE_PASTE_CHARS);
});

test("paste marker expires, so later typing is not a paste", () => {
  const c = clock();
  const tr = new Tracker("h", "0.1.0", c.now);
  tr.markPaste(5);
  c.advance(PASTE_WINDOW_MS + 1);
  type(tr, "abc");
  assert.equal(tr.drain()!.metrics.typed_chars, 3);
});

test("large insertion without paste is bulk insert (likely AI completion)", () => {
  const c = clock();
  const tr = new Tracker("h", "0.1.0", c.now);
  const completion = "def add(a, b):\n    return a + b\n";
  assert.ok(completion.trim().length >= BULK_INSERT_CHARS);
  tr.recordChanges([{ inserted: completion, deletedLength: 0 }], "/p/a.py");
  const b = tr.drain()!;
  assert.equal(b.metrics.bulk_insert_chars, completion.length);
  assert.equal(b.metrics.ai_completion_accepts, 1);
  assert.equal(b.metrics.typed_chars, 0);
  assert.equal(b.paste_events.length, 0); // under LARGE_PASTE_CHARS
});

test("same-size replacement (formatting) is ignored", () => {
  const c = clock();
  const tr = new Tracker("h", "0.1.0", c.now);
  tr.recordChanges([{ inserted: "a".repeat(100), deletedLength: 95 }], "/p/a.py");
  assert.equal(tr.drain(), null);
});

test("active time accumulates only across short gaps and pauses", () => {
  const c = clock();
  const tr = new Tracker("h", "0.1.0", c.now);
  tr.touch();
  c.advance(20_000);
  tr.touch(); // +20s
  c.advance(IDLE_MS + 1);
  tr.touch(); // idle gap: not counted
  c.advance(10_000);
  tr.pause();
  c.advance(5_000);
  tr.touch(); // after pause: not counted
  c.advance(5_000);
  tr.touch(); // +5s
  assert.equal(tr.drain()!.metrics.active_seconds, 25);
});

test("drain resets state and chains windows; empty windows produce no batch", () => {
  const c = clock();
  const tr = new Tracker("h", "0.1.0", c.now);
  type(tr, "ab");
  c.advance(30_000);
  const first = tr.drain()!;
  assert.equal(tr.drain(), null);
  type(tr, "c");
  c.advance(30_000);
  const second = tr.drain()!;
  assert.equal(second.window_start, first.window_end);
  assert.notEqual(second.batch_id, first.batch_id);
  assert.equal(second.session_id, first.session_id);
  assert.equal(second.metrics.typed_chars, 1);
});

test("extOf", () => {
  assert.equal(extOf("C:\\proj\\Main.JAVA"), "java");
  assert.equal(extOf("/proj/Makefile"), null);
});
