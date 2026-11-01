import { ArrowLeft, ExternalLink, GitCommit } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { TypingTimeline } from "../components/charts";
import {
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorBanner,
  Field,
  Notice,
  PageHeader,
  RiskBadge,
  Spinner,
  Stat,
  Table,
  Td,
  TelemetryFlag,
  Textarea,
  Th,
} from "../components/ui";
import { api } from "../lib/api";
import { fmtDateTime, fmtNum, fmtPct, fmtRatio, shortSha } from "../lib/format";
import { useApi } from "../lib/useApi";

const ranges = (rs) => (rs || []).map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`)).join(", ");

function blobUrl(repoUrl, sha, path, lines) {
  if (!repoUrl || !sha) return null;
  const anchor = lines?.length ? `#L${lines[0][0]}-L${lines[0][1]}` : "";
  return `${repoUrl}/blob/${sha}/${path}${anchor}`;
}

function MemberTimeline({ reportId, member }) {
  const { data, loading, error } = useApi(`/reports/${reportId}/telemetry/${member.user_id}`);
  if (loading) return <Spinner label="Loading telemetry" />;
  if (error) return <ErrorBanner>{error}</ErrorBanner>;
  if (!data.buckets.length) return <Empty title="No telemetry recorded">This member did not use the VERIQO extension during the event.</Empty>;
  const big = data.paste_events.filter((e) => e.chars >= 200).slice(-12).reverse();
  return (
    <div className="space-y-4">
      <TypingTimeline data={data.buckets} />
      {big.length > 0 && (
        <div>
          <h4 className="mb-2 text-sm font-medium">Largest recent insertions</h4>
          <Table>
            <thead>
              <tr>
                <Th>Time</Th>
                <Th>Source</Th>
                <Th>File type</Th>
                <Th className="text-right">Characters</Th>
                <Th className="text-right">Lines</Th>
              </tr>
            </thead>
            <tbody>
              {big.map((e, i) => (
                <tr key={i}>
                  <Td className="tabular">{fmtDateTime(e.ts)}</Td>
                  <Td>{e.source === "clipboard" ? "Clipboard paste" : "Bulk insert (likely AI completion)"}</Td>
                  <Td>{e.file_ext || "—"}</Td>
                  <Td className="tabular text-right">{fmtNum(e.chars)}</Td>
                  <Td className="tabular text-right">{fmtNum(e.lines)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </div>
  );
}

export default function ReportPage() {
  const { id } = useParams();
  const { data, error, loading, setData } = useApi(`/reports/${id}`);
  const [member, setMember] = useState(null);
  const [notes, setNotes] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  if (loading) return <Spinner />;
  if (error) return <ErrorBanner>{error}</ErrorBanner>;

  const { report: r, submission: s, team_name, members } = data;
  const d = r.details || {};
  const activeMember = member || d.members?.[0];

  const save = async (status) => {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await api(`/reports/${id}`, { method: "PATCH", body: { judge_notes: notes ?? r.judge_notes ?? "", ...(status ? { status } : {}) } });
      setData({ ...data, report: updated });
      setNotes(null);
    } catch (e) {
      setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Link to={`/manage/${s.hackathon_id}`} className="mb-4 inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Back to evaluation
      </Link>
      <PageHeader
        eyebrow={team_name || members.map((m) => m.name).join(", ")}
        title={s.project_title}
        subtitle={
          <a href={s.repository_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
            {s.repository_url.replace("https://github.com/", "")} @ {shortSha(s.commit_sha)} <ExternalLink className="size-3.5" aria-hidden />
          </a>
        }
        action={<RiskBadge level={r.risk_level} />}
      />

      {r.status === "failed" ? (
        <ErrorBanner>Scan failed: {d.error}</ErrorBanner>
      ) : (
        <div className="space-y-6">
          <Card className="p-5">
            <h2 className="mb-2 font-semibold">Why this band</h2>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {(d.risk_reasons || []).map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted">
              Generated {fmtDateTime(r.generated_at)}. Evidence for human review, not an automatic verdict. AI-generated-code probability is not reported: published
              detectors perform near chance on source code, so IDE telemetry is used instead.
            </p>
          </Card>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <Stat label="Matched code" value={fmtPct(r.plagiarism_score, 1)} sub={`${d.files_flagged ?? 0} of ${d.files_compared ?? 0} files flagged`} />
            <Stat label="Pre-event code" value={fmtPct(r.pre_event_share, 1)} sub={`${d.commits?.before_start ?? 0} commits before start`} />
            <Stat label="Allowed template" value={fmtPct(r.template_share, 1)} sub="excluded from matching" />
            <Stat label="Team paste ratio" value={fmtRatio(r.paste_ratio)} sub={<TelemetryFlag flag={r.telemetry_flag} />} />
            <Stat label="Active coding" value={`${((r.active_minutes || 0) / 60).toFixed(1)} h`} sub={`telemetry from ${fmtRatio(r.telemetry_coverage)} of members`} />
          </div>

          {d.top_sources?.length > 0 && (
            <Card>
              <CardHeader title="Matched sources" subtitle="Share of this submission's code matching each source" />
              <ul className="divide-y divide-line">
                {d.top_sources.map((src) => (
                  <li key={src.source_id} className="flex items-center justify-between px-5 py-3 text-sm">
                    <span>
                      <span className="font-medium">{src.label}</span> <span className="text-muted">· {src.kind}</span>
                    </span>
                    <span className="tabular font-semibold">{fmtPct(src.share, 1)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card>
            <CardHeader title="File-level matches" subtitle={`Files are flagged when the clone classifier's probability is ≥ ${d.decision_threshold ?? 0.5}.`} />
            {!r.matches?.length ? (
              <Empty title="No overlapping code found" />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>File</Th>
                    <Th>Closest source</Th>
                    <Th className="text-right">Overlap</Th>
                    <Th className="text-right">Structure</Th>
                    <Th className="text-right">Clone prob.</Th>
                    <Th>Lines</Th>
                  </tr>
                </thead>
                <tbody>
                  {r.matches.map((f) => {
                    const m = f.best_match;
                    const href = blobUrl(s.repository_url, s.commit_sha, f.path, m.sub_lines);
                    return (
                      <tr key={f.path} className={f.flagged ? "" : "text-ink-2"}>
                        <Td className="font-mono text-xs">
                          {href ? (
                            <a href={href} target="_blank" rel="noreferrer" className="hover:underline">
                              {f.path}
                            </a>
                          ) : (
                            f.path
                          )}
                          {f.flagged && <div className="mt-1 font-sans text-xs font-medium text-bad">Flagged</div>}
                        </Td>
                        <Td>
                          <div>{m.source_label}</div>
                          <div className="font-mono text-xs text-muted">{m.source_path}</div>
                        </Td>
                        <Td className="tabular text-right">{fmtRatio(m.containment)}</Td>
                        <Td className="tabular text-right">{fmtRatio(m.ast_similarity)}</Td>
                        <Td className="tabular text-right">{m.probability.toFixed(2)}</Td>
                        <Td className="max-w-56 text-xs text-ink-2">
                          ours {ranges(m.sub_lines)}
                          <br />
                          theirs {ranges(m.src_lines)}
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            )}
          </Card>

          <Card>
            <CardHeader title="IDE telemetry by member" subtitle="From the VERIQO VS Code extension during the event window" />
            <Table>
              <thead>
                <tr>
                  <Th>Member</Th>
                  <Th>Flag</Th>
                  <Th className="text-right">Active</Th>
                  <Th className="text-right">Typed</Th>
                  <Th className="text-right">Pasted</Th>
                  <Th className="text-right">Bulk inserted</Th>
                  <Th className="text-right">Paste ratio</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {(d.members || []).map((m) => (
                  <tr key={m.user_id} className={activeMember?.user_id === m.user_id ? "bg-surface-2/60" : ""}>
                    <Td className="font-medium">{m.name}</Td>
                    <Td>
                      <TelemetryFlag flag={m.flag} />
                    </Td>
                    <Td className="tabular text-right">{m.active_minutes} min</Td>
                    <Td className="tabular text-right">{fmtNum(m.typed_chars)}</Td>
                    <Td className="tabular text-right">{fmtNum(m.pasted_chars)}</Td>
                    <Td className="tabular text-right">{fmtNum(m.bulk_insert_chars)}</Td>
                    <Td className="tabular text-right">{fmtRatio(m.paste_ratio)}</Td>
                    <Td className="text-right">
                      <Button size="sm" variant="ghost" onClick={() => setMember(m)}>
                        Timeline
                      </Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            {activeMember && (
              <div className="border-t border-line p-5">
                <h3 className="mb-3 text-sm font-medium">Activity timeline: {activeMember.name} (30-minute buckets)</h3>
                <MemberTimeline key={activeMember.user_id} reportId={id} member={activeMember} />
              </div>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="p-5">
              <h2 className="mb-3 flex items-center gap-2 font-semibold">
                <GitCommit className="size-4" aria-hidden /> Commit history
              </h2>
              <dl className="grid grid-cols-2 gap-y-2 text-sm">
                <dt className="text-ink-2">Commits evaluated</dt>
                <dd className="tabular">{d.commits?.total ?? "—"}</dd>
                <dt className="text-ink-2">Before the event started</dt>
                <dd className="tabular">{d.commits?.before_start ?? "—"}</dd>
                <dt className="text-ink-2">After the deadline (ignored)</dt>
                <dd className="tabular">{d.commits?.after_deadline ?? 0}</dd>
                <dt className="text-ink-2">First commit</dt>
                <dd>{fmtDateTime(d.commits?.first_commit_at)}</dd>
                <dt className="text-ink-2">Last commit</dt>
                <dd>{fmtDateTime(d.commits?.last_commit_at)}</dd>
                <dt className="text-ink-2">Authors</dt>
                <dd>{(d.commits?.authors || []).join(", ") || "—"}</dd>
              </dl>
              <p className="mt-3 text-xs text-muted">Git timestamps are set by the committer and can be forged; treat them as supporting evidence.</p>
            </Card>
            <Card className="p-5">
              <h2 className="mb-3 font-semibold">Judge notes</h2>
              <ErrorBanner>{saveError}</ErrorBanner>
              <Field label="Internal notes" hint="Not visible to participants.">
                <Textarea rows={5} value={notes ?? r.judge_notes ?? ""} onChange={(e) => setNotes(e.target.value)} />
              </Field>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="secondary" busy={saving} onClick={() => save()}>
                  Save notes
                </Button>
                {r.status !== "reviewed" ? (
                  <Button busy={saving} onClick={() => save("reviewed")}>
                    Mark reviewed
                  </Button>
                ) : (
                  <Notice>Reviewed</Notice>
                )}
              </div>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
