import { Plus, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { Button, Card, Chip, Empty, ErrorBanner, Input, Notice, Select, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtPct } from "../../lib/format";
import { useApi } from "../../lib/useApi";

export default function Teams({ hackathon, canEdit }) {
  const { data: teams, error, loading, setData, reload } = useApi(`/hackathons/${hackathon.id}/teams`);
  const apps = useApi(canEdit ? `/hackathons/${hackathon.id}/applications` : null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [newName, setNewName] = useState("");

  const run = async (fn) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const formTeams = () => run(async () => setData(await api(`/hackathons/${hackathon.id}/teams/form`, { method: "POST" })));
  const move = (userId, teamId) => run(async () => setData(await api(`/teams/${teamId}/members`, { method: "POST", body: { user_id: userId } })));
  const remove = (userId, teamId) => run(async () => setData(await api(`/teams/${teamId}/members/${userId}`, { method: "DELETE" })));
  const addTeam = (e) => {
    e.preventDefault();
    run(async () => {
      await api(`/hackathons/${hackathon.id}/teams`, { method: "POST", body: { team_name: newName } });
      setNewName("");
      reload();
    });
  };

  if (loading) return <Spinner />;
  const placed = new Set(teams.flatMap((t) => t.members.map((m) => m.user.id)));
  const unplaced = (apps.data || []).filter((a) => a.status === "shortlisted" && !placed.has(a.user.id));

  return (
    <div className="space-y-6">
      <ErrorBanner>{error || actionError}</ErrorBanner>
      {canEdit && (
        <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <h2 className="font-semibold">AI team formation</h2>
            <p className="text-sm text-ink-2">
              Groups shortlisted participants into teams of {hackathon.max_team_size}, spreading top scorers and covering as many required skills as possible.
              {teams.length > 0 && " Re-running replaces the current teams."}
            </p>
          </div>
          <Button onClick={formTeams} busy={busy}>
            <Sparkles className="size-4" aria-hidden /> {teams.length ? "Re-form teams" : "Form teams with AI"}
          </Button>
        </Card>
      )}
      {canEdit && unplaced.length > 0 && (
        <Notice>
          Not in a team yet: {unplaced.map((a) => a.user.name).join(", ")}. Use “Add member” on a team below.
        </Notice>
      )}
      {!teams.length ? (
        <Card>
          <Empty title="No teams yet">{canEdit ? "Shortlist applicants first, then form teams." : "The organizer hasn't formed teams yet."}</Empty>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {teams.map((t) => (
            <Card key={t.id} className="flex flex-col">
              <div className="border-b border-line px-5 py-4">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-semibold">{t.team_name}</h3>
                  <span className="text-sm text-ink-2">
                    {t.members.length}/{hackathon.max_team_size}
                  </span>
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
                    <div>
                      <div className="font-medium">{m.user.name}</div>
                      <div className="text-xs text-ink-2">
                        {m.role || "Generalist"}
                        {m.ai_recommended && " · AI-placed"}
                      </div>
                    </div>
                    {canEdit && (
                      <div className="flex items-center gap-1">
                        <select
                          className="rounded-md border border-line bg-surface px-1.5 py-1 text-xs"
                          value=""
                          onChange={(e) => move(m.user.id, e.target.value)}
                          aria-label={`Move ${m.user.name} to another team`}
                        >
                          <option value="">Move…</option>
                          {teams.filter((o) => o.id !== t.id).map((o) => (
                            <option key={o.id} value={o.id}>
                              {o.team_name}
                            </option>
                          ))}
                        </select>
                        <button onClick={() => remove(m.user.id, t.id)} className="rounded p-1 text-muted hover:text-bad" aria-label={`Remove ${m.user.name}`}>
                          <X className="size-4" />
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              <div className="space-y-2 border-t border-line px-5 py-3">
                {t.missing_skills.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1 text-xs text-ink-2">
                    Missing:
                    {t.missing_skills.map((s) => (
                      <Chip key={s}>{s}</Chip>
                    ))}
                  </div>
                )}
                {canEdit && unplaced.length > 0 && t.members.length < hackathon.max_team_size && (
                  <Select value="" onChange={(e) => e.target.value && move(e.target.value, t.id)} aria-label={`Add member to ${t.team_name}`}>
                    <option value="">Add member…</option>
                    {unplaced.map((a) => (
                      <option key={a.user.id} value={a.user.id}>
                        {a.user.name}
                      </option>
                    ))}
                  </Select>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
      {canEdit && (
        <form onSubmit={addTeam} className="flex max-w-md gap-2">
          <Input placeholder="New team name" value={newName} onChange={(e) => setNewName(e.target.value)} required />
          <Button type="submit" variant="secondary">
            <Plus className="size-4" aria-hidden /> Add team
          </Button>
        </form>
      )}
    </div>
  );
}
