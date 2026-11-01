import { EyeOff, ShieldCheck } from "lucide-react";
import { Card, CardHeader, PageHeader } from "../components/ui";

const Step = ({ n, title, children }) => (
  <li className="flex gap-4">
    <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent">{n}</span>
    <div>
      <div className="font-medium">{title}</div>
      <div className="mt-1 text-sm text-ink-2">{children}</div>
    </div>
  </li>
);

const Code = ({ children }) => <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-ink">{children}</code>;

export default function ExtensionSetup() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="VS Code extension" subtitle="Verifies that your hackathon code was written during the event." />
      <Card>
        <CardHeader title="Set up" />
        <ol className="space-y-5 p-5">
          <Step n={1} title="Install the extension">
            Get <Code>veriqo-telemetry-0.1.0.vsix</Code> from your organizer (or build it from <Code>extension/</Code> with <Code>npm run package</Code>), then run{" "}
            <Code>code --install-extension veriqo-telemetry-0.1.0.vsix</Code>.
          </Step>
          <Step n={2} title="Sign in">
            Open the Command Palette (<Code>Ctrl+Shift+P</Code>) and run <Code>VERIQO: Sign in</Code> with your VERIQO email and password.
          </Step>
          <Step n={3} title="Start tracking your hackathon">
            Open your project folder, run <Code>VERIQO: Start tracking</Code> and pick the hackathon. The status bar shows <Code>VERIQO ● tracking</Code> while it records.
          </Step>
          <Step n={4} title="Code as usual">
            Activity syncs every 30 seconds and is queued if you go offline. Run <Code>VERIQO: Stop tracking</Code> when you're done.
          </Step>
        </ol>
      </Card>
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader title="What is recorded" />
          <ul className="space-y-2 p-5 text-sm text-ink-2">
            <li className="flex gap-2">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-good" aria-hidden /> Counts of typed, pasted and deleted characters
            </li>
            <li className="flex gap-2">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-good" aria-hidden /> Size and time of large pastes or bulk insertions (e.g. AI completions)
            </li>
            <li className="flex gap-2">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-good" aria-hidden /> Active coding time and file extensions (like <Code>.py</Code>)
            </li>
          </ul>
        </Card>
        <Card>
          <CardHeader title="What is never recorded" />
          <ul className="space-y-2 p-5 text-sm text-ink-2">
            <li className="flex gap-2">
              <EyeOff className="mt-0.5 size-4 shrink-0" aria-hidden /> The code or text you type or paste
            </li>
            <li className="flex gap-2">
              <EyeOff className="mt-0.5 size-4 shrink-0" aria-hidden /> File names, paths or anything outside the tracked project folder
            </li>
            <li className="flex gap-2">
              <EyeOff className="mt-0.5 size-4 shrink-0" aria-hidden /> Anything when tracking is stopped
            </li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
