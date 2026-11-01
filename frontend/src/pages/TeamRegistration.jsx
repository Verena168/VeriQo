import { ArrowLeft, CheckCircle2, Circle, Crown, FileText, MailPlus, RefreshCw, Trash2, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Invitations from "../components/Invitations";
import {
  Button,
  Card,
  CardHeader,
  Chip,
  ErrorBanner,
  Field,
  Input,
  Notice,
  PageHeader,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { api, openFile } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";

const MEMBER_STATUS = { confirmed: ["good", "Confirmed"], invited: ["warning", "Waiting for confirmation"] };
const PARSE = {
  ok: ["good", "Analysed"],
  unreadable: ["warning", "Text couldn't be read: the organizer will review it manually"],
  failed: ["critical", "Analysis failed: please upload again"],
  pending: ["neutral", "Not uploaded yet"],
};

function Step({ done, children }) {
  return (
    <li className={`flex items-center gap-2 text-sm ${done ? "text-ink" : "text-ink-2"}`}>
      {done ? <CheckCircle2 className="size-4 text-good" aria-hidden /> : <Circle className="size-4 text-muted" aria-hidden />}
      {children}
    </li>
  );
}

function StartForm({ hackathon, onCreated }) {
  const { user } = useAuth();
  const solo = hackathon.participation_mode === "solo";
  const [name, setName] = useState(solo ? user.name : "");
  const [seeking, setSeeking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onCreated(await api(`/hackathons/${hackathon.id}/registrations`, { method: "POST", body: { team_name: name, seeking_teammates: seeking } }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <CardHeader
        title={solo ? "Register" : "Start your team"}
        subtitle={solo ? "This is a solo hackathon." : `You'll be the Team Lead. Teams have ${hackathon.min_team_size}–${hackathon.max_team_size} members; you invite the others next.`}
      />
      <form onSubmit={submit} className="space-y-4 p-5">
        <ErrorBanner>{error}</ErrorBanner>
        {!solo && (
          <Field label="Team name">
            <Input required minLength={2} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
        )}
        {!solo && (
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-1" checked={seeking} onChange={(e) => setSeeking(e.target.checked)} />
            <span>
              <span className="font-medium">I'm registering alone and looking for teammates</span>
              <span className="block text-ink-2">If you're shortlisted, the organizer can place you in a team with complementary skills.</span>
            </span>
          </label>
        )}
        <Button type="submit" busy={busy}>
          {solo ? "Start registration" : "Create team"}
        </Button>
      </form>
    </Card>
  );
}

function MemberDocs({ reg, member, canEdit, onSaved }) {
  const a = member.artifact || {};
  const [file, setFile] = useState(null);
  const [github, setGithub] = useState(a.github_url || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => setGithub(member.artifact?.github_url || ""), [member.artifact?.github_url]);
  const [s, label] = PARSE[a.has_cv ? a.parse_status : "pending"] || PARSE.pending;

  const save = async (e) => {
    e.preventDefault();
    const form = new FormData();
    if (file) form.append("cv", file);
    if (github.trim() !== (a.github_url || "")) form.append("github_url", github.trim());
    if (![...form.keys()].length) return setError("Choose a CV file or change the GitHub link first.");
    setBusy(true);
    setError(null);
    try {
      onSaved(await api(`/registrations/${reg.team_id}/members/${member.user.id}/artifacts`, { method: "PUT", form }));
      setFile(null);
      e.target.reset();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium">
          {member.user.name} {member.is_lead && <Chip tone="accent">Lead</Chip>}
        </div>
        <StatusBadge status={s}>{label}</StatusBadge>
      </div>
      {a.has_cv && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
          <FileText className="size-4" aria-hidden /> {a.cv_filename}
          <Button size="sm" variant="ghost" type="button" onClick={() => openFile(`/teams/${reg.team_id}/members/${member.user.id}/cv`).catch((e) => setError(e.message))}>
            View
          </Button>
        </div>
      )}
      {a.parse_note && <p className="text-xs text-muted">{a.parse_note}</p>}
      {canEdit ? (
        <form onSubmit={save} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]">
          <Field label={a.has_cv ? "Replace CV" : "CV"} hint="PDF, DOCX or TXT, up to 5 MB.">
            <Input type="file" accept=".pdf,.docx,.txt" onChange={(e) => setFile(e.target.files[0] || null)} />
          </Field>
          <Field label="GitHub profile">
            <Input placeholder="https://github.com/username" value={github} onChange={(e) => setGithub(e.target.value)} />
          </Field>
          <Button type="submit" variant="secondary" busy={busy}>
            <Upload className="size-4" aria-hidden /> Save
          </Button>
          {error && <p className="text-sm text-bad sm:col-span-3">{error}</p>}
          {busy && <p className="text-sm text-ink-2 sm:col-span-3">Analysing the CV and GitHub profile…</p>}
        </form>
      ) : (
        a.github_url && (
          <a className="text-sm text-accent hover:underline" href={a.github_url} target="_blank" rel="noreferrer">
            {a.github_url.replace("https://github.com/", "@")}
          </a>
        )
      )}
    </div>
  );
}

export default function TeamRegistration() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const hk = useApi(`/hackathons/${id}`);
  const [poll, setPoll] = useState(null);
  const { data: reg, setData: setReg, loading, reload, error } = useApi(`/hackathons/${id}/registration`, { poll });
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(null);
  const [actionError, setActionError] = useState(null);
  const pending = reg?.members.some((m) => m.status === "invited");
  useEffect(() => setPoll(pending ? 10000 : null), [pending]); // see members confirm without reloading

  if (hk.loading || loading) return <Spinner />;
  if (hk.error || error) return <ErrorBanner>{hk.error || error}</ErrorBanner>;
  const h = hk.data;

  const run = async (key, fn) => {
    setBusy(key);
    setActionError(null);
    try {
      const out = await fn();
      if (out) setReg(out);
    } catch (e) {
      setActionError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const header = (
    <>
      <Link to={`/hackathons/${id}`} className="mb-4 inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> {h.event_name}
      </Link>
      <PageHeader title="Team registration" subtitle={reg ? reg.team_name : "Register your team for this hackathon."} />
    </>
  );

  if (!reg) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        {header}
        <Invitations hackathonId={id} onChange={(kind) => kind === "accept" && reload()} />
        {h.phase === "ended" ? <Notice>This hackathon has ended.</Notice> : <StartForm hackathon={h} onCreated={setReg} />}
      </div>
    );
  }

  const lead = reg.is_lead;
  const draft = reg.status === "draft";
  const solo = h.participation_mode === "solo";
  const confirmed = reg.members.filter((m) => m.status === "confirmed");
  const docsDone = confirmed.every((m) => m.artifact?.has_cv && m.artifact?.github_url);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {header}
      {!draft && reg.application && <Notice icon={CheckCircle2}>{reg.application.status_message}</Notice>}
      {draft && (
        <Card className="p-5">
          <ol className="grid gap-2 sm:grid-cols-4">
            <Step done>Team created</Step>
            <Step done={solo || (confirmed.length >= h.min_team_size && !pending) || (reg.seeking_teammates && !pending)}>Members confirmed</Step>
            <Step done={docsDone}>CVs &amp; GitHub</Step>
            <Step done={false}>Submitted</Step>
          </ol>
          {!lead && <p className="mt-3 text-sm text-ink-2">Your team lead submits the registration. You can upload your own CV and GitHub profile below.</p>}
        </Card>
      )}
      <ErrorBanner>{actionError}</ErrorBanner>

      {!solo && (
        <Card>
          <CardHeader
            title="Members"
            subtitle={
              reg.seeking_teammates
                ? "You're registering alone and looking for teammates."
                : `${confirmed.length} of up to ${h.max_team_size} confirmed. Invited members confirm with a code we email them.`
            }
          />
          <ul className="divide-y divide-line">
            {reg.members.map((m) => {
              const [s, label] = MEMBER_STATUS[m.status] || ["neutral", m.status];
              return (
                <li key={m.user.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm">
                  <div>
                    <div className="font-medium">
                      {m.user.name} {m.is_lead && <Crown className="inline size-3.5 text-warn" aria-label="Team lead" />}
                    </div>
                    <div className="text-xs text-muted">{m.user.email}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={s}>{label}</StatusBadge>
                    {lead && draft && m.status === "invited" && (
                      <Button size="sm" variant="ghost" busy={busy === `resend-${m.user.id}`} title="Resend code"
                        onClick={() => run(`resend-${m.user.id}`, () => api(`/registrations/${reg.team_id}/members/${m.user.id}/resend`, { method: "POST" }))}>
                        <RefreshCw className="size-4" aria-hidden /> Resend
                      </Button>
                    )}
                    {lead && draft && !m.is_lead && (
                      <Button size="sm" variant="ghost" aria-label={`Remove ${m.user.name}`} busy={busy === `rm-${m.user.id}`}
                        onClick={() => run(`rm-${m.user.id}`, () => api(`/registrations/${reg.team_id}/members/${m.user.id}`, { method: "DELETE" }))}>
                        <Trash2 className="size-4" />
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          {lead && draft && !reg.seeking_teammates && reg.members.length < h.max_team_size && (
            <form
              className="flex flex-wrap items-end gap-2 border-t border-line px-5 py-4"
              onSubmit={(e) => {
                e.preventDefault();
                run("invite", async () => {
                  const out = await api(`/registrations/${reg.team_id}/members`, { method: "POST", body: { email } });
                  setEmail("");
                  return out;
                });
              }}
            >
              <div className="min-w-60 flex-1">
                <Field label="Invite a member by email" hint="They need a VERIQO participant account.">
                  <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@college.edu" />
                </Field>
              </div>
              <Button type="submit" busy={busy === "invite"}>
                <MailPlus className="size-4" aria-hidden /> Send invite
              </Button>
            </form>
          )}
        </Card>
      )}

      <Card>
        <CardHeader title="CVs and GitHub profiles" subtitle="Required for every member. VERIQO scores the whole team on its combined skills." />
        <div className="divide-y divide-line">
          {confirmed.map((m) => (
            <MemberDocs key={m.user.id} reg={reg} member={m} canEdit={draft && (lead || m.user.id === user.id)} onSaved={setReg} />
          ))}
        </div>
      </Card>

      {draft && (
        <Card className="p-5">
          <h2 className="mb-2 font-semibold">Submit</h2>
          {reg.checklist.length ? (
            <ul className="mb-4 list-disc space-y-1 pl-5 text-sm text-ink-2">
              {reg.checklist.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : (
            <p className="mb-4 text-sm text-good">Everything's ready. Once submitted, the team can't be changed.</p>
          )}
          {lead && (
            <div className="flex flex-wrap gap-2">
              <Button disabled={reg.checklist.length > 0} busy={busy === "submit"}
                onClick={() => run("submit", () => api(`/registrations/${reg.team_id}/submit`, { method: "POST" }))}>
                Submit registration
              </Button>
              <Button variant="danger" busy={busy === "discard"}
                onClick={() => {
                  if (window.confirm("Discard this registration? Invitations and uploaded CVs are removed.")) {
                    run("discard", async () => {
                      await api(`/registrations/${reg.team_id}`, { method: "DELETE" });
                      navigate(`/hackathons/${id}`);
                    });
                  }
                }}>
                Discard
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
