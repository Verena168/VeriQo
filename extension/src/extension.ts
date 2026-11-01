import * as path from "node:path";
import * as vscode from "vscode";
import { AuthError, BatchQueue, VeriqoClient } from "./client";
import { Batch, Tracker } from "./tracker";

const TOKEN_KEY = "veriqo.token";
const STATE_KEY = "veriqo.tracking"; // { hackathonId, hackathonName, folder }
const QUEUE_KEY = "veriqo.queue";
const FLUSH_MS = 30_000;

interface TrackingState {
  hackathonId: string;
  hackathonName: string;
  folder: string;
}

let tracker: Tracker | null = null;
let trackingState: TrackingState | null = null;
let flushTimer: NodeJS.Timeout | undefined;
let status: vscode.StatusBarItem;
let output: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext): void {
  output = vscode.window.createOutputChannel("VERIQO");
  const config = () => vscode.workspace.getConfiguration("veriqo");
  const client = new VeriqoClient(
    () => config().get<string>("apiUrl", "http://localhost:8000/api/v1"),
    () => Promise.resolve(context.secrets.get(TOKEN_KEY)),
  );
  const queue = new BatchQueue(
    () => context.globalState.get<Batch[]>(QUEUE_KEY, []),
    (q) => context.globalState.update(QUEUE_KEY, q),
  );
  const version = (context.extension.packageJSON as { version: string }).version;

  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = "veriqo.showStatus";
  status.show();
  context.subscriptions.push(status, output);

  const updateStatus = () => {
    if (trackingState) {
      status.text = "$(record) VERIQO tracking";
      status.tooltip = `Tracking ${trackingState.hackathonName}\nFolder: ${trackingState.folder}\nQueued batches: ${queue.size}`;
    } else {
      status.text = "$(circle-slash) VERIQO";
      status.tooltip = "VERIQO telemetry is off. Click for options.";
    }
  };

  const inScope = (doc: vscode.TextDocument) =>
    trackingState !== null &&
    doc.uri.scheme === "file" &&
    !path.relative(trackingState.folder, doc.uri.fsPath).startsWith("..") &&
    !path.isAbsolute(path.relative(trackingState.folder, doc.uri.fsPath));

  const flush = async () => {
    if (tracker) {
      const batch = tracker.drain();
      if (batch) await queue.push(batch);
    }
    try {
      const sent = await queue.flush(client, (b, err) => output.appendLine(`Dropped batch ${b.batch_id}: ${err.message}`));
      if (sent) output.appendLine(`Synced ${sent} batch(es)`);
    } catch (err) {
      output.appendLine(`Sync failed: ${(err as Error).message}`);
    }
    if (!(await context.secrets.get(TOKEN_KEY)) && trackingState) {
      vscode.window.showWarningMessage("VERIQO: you are signed out, so activity is queued but not uploaded.", "Sign in").then((c) => {
        if (c) vscode.commands.executeCommand("veriqo.signIn");
      });
    }
    updateStatus();
  };

  const start = (state: TrackingState) => {
    trackingState = state;
    tracker = new Tracker(state.hackathonId, version);
    clearInterval(flushTimer);
    flushTimer = setInterval(flush, FLUSH_MS);
    vscode.commands.executeCommand("setContext", "veriqo.tracking", true);
    updateStatus();
  };

  const stop = async () => {
    await flush();
    clearInterval(flushTimer);
    tracker = null;
    trackingState = null;
    await context.workspaceState.update(STATE_KEY, undefined);
    vscode.commands.executeCommand("setContext", "veriqo.tracking", false);
    updateStatus();
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("veriqo.signIn", async () => {
      const email = await vscode.window.showInputBox({ prompt: "VERIQO email", ignoreFocusOut: true });
      if (!email) return;
      const password = await vscode.window.showInputBox({ prompt: "VERIQO password", password: true, ignoreFocusOut: true });
      if (!password) return;
      try {
        const res = await client.login(email, password);
        if (res.user.role !== "participant") {
          vscode.window.showErrorMessage("VERIQO: only participant accounts record telemetry.");
          return;
        }
        await context.secrets.store(TOKEN_KEY, res.access_token);
        vscode.window.showInformationMessage(`VERIQO: signed in as ${res.user.name}.`);
        await flush();
      } catch (err) {
        vscode.window.showErrorMessage(`VERIQO: ${err instanceof AuthError ? "incorrect email or password" : (err as Error).message}`);
      }
    }),

    vscode.commands.registerCommand("veriqo.signOut", async () => {
      await context.secrets.delete(TOKEN_KEY);
      vscode.window.showInformationMessage("VERIQO: signed out.");
    }),

    vscode.commands.registerCommand("veriqo.startTracking", async () => {
      if (!(await context.secrets.get(TOKEN_KEY))) {
        await vscode.commands.executeCommand("veriqo.signIn");
        if (!(await context.secrets.get(TOKEN_KEY))) return;
      }
      let hackathons;
      try {
        hackathons = await client.myHackathons();
      } catch (err) {
        vscode.window.showErrorMessage(`VERIQO: ${(err as Error).message}`);
        return;
      }
      const usable = hackathons.filter((h) => h.phase !== "ended");
      if (!usable.length) {
        vscode.window.showWarningMessage("VERIQO: you are not shortlisted for any upcoming or live hackathon.");
        return;
      }
      const pick = await vscode.window.showQuickPick(
        usable.map((h) => ({ label: h.event_name, description: h.phase === "live" ? "live now" : "upcoming", h })),
        { placeHolder: "Which hackathon are you working on?" },
      );
      if (!pick) return;
      const folders = vscode.workspace.workspaceFolders || [];
      if (!folders.length) {
        vscode.window.showWarningMessage("VERIQO: open your project folder first. Only files inside it are tracked.");
        return;
      }
      const folder =
        folders.length === 1
          ? folders[0]
          : (await vscode.window.showQuickPick(folders.map((f) => ({ label: f.name, f })), { placeHolder: "Which folder is your hackathon project?" }))?.f;
      if (!folder) return;
      const state = { hackathonId: pick.h.id, hackathonName: pick.h.event_name, folder: folder.uri.fsPath };
      await context.workspaceState.update(STATE_KEY, state);
      start(state);
      vscode.window.showInformationMessage(`VERIQO: tracking ${pick.h.event_name} in ${folder.name}. Only activity counts are recorded, never your code.`);
    }),

    vscode.commands.registerCommand("veriqo.stopTracking", async () => {
      await stop();
      vscode.window.showInformationMessage("VERIQO: tracking stopped.");
    }),

    vscode.commands.registerCommand("veriqo.showStatus", async () => {
      if (!trackingState) {
        const c = await vscode.window.showInformationMessage("VERIQO telemetry is off.", "Start tracking");
        if (c) vscode.commands.executeCommand("veriqo.startTracking");
        return;
      }
      await flush();
      try {
        const s = await client.summary(trackingState.hackathonId);
        const mins = Math.round(Number(s.active_seconds) / 60);
        const choice = await vscode.window.showInformationMessage(
          `VERIQO · ${trackingState.hackathonName}: ${mins} active min, ${s.typed_chars} typed, ${s.pasted_chars} pasted, ${s.bulk_insert_chars} bulk-inserted. Flag: ${s.flag}.`,
          "Stop tracking",
        );
        if (choice) vscode.commands.executeCommand("veriqo.stopTracking");
      } catch (err) {
        vscode.window.showErrorMessage(`VERIQO: ${(err as Error).message}`);
      }
    }),

    // Bound to Ctrl/Cmd+V while tracking: note the clipboard size, then run the normal paste.
    vscode.commands.registerCommand("veriqo.paste", async () => {
      const editor = vscode.window.activeTextEditor;
      if (tracker && editor && inScope(editor.document)) {
        tracker.markPaste((await vscode.env.clipboard.readText()).length);
      }
      await vscode.commands.executeCommand("editor.action.clipboardPasteAction");
    }),

    vscode.workspace.onDidChangeTextDocument((e) => {
      if (!tracker || !inScope(e.document) || !e.contentChanges.length) return;
      if (e.reason === vscode.TextDocumentChangeReason.Undo || e.reason === vscode.TextDocumentChangeReason.Redo) return;
      tracker.recordChanges(
        e.contentChanges.map((c) => ({ inserted: c.text, deletedLength: c.rangeLength })),
        e.document.uri.fsPath,
      );
    }),
    vscode.window.onDidChangeTextEditorSelection((e) => {
      if (tracker && inScope(e.textEditor.document)) tracker.touch();
    }),
    vscode.window.onDidChangeWindowState((s) => {
      if (tracker && !s.focused) tracker.pause();
    }),
  );

  // Resume tracking after a reload if it was on for this workspace.
  const saved = context.workspaceState.get<TrackingState>(STATE_KEY);
  if (saved) start(saved);
  updateStatus();
  void flush();
}

export async function deactivate(): Promise<void> {
  clearInterval(flushTimer);
}
