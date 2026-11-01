import { ChevronDown, ChevronRight, FileText, Presentation, Send } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { ApplicationBadge, Button, Card, Chip, Empty, ErrorBanner, Meter, Select, Spinner, Table, Td, Th } from "../../components/ui";
import { api, openFile } from "../../lib/api";
import { fmtDateTime } from "../../lib/format";
import { useApi } from "../../lib/useApi";
import { MatchBreakdown } from "../HackathonDetail";

/** Decisions stay private until published; this bar shows what's pending and publishes it. */
function PublishBar({ hackathon, applications, onPublished }) {
  const [confirming, setConfirming] = useState(false);
  const [notify, setNotify] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const unpublished = applications.filter((a) => ["shortlisted", "rejected"].includes(a.status) && !a.decision_published_at);
  const undecided = applications.filter((a) => ["pending", "needs_review"].includes(a.status));
  const count = (s) => unpublished.filter((a) => a.status === s).length;

  const publish = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api(`/hackathons/${hackathon.id}/results/publish`, { method: "POST", body: { notify, allow_undecided: true } });
      setResult(res);
      setConfirming(false);
      onPublished();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-b border-line bg-surface-2/40 px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm">
          {unpublished.length ? (
            <span>
              <b>{unpublished.length}</b> decision{unpublished.length === 1 ? "" : "s"} not yet visible to applicants ({count("shortlisted")} shortlisted,{" "}
              {count("rejected")} not shortlisted).
            </span>
          ) : (
            <span className="text-ink-2">All decisions are published.</span>
          )}
          {undecided.length > 0 && <span className="text-warn"> {undecided.length} still need a decision and will stay “under review”.</span>}
          <div className="mt-0.5 text-xs text-muted">
            {hackathon.results_published_at ? `Last published ${fmtDateTime(hackathon.results_published_at)}. ` : "Results have not been published yet. "}
            Applicants never see AI scores{hackathon.is_score_published ? ", except as feedback after publishing (enabled in Settings)" : ""}.
          </div>
        </div>
        {!confirming && (
          <Button onClick={() => { setConfirming(true); setResult(null); }} disabled={!unpublished.length}>
            <Send className="size-4" aria-hidden /> Publish results
          </Button>
        )}
      </div>
      {confirming && (
        <div className="mt-3 flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-3 text-sm">
          <span>
            Publish {unpublished.length} result{unpublished.length === 1 ? "" : "s"}? Applicants will see their outcome on their dashboard.
          </span>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} /> Email applicants
          </label>
          <div className="ml-auto flex gap-2">
            <Button variant="ghost" onClick={() => setConfirming(false)}>Cancel</Button>
            <Button onClick={publish} busy={busy}>Confirm &amp; publish</Button>
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-bad">{error}</p>}
      {result && (
        <p className="mt-2 text-sm text-good">
          Published {result.published} result{result.published === 1 ? "" : "s"}
          {result.emails_queued ? `; ${result.emails_queued} email${result.emails_queued === 1 ? "" : "s"} queued` : ""}.
        </p>
      )}
    </div>
  );
}

export default function Applicants({ hackathon, canEdit }) {
  const { data, error, loading, reload } = useApi(`/hackathons/${hackathon.id}/applications`);
  const [open, setOpen] = useState(null);
  const [filter, setFilter] = useState("all");
  const [actionError, setActionError] = useState(null);
  const rows = useMemo(() => (data || []).filter((a) => filter === "all" || a.status === filter), [data, filter]);

  const setStatus = async (app, status) => {
    setActionError(null);
    try {
      await api(`/applications/${app.id}`, { method: "PATCH", body: { status } });
      reload();
    } catch (e) {
      setActionError(e.message);
    }
  };

  if (loading) return <Spinner />;
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="font-semibold">Registered teams</h2>
          <p className="text-sm text-ink-2">Ranked by the AI team score (all members' skills pooled). The status is the AI's suggestion until you change it; teams see nothing until you publish.</p>
        </div>
        <div className="w-48">
          <Select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by status">
            <option value="all">All ({data.length})</option>
            <option value="shortlisted">Shortlisted</option>
            <option value="needs_review">Needs review</option>
            <option value="rejected">Not shortlisted</option>
          </Select>
        </div>
      </div>
      {canEdit && data.length > 0 && <PublishBar hackathon={hackathon} applications={data} onPublished={reload} />}
      <div className="px-5 pt-4">
        <ErrorBanner>{error || actionError}</ErrorBanner>
      </div>
      {!rows.length ? (
        <Empty title="No teams here yet">Teams appear once their lead submits the registration.</Empty>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th className="w-8" />
              <Th>Team</Th>
              <Th>Team score</Th>
              <Th>Status</Th>
              <Th>Combined skills</Th>
              {canEdit && <Th className="text-right">Decision</Th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const isOpen = open === a.id;
              const pooled = [...new Set(a.members.flatMap((m) => m.skills))];
              return (
                <Fragment key={a.id}>
                  <tr className="hover:bg-surface-2/50">
                    <Td>
                      <button onClick={() => setOpen(isOpen ? null : a.id)} aria-label="Show members and score breakdown" className="text-ink-2">
                        {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                      </button>
                    </Td>
                    <Td>
                      <div className="font-medium">
                        {a.team_name} {a.formed_by === "ai" && <Chip tone="accent">AI-formed</Chip>}
                      </div>
                      <div className="text-xs text-muted">
                        {a.members.map((m) => m.user.name + (m.is_lead ? " (lead)" : "")).join(", ")}
                        {a.seeking_teammates && " · looking for teammates"}
                      </div>
                    </Td>
                    <Td>
                      <Meter value={a.score} />
                    </Td>
                    <Td>
                      <ApplicationBadge status={a.status} />
                      {!a.decision_published_at && ["shortlisted", "rejected"].includes(a.status) && (
                        <div className="mt-1 text-xs text-muted" title="Teams still see 'under review' until you publish results">
                          Not published yet
                        </div>
                      )}
                    </Td>
                    <Td>
                      <div className="flex max-w-sm flex-wrap gap-1">
                        {pooled.slice(0, 6).map((s) => (
                          <Chip key={s}>{s}</Chip>
                        ))}
                        {pooled.length > 6 && <Chip>+{pooled.length - 6}</Chip>}
                      </div>
                    </Td>
                    {canEdit && (
                      <Td className="whitespace-nowrap text-right">
                        {a.status !== "shortlisted" && (
                          <Button size="sm" variant="secondary" onClick={() => setStatus(a, "shortlisted")}>
                            Shortlist
                          </Button>
                        )}
                        {a.status !== "rejected" && (
                          <Button size="sm" variant="ghost" onClick={() => setStatus(a, "rejected")}>
                            Reject
                          </Button>
                        )}
                      </Td>
                    )}
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={canEdit ? 6 : 5} className="space-y-4 border-b border-line bg-surface-2/40 px-5 py-4">
                        <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
                          <span>Registered {fmtDateTime(a.applied_at)}</span>
                          {a.pitch_deck_file_id && (
                            <Button size="sm" variant="secondary" onClick={() => openFile(`/applications/${a.id}/pitch-deck`).catch((e) => setActionError(e.message))}>
                              <Presentation className="size-3.5" aria-hidden /> View pitch deck
                            </Button>
                          )}
                        </div>
                        {a.review_note && <p className="text-sm text-warn">{a.review_note}</p>}
                        <div className="grid gap-3 md:grid-cols-2">
                          {a.members.map((m) => (
                            <div key={m.user.id} className="rounded-lg border border-line bg-surface p-3 text-sm">
                              <div className="flex items-start justify-between gap-2">
                                <div>
                                  <div className="font-medium">
                                    {m.user.name} {m.is_lead && <span className="text-xs text-muted">· lead</span>}
                                  </div>
                                  <div className="text-xs text-muted">
                                    {m.user.email}
                                    {m.experience_level && ` · ${m.experience_level}`}
                                  </div>
                                  {m.artifact?.github_url && (
                                    <a className="text-xs text-accent hover:underline" href={m.artifact.github_url} target="_blank" rel="noreferrer">
                                      {m.artifact.github_url.replace("https://github.com/", "@")}
                                    </a>
                                  )}
                                </div>
                                {m.artifact?.has_cv && (
                                  <Button size="sm" variant="secondary" onClick={() => openFile(`/teams/${a.team_id}/members/${m.user.id}/cv`).catch((e) => setActionError(e.message))}>
                                    <FileText className="size-3.5" aria-hidden /> CV
                                  </Button>
                                )}
                              </div>
                              {m.artifact?.parse_status === "unreadable" && <p className="mt-1 text-xs text-warn">CV text couldn't be read; review it manually.</p>}
                              <div className="mt-2 flex flex-wrap gap-1">
                                {m.skills.slice(0, 10).map((s) => (
                                  <Chip key={s}>{s}</Chip>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                        <div>
                          <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">How the team matched the requirements</h4>
                          <MatchBreakdown breakdown={a.match_details} />
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
