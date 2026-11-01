import { Code2 } from "lucide-react";
import ThemeToggle from "../components/ThemeToggle";

export default function AuthShell({ title, subtitle, children }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-accent p-12 text-white lg:flex">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <Code2 className="size-6" aria-hidden /> VERIQO
        </div>
        <div>
          <h2 className="text-3xl font-semibold leading-tight">Fair hackathons, verified code.</h2>
          <p className="mt-4 max-w-md text-white/80">
            AI shortlisting and team formation, live IDE telemetry, and AST-based code integrity reports, in one
            platform for organizers, judges and developers.
          </p>
        </div>
        <p className="text-sm text-white/60">St. Francis Institute of Technology · Major Project 2026–27</p>
      </div>
      <div className="relative flex items-center justify-center px-4 py-12">
        <ThemeToggle className="absolute right-4 top-4" />
        <div className="w-full max-w-sm">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mb-6 mt-1 text-ink-2">{subtitle}</p>
          {children}
        </div>
      </div>
    </div>
  );
}
