import { ArrowDown, ArrowUp, ExternalLink, RefreshCw, ScanSearch } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Button, Card, Empty, ErrorBanner, Notice, RiskBadge, Spinner, Table, Td, TelemetryFlag, Th } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtPct, fmtRatio, shortSha } from "../../lib/format";
import { useApi } from "../../lib/useApi";

const RISK_ORDER = { red: 0, amber: 1, green: 2 };
const COLUMNS = [
  { id: "team", label: "Team / project", get: (r) => (r.team_name || r.members[0]?.name || "").toLowerCase() },
  { id: "risk", label: "Risk", get: (r) => (r.report?.risk_level ? RISK_ORDER[r.report.risk_level] : 9) },
  { id: "plag", label: "Matched code", get: (r) => r.report?.plagiarism_score ?? -1, num: true },
  { id: "pre", label: "Pre-event code", get: (r) => r.report?.pre_event_share ?? -1, num: true },
  { id: "paste", label: "Paste ratio", get: (r) => r.report?.paste_ratio ?? -1, num: true },
  { id: "active", label: "Active time", get: (r) => r.report?.active_minutes ?? -1, num: true },
  { id: "flag", label: "Telemetry", get: (r) => r.report?.telemetry_flag || "" },
];

export default function Evaluation({ hackathon, canScan }) {
  const [poll, setPoll] = useState(null);
  const { data, error, loading, reload } = useApi(`/hackathons/${hackathon.id}/reports`, { poll });
  const [sort, setSort] = useState({ id: "risk", dir: 1 });
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const scanning = (data || []).some((r) => r.submission.status === "scanning");
  useEffect(() => setPoll(scanning ? 4000 : null), [scanning]);

  const rows = useMemo(() => {
    const col = COLUMNS.find((c) => c.id === sort.id);
    return [...(data || [])].sort((a, b) => {
      const x = col.get(a);
      const y = col.get(b);
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
    });
  }, [data, sort]);

  const scan = async (path) => {
    setBusy(true);
    setActionError(null);
    try {
      await api(path, { method: "POST" });
      await reload();
      setPoll(4000);
    } catch (e) {
      setActionError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Spinner />;
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="font-semibold">Originality reports</h2>
          <p className="text-sm text-ink-2">
            AST/token similarity, code that existed before the event, and live IDE telemetry, per submission. Bands are for triage; open a report to see the evidence.
          </p>
        </div>
        {canScan && (
          <Button onClick={() => scan(`/hackathons/${hackathon.id}/scan`)} busy={busy || scanning} disabled={!data.length}>
            <ScanSearch className="size-4" aria-hidden /> {scanning ? "Scanning…" : "Scan all submissions"}
          </Button>
        )}
      </div>
      <div className="px-5 pt-4">
        <ErrorBanner>{error || actionError}</ErrorBanner>
        {hackathon.phase === "live" && data.length > 0 && (
          <div className="mb-4">
            <Notice>The hackathon is still live: scans use the latest commit before the deadline, so re-scan after it ends for final results.</Notice>
          </div>
        )}
      </div>
      {!data.length ? (
        <Empty title="No submissions yet">Teams submit a GitHub repository while the hackathon is live.</Empty>
      ) : (
        <Table>
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <Th key={c.id} className={c.num ? "text-right" : ""} aria-sort={sort.id === c.id ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                  <button
                    className="inline-flex items-center gap-1 uppercase hover:text-ink"
                    onClick={() => setSort({ id: c.id, dir: sort.id === c.id ? -sort.dir : c.num ? -1 : 1 })}
                  >
                    {c.label}
                    {sort.id === c.id && (sort.dir === 1 ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
                  </button>
                </Th>
              ))}
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ submission: s, team_name, members, report: r }) => (
              <tr key={s.id} className="hover:bg-surface-2/50">
                <Td>
                  <div className="font-medium">{team_name || members[0]?.name}</div>
                  <div className="text-ink-2">{s.project_title}</div>
                  <a href={s.repository_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                    {s.repository_url.replace("https://github.com/", "")} @ {shortSha(s.commit_sha)}
                    <ExternalLink className="size-3" aria-hidden />
                  </a>
                </Td>
                <Td className="whitespace-nowrap">
                  {s.status === "scanning" ? (
                    <span className="inline-flex items-center gap-1.5 text-sm text-ink-2">
                      <RefreshCw className="size-4 animate-spin" aria-hidden /> Scanning
                    </span>
                  ) : r?.status === "failed" ? (
                    <span className="text-sm text-bad">Scan failed</span>
                  ) : (
                    <RiskBadge level={r?.risk_level} />
                  )}
                </Td>
                <Td className="tabular text-right">{fmtPct(r?.plagiarism_score)}</Td>
                <Td className="tabular text-right">{fmtPct(r?.pre_event_share)}</Td>
                <Td className="tabular text-right">{fmtRatio(r?.paste_ratio)}</Td>
                <Td className="tabular whitespace-nowrap text-right">{r?.active_minutes != null ? `${(r.active_minutes / 60).toFixed(1)} h` : "—"}</Td>
                <Td>
                  <TelemetryFlag flag={r?.telemetry_flag} />
                </Td>
                <Td className="whitespace-nowrap text-right">
                  {r && (
                    <Link to={`/reports/${r.id}`}>
                      <Button size="sm" variant="secondary">
                        {r.status === "reviewed" ? "Reviewed ✓" : "Open report"}
                      </Button>
                    </Link>
                  )}
                  {canScan && s.status !== "scanning" && (
                    <Button size="sm" variant="ghost" onClick={() => scan(`/submissions/${s.id}/scan`)} aria-label="Re-scan this submission" title="Re-scan">
                      <RefreshCw className="size-4" />
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
