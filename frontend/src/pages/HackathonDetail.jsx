import { CalendarDays, ExternalLink, FileUp, Plug, Users, Clock, Info, PartyPopper } from "lucide-react";
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

/** Mirrors services/eligibility.py so applicants see what to fix before uploading anything.
 *  The server still enforces these rules; this is only for a clearer experience. */
function eligibilityProblems(user, h) {
  const problems = [];
  const now = new Date();
  if (h.registration_opens_at && now < new Date(h.registration_opens_at)) {
    problems.push(`Registration opens ${fmtDateTime(h.registration_opens_at)}.`);
  }
  if (now > new Date(h.registration_closes_at || h.end_date)) problems.push("Registration has closed.");
  if (h.age_min != null || h.age_max != null) {
    if (!user.date_of_birth) {
      problems.push("Add your date of birth: this hackathon has an age requirement.");
    } else {
      const [by, bm, bd] = user.date_of_birth.split("-").map(Number);
      const s = new Date(h.start_date);
      const age = s.getFullYear() - by - (s.getMonth() + 1 < bm || (s.getMonth() + 1 === bm && s.getDate() < bd) ? 1 : 0);
      if (h.age_min != null && age < h.age_min) problems.push(`You must be at least ${h.age_min} when it starts (you will be ${age}).`);
      if (h.age_max != null && age > h.age_max) problems.push(`You must be ${h.age_max} or younger when it starts (you will be ${age}).`);
    }
  }
  if (h.student_only && !user.is_student) problems.push("This hackathon is for students only. Mark yourself as a student if you are one.");
  return problems;
}

function ApplySection({ hackathon, application, onDone }) {
  const { user } = useAuth();
  const [file, setFile] = useState(null);
  const [github, setGithub] = useState(user.github_url || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const ended = hackathon.phase === "ended";
  const problems = eligibilityProblems(user, hackathon); // the server enforces the same rules

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
        subtitle={application ? `Submitted ${fmtDateTime(application.applied_at)} · ${application.resume_filename}` : "Upload your resume and GitHub profile to register for this event."}
        action={application && <ApplicationBadge status={application.state} />}
      />
      <div className="space-y-5 p-5">
        {application && (
          <>
            {/* The AI match score is never shown to participants; only the published outcome. */}
            <Notice icon={application.state === "under_review" ? Clock : application.state === "shortlisted" ? PartyPopper : Info}>
              {application.status_message}
              {application.published_at && <span className="text-muted"> · Results published {fmtDateTime(application.published_at)}</span>}
            </Notice>
            {application.feedback && (
              <div>
                <h3 className="mb-2 text-sm font-medium">Feedback shared by the organizer</h3>
                <MatchBreakdown breakdown={application.feedback.breakdown} />
              </div>
            )}
          </>
        )}
        {!ended && problems.length > 0 && (
          <Notice icon={Info}>
            <div className="font-medium">Before you can apply:</div>
            <ul className="mt-1 list-disc pl-5">
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            <Link to="/profile" className="mt-2 inline-block font-medium text-accent hover:underline">
              Update your profile
            </Link>
          </Notice>
        )}
        {!ended && problems.length === 0 && (
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
  const shortlisted = application?.state === "shortlisted"; // published decisions only

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
          </Card>
          {h.problem_statement && (
            <Card className="p-5">
              <h3 className="mb-2 text-sm font-semibold">Problem statement</h3>
              <p className="whitespace-pre-line text-sm">{h.problem_statement}</p>
            </Card>
          )}
          <Card>
            <CardHeader title="Rules" />
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 px-5 py-4 text-sm">
              <dt className="text-ink-2">Format</dt>
              <dd>{h.participation_mode === "solo" ? "Solo" : `Teams of ${h.min_team_size === h.max_team_size ? h.max_team_size : `${h.min_team_size}–${h.max_team_size}`}`}</dd>
              <dt className="text-ink-2">Registration</dt>
              <dd>
                {h.registration_opens_at ? `${fmtDateTime(h.registration_opens_at)} – ` : "Open until "}
                {fmtDateTime(h.registration_closes_at || h.end_date)}
              </dd>
              {(h.age_min || h.age_max) && (
                <>
                  <dt className="text-ink-2">Age</dt>
                  <dd>{h.age_min && h.age_max ? `${h.age_min}–${h.age_max}` : h.age_min ? `${h.age_min}+` : `Up to ${h.age_max}`} at the start date</dd>
                </>
              )}
              {h.student_only && (
                <>
                  <dt className="text-ink-2">Who</dt>
                  <dd>Students only</dd>
                </>
              )}
              <dt className="text-ink-2">Fee</dt>
              <dd>{Number(h.fee_amount) > 0 ? `₹${Number(h.fee_amount).toLocaleString()}` : "Free"}</dd>
            </dl>
          </Card>
          {h.prizes?.length > 0 && (
            <Card>
              <CardHeader title="Prizes" />
              <ul className="divide-y divide-line">
                {h.prizes.map((p, i) => (
                  <li key={i} className="px-5 py-2.5 text-sm">
                    <div className="flex justify-between gap-3">
                      <span className="font-medium">{p.title}</span>
                      {p.amount != null && <span className="tabular">₹{Number(p.amount).toLocaleString()}</span>}
                    </div>
                    {p.note && <div className="text-xs text-ink-2">{p.note}</div>}
                  </li>
                ))}
              </ul>
            </Card>
          )}
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
        </aside>
      </div>
    </>
  );
}
