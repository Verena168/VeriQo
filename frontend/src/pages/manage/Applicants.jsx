import { ChevronDown, ChevronRight, FileText, Presentation } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { ApplicationBadge, Button, Card, Chip, Empty, ErrorBanner, Meter, Select, Spinner, Table, Td, Th } from "../../components/ui";
import { api, openFile } from "../../lib/api";
import { fmtDateTime } from "../../lib/format";
import { useApi } from "../../lib/useApi";
import { MatchBreakdown } from "../HackathonDetail";

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
          <h2 className="font-semibold">Applicants</h2>
          <p className="text-sm text-ink-2">Ranked by AI match score against your required skills.</p>
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
      <div className="px-5 pt-4">
        <ErrorBanner>{error || actionError}</ErrorBanner>
      </div>
      {!rows.length ? (
        <Empty title="No applicants here">Participants apply from the hackathon page by uploading a resume.</Empty>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th className="w-8" />
              <Th>Applicant</Th>
              <Th>Score</Th>
              <Th>Status</Th>
              <Th>Top skills</Th>
              <Th>Experience</Th>
              {canEdit && <Th className="text-right">Decision</Th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const p = a.user.parsed_skills || {};
              const isOpen = open === a.id;
              return (
                <Fragment key={a.id}>
                  <tr className="hover:bg-surface-2/50">
                    <Td>
                      <button onClick={() => setOpen(isOpen ? null : a.id)} aria-label="Show score breakdown" className="text-ink-2">
                        {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                      </button>
                    </Td>
                    <Td>
                      <div className="font-medium">{a.user.name}</div>
                      <div className="text-xs text-muted">{a.user.email}</div>
                      {a.user.github_url && (
                        <a className="text-xs text-accent hover:underline" href={a.user.github_url} target="_blank" rel="noreferrer">
                          {a.user.github_url.replace("https://github.com/", "@")}
                        </a>
                      )}
                    </Td>
                    <Td>
                      <Meter value={a.score} />
                    </Td>
                    <Td>
                      <ApplicationBadge status={a.status} />
                    </Td>
                    <Td>
                      <div className="flex max-w-xs flex-wrap gap-1">
                        {(p.skills || []).slice(0, 5).map((s) => (
                          <Chip key={s.name} title={`${s.mentions} mention(s) · ${s.sources.join(", ")}`}>
                            {s.name}
                          </Chip>
                        ))}
                      </div>
                    </Td>
                    <Td className="whitespace-nowrap text-ink-2">
                      {p.experience_level || "—"}
                      {p.experience_years ? ` · ${p.experience_years} yrs` : ""}
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
                      <td colSpan={canEdit ? 7 : 6} className="border-b border-line bg-surface-2/40 px-5 py-4">
                        <div className="mb-2 flex flex-wrap items-center gap-3 text-xs text-muted">
                          <span>
                            Applied {fmtDateTime(a.applied_at)} · {a.resume_filename}
                            {p.github && ` · GitHub: ${p.github.public_repos} repos, ${p.github.recently_active_repos} active in 6 months`}
                          </span>
                          {a.cv_file_id && (
                            <Button size="sm" variant="secondary" onClick={() => openFile(`/applications/${a.id}/cv`).catch((e) => setActionError(e.message))}>
                              <FileText className="size-3.5" aria-hidden /> View CV
                            </Button>
                          )}
                          {a.pitch_deck_file_id && (
                            <Button size="sm" variant="secondary" onClick={() => openFile(`/applications/${a.id}/pitch-deck`).catch((e) => setActionError(e.message))}>
                              <Presentation className="size-3.5" aria-hidden /> View pitch deck
                            </Button>
                          )}
                        </div>
                        {a.review_note && <p className="mb-2 text-sm text-warn">{a.review_note}</p>}
                        <MatchBreakdown breakdown={a.match_details} />
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
