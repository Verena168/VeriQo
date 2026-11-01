import { CalendarDays, ExternalLink, FileUp, Plug, Users } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApplicationBadge,
  Button,
  Card,
  CardHeader,
  Chip,
  ErrorBanner,
  Field,
  Input,
  Meter,
  Notice,
  PageHeader,
  RiskBadge,
  Spinner,
  Table,
  Td,
  TelemetryFlag,
  Th,
} from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtDateTime, fmtNum, fmtPct, fmtRatio, shortSha } from "../lib/format";
import { useApi } from "../lib/useApi";
import { PhaseChip } from "./Hackathons";

const MATCHED_BY = { exact: "Exact match", semantic: "Similar skill", category: "Same field", none: "Missing" };

export function MatchBreakdown({ breakdown }) {
  if (!breakdown?.length) return null;
  return (
    <Table>
      <thead>
        <tr>
          <Th>Required skill</Th>
          <Th>Priority</Th>
          <Th>Result</Th>
          <Th>Evidence</Th>
          <Th className="text-right">Credit</Th>
        </tr>
      </thead>
      <tbody>
        {breakdown.map((b) => (
          <tr key={b.skill}>
            <Td className="font-medium">{b.skill}</Td>
            <Td className="tabular">{b.weight}</Td>
            <Td className={b.matched_by === "none" ? "text-muted" : ""}>{MATCHED_BY[b.matched_by]}</Td>
            <Td className="text-ink-2">{b.evidence || "—"}</Td>
            <Td className="tabular text-right">{Math.round(b.score * 100)}%</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function ApplySection({ hackathon, application, onDone }) {
  const { user } = useAuth();
  const [file, setFile] = useState(null);
  const [github, setGithub] = useState(user.github_url || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const ended = hackathon.phase === "ended";

  const submit = async (e) => {
    e.preventDefault();
    if (!file) return setError("Choose your resume first.");
    const form = new FormData();
    form.append("resume", file);
    if (github.trim()) form.append("github_url", github.trim());
    setBusy(true);
    setError(null);
    try {
      await api(`/hackathons/${hackathon.id}/applications`, { method: "POST", form });
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Your application"
        subtitle={application ? `Submitted ${fmtDateTime(application.applied_at)} · ${application.resume_filename}` : "Upload your resume to be scored against this event's requirements."}
        action={application && <ApplicationBadge status={application.status} />}
      />
      <div className="space-y-5 p-5">
        {application && (
          <>
            <div className="flex flex-wrap items-center gap-6">
              <div>
                <div className="text-sm text-ink-2">Match score</div>
                <div className="text-3xl font-semibold tracking-tight">{application.score === null ? "—" : Math.round(application.score)}</div>
              </div>
              <div className="text-sm text-ink-2">Shortlist threshold: {hackathon.shortlist_threshold}</div>
            </div>
            {application.review_note && <Notice>{application.review_note}. An organizer will review your application manually.</Notice>}
            <MatchBreakdown breakdown={application.match_details} />
          </>
        )}
        {!ended && (
          <form onSubmit={submit} className="space-y-4 border-t border-line pt-5 first:border-0 first:pt-0">
            <ErrorBanner>{error}</ErrorBanner>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={application ? "Re-upload resume" : "Resume"} hint="PDF, DOCX or TXT, up to 5 MB.">
                <Input type="file" accept=".pdf,.docx,.txt" onChange={(e) => setFile(e.target.files[0] || null)} />
              </Field>
              <Field label="GitHub profile" hint="Your public repos add verified skill evidence.">
                <Input placeholder="https://github.com/username" value={github} onChange={(e) => setGithub(e.target.value)} />
              </Field>
            </div>
            <Button type="submit" busy={busy}>
              <FileUp className="size-4" aria-hidden /> {application ? "Re-apply" : "Apply"}
            </Button>
            {busy && <p className="text-sm text-ink-2">Parsing your resume and analysing your GitHub profile…</p>}
          </form>
        )}
      </div>
    </Card>
  );
}

function TeamSection({ hackathonId }) {
  const { data: team, loading } = useApi(`/hackathons/${hackathonId}/my-team`);
  if (loading) return null;
  return (
    <Card>
      <CardHeader title="Your team" subtitle={team ? team.description : "Teams are formed by the organizer once shortlisting closes."} action={<Users className="size-5 text-muted" aria-hidden />} />
      {team && (
        <div className="p-5">
          <div className="mb-3 text-lg font-semibold">{team.team_name}</div>
          <ul className="divide-y divide-line">
            {team.members.map((m) => (
              <li key={m.user.id} className="flex items-center justify-between py-2 text-sm">
                <span className="font-medium">{m.user.name}</span>
                <span className="text-ink-2">{m.role || "Generalist"}</span>
              </li>
            ))}
          </ul>
          {team.coverage !== null && (
            <div className="mt-4 text-sm text-ink-2">
              Covers {fmtPct(team.coverage)} of required skills
              {team.missing_skills.length > 0 && <> · missing {team.missing_skills.join(", ")}</>}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function SubmissionSection({ hackathon }) {
  const { data: sub, reload, loading } = useApi(`/hackathons/${hackathon.id}/my-submission`);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  if (loading) return null;
  const values = form || { project_title: sub?.project_title || "", repository_url: sub?.repository_url || "" };
  const live = hackathon.phase === "live";

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/hackathons/${hackathon.id}/submissions`, { method: "POST", body: values });
      setForm(null);
      reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Project submission"
        subtitle={live ? "Submit your team's public GitHub repository. Only commits made before the deadline are evaluated." : hackathon.phase === "upcoming" ? "Submissions open when the hackathon starts." : "Submissions are closed."}
      />
      <div className="space-y-4 p-5">
        {sub && (
          <div className="text-sm">
            <div className="font-medium">{sub.project_title}</div>
            <a href={sub.repository_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
              {sub.repository_url.replace("https://github.com/", "")} <ExternalLink className="size-3.5" aria-hidden />
            </a>
            <div className="mt-1 text-ink-2">
              Status: {sub.status.replace("_", " ")} · commit {shortSha(sub.commit_sha)} · last updated {fmtDateTime(sub.submitted_at)}
            </div>
          </div>
        )}
        {live && (
          <form onSubmit={submit} className="space-y-4">
            <ErrorBanner>{error}</ErrorBanner>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Project title">
                <Input required minLength={2} value={values.project_title} onChange={(e) => setForm({ ...values, project_title: e.target.value })} />
              </Field>
              <Field label="Repository URL">
                <Input required placeholder="https://github.com/team/project" value={values.repository_url} onChange={(e) => setForm({ ...values, repository_url: e.target.value })} />
              </Field>
            </div>
            <Button type="submit" busy={busy}>
              {sub ? "Update submission" : "Submit project"}
            </Button>
          </form>
        )}
      </div>
    </Card>
  );
}

function TelemetrySection({ hackathonId }) {
  const { data } = useApi(`/telemetry/summary?hackathon_id=${hackathonId}`);
  if (!data) return null;
  return (
    <Card>
      <CardHeader title="Your IDE activity" subtitle="Recorded by the VERIQO VS Code extension during the event." action={<TelemetryFlag flag={data.flag} />} />
      <div className="grid grid-cols-2 gap-4 p-5 sm:grid-cols-4">
        <div>
          <div className="text-sm text-ink-2">Active time</div>
          <div className="text-xl font-semibold">{Math.round(data.active_seconds / 60)} min</div>
        </div>
        <div>
          <div className="text-sm text-ink-2">Typed</div>
          <div className="text-xl font-semibold">{fmtNum(data.typed_chars)}</div>
        </div>
        <div>
          <div className="text-sm text-ink-2">Pasted + inserted</div>
          <div className="text-xl font-semibold">{fmtNum(data.pasted_chars + data.bulk_insert_chars)}</div>
        </div>
        <div>
          <div className="text-sm text-ink-2">Paste ratio</div>
          <div className="text-xl font-semibold">{fmtRatio(data.paste_ratio)}</div>
        </div>
      </div>
      {!data.batches && (
        <div className="px-5 pb-5">
          <Notice icon={Plug}>
            No activity recorded yet.{" "}
            <Link className="font-medium text-accent hover:underline" to="/extension">
              Set up the VS Code extension
            </Link>{" "}
            so your effort is verified.
          </Notice>
        </div>
      )}
    </Card>
  );
}

function OwnReport({ hackathonId }) {
  const { data: report } = useApi(`/hackathons/${hackathonId}/my-report`);
  if (!report) return null;
  return (
    <Card>
      <CardHeader title="Originality report" subtitle="The same report the judges see." action={<RiskBadge level={report.risk_level} />} />
      <div className="grid grid-cols-2 gap-4 p-5 sm:grid-cols-4">
        <div>
          <div className="text-sm text-ink-2">Matched code</div>
          <div className="text-xl font-semibold">{fmtPct(report.plagiarism_score)}</div>
        </div>
        <div>
          <div className="text-sm text-ink-2">Pre-event code</div>
          <div className="text-xl font-semibold">{fmtPct(report.pre_event_share)}</div>
        </div>
        <div>
          <div className="text-sm text-ink-2">Team paste ratio</div>
          <div className="text-xl font-semibold">{fmtRatio(report.paste_ratio)}</div>
        </div>
        <div>
          <div className="text-sm text-ink-2">Active time</div>
          <div className="text-xl font-semibold">{report.active_minutes ?? "—"} min</div>
        </div>
      </div>
      <ul className="list-disc space-y-1 px-10 pb-5 text-sm text-ink-2">
        {(report.details?.risk_reasons || []).map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </Card>
  );
}

export default function HackathonDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const { data: h, error, loading } = useApi(`/hackathons/${id}`);
  const apps = useApi(user.role === "participant" ? "/applications/mine" : null);
  if (loading) return <Spinner />;
  if (error) return <ErrorBanner>{error}</ErrorBanner>;
  const application = apps.data?.find((a) => a.hackathon_id === id);
  const shortlisted = application?.status === "shortlisted";

  return (
    <>
      <PageHeader eyebrow={h.theme} title={h.event_name} action={<PhaseChip phase={h.phase} />} />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          {user.role === "participant" && !apps.loading && (
            <>
              <ApplySection hackathon={h} application={application} onDone={apps.reload} />
              {shortlisted && <TeamSection hackathonId={id} />}
              {shortlisted && <SubmissionSection hackathon={h} />}
              {shortlisted && <TelemetrySection hackathonId={id} />}
              {shortlisted && <OwnReport hackathonId={id} />}
            </>
          )}
          {user.role !== "participant" && <Notice>You are viewing this event as {user.role === "judge" ? "a judge" : "an organizer who doesn't run it"}.</Notice>}
        </div>
        <aside className="space-y-6">
          <Card className="p-5">
            <div className="flex items-start gap-2 text-sm text-ink-2">
              <CalendarDays className="mt-0.5 size-4 shrink-0" aria-hidden />
              <div>
                <div>Starts {fmtDateTime(h.start_date)}</div>
                <div>Ends {fmtDateTime(h.end_date)}</div>
              </div>
            </div>
            {h.description && <p className="mt-4 whitespace-pre-line text-sm">{h.description}</p>}
            <div className="mt-4 text-sm text-ink-2">Teams of up to {h.max_team_size}</div>
          </Card>
          <Card>
            <CardHeader title="Required skills" />
            <ul className="divide-y divide-line">
              {h.requirements.map((r) => (
                <li key={r.id} className="flex items-center justify-between px-5 py-2.5 text-sm">
                  <span>{r.skill}</span>
                  <Chip>priority {r.priority}</Chip>
                </li>
              ))}
              {!h.requirements.length && <li className="px-5 py-3 text-sm text-muted">Open to all skills</li>}
            </ul>
          </Card>
          {application && (
            <Card className="p-5">
              <div className="text-sm text-ink-2">Your match</div>
              <div className="mt-2">
                <Meter value={application.score} />
              </div>
            </Card>
          )}
        </aside>
      </div>
    </>
  );
}
