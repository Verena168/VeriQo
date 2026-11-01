export const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—";

export const fmtDateTime = (iso) =>
  iso
    ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : "—";

export const fmtPct = (v, digits = 0) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(digits)}%`);

export const fmtRatio = (v) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

export const fmtNum = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString());

/** datetime-local input value <-> ISO string with the browser's timezone */
export const toLocalInput = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
export const fromLocalInput = (v) => (v ? new Date(v).toISOString() : null);

export const shortSha = (sha) => (sha ? sha.slice(0, 7) : "—");
