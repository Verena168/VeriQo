import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Colours come from CSS tokens so light/dark themes swap in one place (see index.css).
const AXIS = { stroke: "var(--axis)", tick: { fill: "var(--muted)", fontSize: 12 }, tickLine: false };
const GRID = { stroke: "var(--grid)", strokeDasharray: "", vertical: false };

function TooltipBox({ active, payload, label, labelFormatter, valueFormatter = (v) => v?.toLocaleString() }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-ink">{labelFormatter ? labelFormatter(label) : label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-ink-2">
          <span className="size-2 rounded-full" style={{ background: p.color }} aria-hidden />
          <span>{p.name}</span>
          <span className="tabular ml-auto pl-3 font-medium text-ink">{valueFormatter(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

/** Single-series vertical bars (no legend: the card title names the series). */
export function SimpleBars({ data, x, y, name, height = 220, valueFormatter, xFormatter }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={x} {...AXIS} tickFormatter={xFormatter} />
        <YAxis {...AXIS} axisLine={false} allowDecimals={false} />
        <Tooltip cursor={{ fill: "var(--surface-2)" }} content={<TooltipBox valueFormatter={valueFormatter} labelFormatter={xFormatter} />} />
        <Bar dataKey={y} name={name} fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={36} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars for ranked categories (languages, skills). */
export function RankedBars({ data, label, value, name, valueFormatter }) {
  const height = Math.max(120, data.length * 34 + 16);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey={label} {...AXIS} axisLine={false} width={110} />
        <Tooltip cursor={{ fill: "var(--surface-2)" }} content={<TooltipBox valueFormatter={valueFormatter} />} />
        <Bar dataKey={value} name={name} fill="var(--series-1)" radius={[0, 4, 4, 0]} maxBarSize={18} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Typed vs pasted vs AI-inserted characters over time: 3 series, legend + crosshair tooltip. */
export function TypingTimeline({ data, height = 260 }) {
  const fmt = (t) => new Date(t).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const series = [
    { key: "typed", name: "Typed", color: "var(--series-1)" },
    { key: "pasted", name: "Pasted", color: "var(--series-2)" },
    { key: "bulk", name: "Bulk inserted (likely AI)", color: "var(--series-3)" },
  ];
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="t" {...AXIS} tickFormatter={(t) => new Date(t).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })} minTickGap={40} />
        <YAxis {...AXIS} axisLine={false} />
        <Tooltip cursor={{ stroke: "var(--axis)" }} content={<TooltipBox labelFormatter={fmt} valueFormatter={(v) => `${v.toLocaleString()} chars`} />} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "var(--ink-2)" }} />
        {series.map((s) => (
          <Line key={s.key} dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Single-series line over months. */
export function SimpleLine({ data, x, y, name, height = 220, valueFormatter }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={x} {...AXIS} />
        <YAxis {...AXIS} axisLine={false} />
        <Tooltip cursor={{ stroke: "var(--axis)" }} content={<TooltipBox valueFormatter={valueFormatter} />} />
        <Line dataKey={y} name={name} stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)", fill: "var(--series-1)" }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** GitHub-style contribution grid: one cell per day, sequential blue ramp by active minutes. */
export function ActivityHeatmap({ year, daily }) {
  const [hover, setHover] = useState(null);
  const { weeks, max } = useMemo(() => {
    const byDate = Object.fromEntries(daily.map((d) => [d.date, d.active_minutes]));
    const start = new Date(Date.UTC(year, 0, 1));
    const days = [];
    for (let d = new Date(start); d.getUTCFullYear() === year; d.setUTCDate(d.getUTCDate() + 1)) {
      const key = d.toISOString().slice(0, 10);
      days.push({ key, dow: d.getUTCDay(), minutes: byDate[key] || 0 });
    }
    const weeks = [];
    let week = new Array(days[0].dow).fill(null);
    for (const day of days) {
      week.push(day);
      if (week.length === 7) {
        weeks.push(week);
        week = [];
      }
    }
    if (week.length) weeks.push(week);
    return { weeks, max: Math.max(1, ...days.map((d) => d.minutes)) };
  }, [year, daily]);

  const level = (m) => (m === 0 ? 0 : Math.min(5, Math.ceil((m / max) * 5)));
  const cell = 11;
  const gap = 3;
  return (
    <div className="relative">
      <div className="overflow-x-auto">
        <svg width={weeks.length * (cell + gap)} height={7 * (cell + gap)} role="img" aria-label={`Daily coding activity in ${year}`}>
          {weeks.map((w, wi) =>
            w.map(
              (d, di) =>
                d && (
                  <rect
                    key={d.key}
                    x={wi * (cell + gap)}
                    y={di * (cell + gap)}
                    width={cell}
                    height={cell}
                    rx={2}
                    fill={`var(--seq-${level(d.minutes)})`}
                    onMouseEnter={() => setHover({ ...d, x: wi * (cell + gap), y: di * (cell + gap) })}
                    onMouseLeave={() => setHover(null)}
                  >
                    <title>{`${d.key}: ${d.minutes} active minutes`}</title>
                  </rect>
                ),
            ),
          )}
        </svg>
      </div>
      {hover && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-lg"
          style={{ left: hover.x + cell / 2, top: hover.y - 6 }}
        >
          <div className="font-medium">{new Date(hover.key).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</div>
          <div className="tabular text-ink-2">{hover.minutes} active minutes</div>
        </div>
      )}
      <div className="mt-2 flex items-center justify-end gap-1.5 text-xs text-muted">
        Less
        {[0, 1, 2, 3, 4, 5].map((l) => (
          <span key={l} className="size-2.5 rounded-sm" style={{ background: `var(--seq-${l})` }} aria-hidden />
        ))}
        More
      </div>
    </div>
  );
}
