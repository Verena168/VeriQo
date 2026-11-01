import { AlertTriangle, CheckCircle2, CircleHelp, Loader2, ShieldAlert, XCircle } from "lucide-react";

export function Button({ variant = "primary", size = "md", className = "", busy, children, ...props }) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
  const sizes = { sm: "px-2.5 py-1.5 text-xs", md: "px-3.5 py-2 text-sm" };
  const variants = {
    primary: "bg-accent text-white hover:brightness-110",
    secondary: "bg-surface text-ink border border-line hover:bg-surface-2",
    ghost: "text-ink-2 hover:bg-surface-2",
    danger: "bg-surface text-bad border border-line hover:bg-surface-2",
  };
  return (
    <button className={`${base} ${sizes[size]} ${variants[variant]} ${className}`} disabled={busy || props.disabled} {...props}>
      {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Card({ className = "", children, ...props }) {
  return (
    <div className={`rounded-xl border border-line bg-surface ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, action, eyebrow }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-ink-2">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Field({ label, hint, children, error }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-bad">{error}</span>}
    </label>
  );
}

const inputCls =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25";

export const Input = (props) => <input className={inputCls} {...props} />;
export const Textarea = (props) => <textarea className={inputCls} {...props} />;
export const Select = ({ children, ...props }) => (
  <select className={inputCls} {...props}>
    {children}
  </select>
);

export function Spinner({ label = "Loading" }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-ink-2" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}…
    </div>
  );
}

export function ErrorBanner({ children }) {
  if (!children) return null;
  return (
    <div role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-line bg-surface px-4 py-3 text-sm text-bad">
      <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{children}</span>
    </div>
  );
}

export function Notice({ children, icon: Icon = CircleHelp }) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-surface-2 px-4 py-3 text-sm text-ink-2">
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function Empty({ title, children, action }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <div className="font-medium">{title}</div>
      {children && <p className="mt-1 max-w-md text-sm text-ink-2">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Chip({ children, tone = "neutral", title }) {
  const tones = {
    neutral: "bg-surface-2 text-ink-2",
    accent: "bg-accent-soft text-accent",
  };
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

/** Status indicator: colour + icon + label, never colour alone. */
const STATUS = {
  good: { icon: CheckCircle2, color: "var(--good)", ink: "text-good" },
  warning: { icon: AlertTriangle, color: "var(--warning)", ink: "text-warn" },
  critical: { icon: ShieldAlert, color: "var(--critical)", ink: "text-bad" },
  neutral: { icon: CircleHelp, color: "var(--muted)", ink: "text-ink-2" },
};

export function StatusBadge({ status = "neutral", children }) {
  const s = STATUS[status];
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${s.ink}`}>
      <Icon className="size-4" style={{ color: s.color }} aria-hidden />
      {children}
    </span>
  );
}

const RISK = { green: ["good", "Clear"], amber: ["warning", "Review"], red: ["critical", "High risk"] };
export function RiskBadge({ level }) {
  if (!level) return <span className="text-sm text-muted">Not scanned</span>;
  const [status, label] = RISK[level];
  return <StatusBadge status={status}>{label}</StatusBadge>;
}

const APP_STATUS = {
  shortlisted: ["good", "Shortlisted"],
  rejected: ["critical", "Not shortlisted"],
  needs_review: ["warning", "Needs review"],
  pending: ["neutral", "Pending"],
  under_review: ["neutral", "Under review"],
};
export function ApplicationBadge({ status }) {
  const [s, label] = APP_STATUS[status] || ["neutral", status];
  return <StatusBadge status={s}>{label}</StatusBadge>;
}

const FLAG = { low: ["good", "Low"], medium: ["warning", "Medium"], high: ["critical", "High"], no_data: ["neutral", "No data"] };
export function TelemetryFlag({ flag }) {
  if (!flag) return <span className="text-sm text-muted">—</span>;
  const [s, label] = FLAG[flag] || ["neutral", flag];
  return <StatusBadge status={s}>{label}</StatusBadge>;
}

export function Stat({ label, value, sub }) {
  return (
    <Card className="px-5 py-4">
      <div className="text-sm text-ink-2">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </Card>
  );
}

/** Thin horizontal meter for a 0-100 score. */
export function Meter({ value, max = 100 }) {
  const pct = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular text-sm">{value === null || value === undefined ? "—" : Math.round(value)}</span>
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="mb-6 flex gap-1 overflow-x-auto border-b border-line" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={active === t.id}
          onClick={() => onChange(t.id)}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition ${
            active === t.id ? "border-accent text-ink" : "border-transparent text-ink-2 hover:text-ink"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Table({ children }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">{children}</table>
    </div>
  );
}
export const Th = ({ children, className = "", ...p }) => (
  <th className={`border-b border-line px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-muted ${className}`} {...p}>
    {children}
  </th>
);
export const Td = ({ children, className = "", ...p }) => (
  <td className={`border-b border-line px-4 py-3 align-top ${className}`} {...p}>
    {children}
  </td>
);
