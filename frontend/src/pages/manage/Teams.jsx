import { Crown, Sparkles } from "lucide-react";
import { useState } from "react";
import { Button, Card, Chip, Empty, ErrorBanner, Notice, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtPct } from "../../lib/format";
import { useApi } from "../../lib/useApi";

export default function Teams({ hackathon, canEdit }) {
  const { data: teams, error, loading, reload } = useApi(`/hackathons/${hackathon.id}/teams`);
  const apps = useApi(canEdit ? `/hackathons/${hackathon.id}/applications` : null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [formedCount, setFormedCount] = useState(null);

  const formTeams = async () => {
    setBusy(true);
    setActionError(null);
    try {
      const formed = await api(`/hackathons/${hackathon.id}/teams/form`, { method: "POST" });
      setFormedCount(formed.length);
      reload();
      apps.reload();
    } catch (e) {
      setActionError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Spinner />;
  const seekers = (apps.data || []).filter((a) => a.seeking_teammates && a.members.length === 1);
  const shortlistedSeekers = seekers.filter((a) => a.status === "shortlisted");

  return (
    <div className="space-y-6">
      <ErrorBanner>{error || actionError}</ErrorBanner>
      {canEdit && hackathon.participation_mode === "team" && (
        <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
          <div className="max-w-2xl">
            <h2 className="font-semibold">AI team formation</h2>
            <p className="text-sm text-ink-2">
              Teams register themselves. Participants who registered alone and asked for teammates can be placed into skill-balanced teams here, after
              you shortlist them. {seekers.length} looking for teammates · {shortlistedSeekers.length} shortlisted.
            </p>
            {formedCount !== null && (
              <p className="mt-1 text-sm text-good">
                Formed {formedCount} team{formedCount === 1 ? "" : "s"}. Members see their new team once you publish results.
              </p>
            )}
          </div>
          <Button onClick={formTeams} busy={busy} disabled={shortlistedSeekers.length < 2}>
            <Sparkles className="size-4" aria-hidden /> Form teams with AI
          </Button>
        </Card>
      )}
      {!teams.length ? (
        <Card>
          <Empty title="No registered teams yet">Teams appear here once their lead submits the registration.</Empty>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {teams.map((t) => (
            <Card key={t.id} className="flex flex-col">
              <div className="border-b border-line px-5 py-4">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-semibold">{t.team_name}</h3>
                  {t.formed_by === "ai" ? <Chip tone="accent">AI-formed</Chip> : <span className="text-sm text-ink-2">{t.members.length} member{t.members.length === 1 ? "" : "s"}</span>}
                </div>
                {t.coverage !== null && (
                  <div className="mt-2">
                    <div className="flex justify-between text-xs text-ink-2">
                      <span>Skill coverage</span>
                      <span className="tabular">{fmtPct(t.coverage)}</span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                      <div className="h-full rounded-full bg-accent" style={{ width: `${t.coverage}%` }} />
                    </div>
                  </div>
                )}
              </div>
              <ul className="flex-1 divide-y divide-line">
                {t.members.map((m) => (
                  <li key={m.user.id} className="flex items-center justify-between gap-2 px-5 py-2.5 text-sm">
                    <span className="font-medium">
                      {m.user.name} {m.is_lead && <Crown className="inline size-3.5 text-warn" aria-label="Team lead" />}
                    </span>
                    <span className="text-xs text-ink-2">{m.role || (m.ai_recommended ? "AI-placed" : "")}</span>
                  </li>
                ))}
              </ul>
              {t.missing_skills.length > 0 && (
                <div className="flex flex-wrap items-center gap-1 border-t border-line px-5 py-3 text-xs text-ink-2">
                  Missing:
                  {t.missing_skills.map((s) => (
                    <Chip key={s}>{s}</Chip>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
      {canEdit && hackathon.participation_mode === "team" && seekers.length > 0 && shortlistedSeekers.length < 2 && (
        <Notice>Shortlist at least two solo registrants who are looking for teammates to form AI teams.</Notice>
      )}
    </div>
  );
}
