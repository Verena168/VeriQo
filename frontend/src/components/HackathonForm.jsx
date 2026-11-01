import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { fromLocalInput, toLocalInput } from "../lib/format";
import { useApi } from "../lib/useApi";
import { Button, Card, ErrorBanner, Field, Input, Select, Textarea } from "./ui";

const PRIORITY = { 1: "Nice to have", 2: "Useful", 3: "Important", 4: "Very important", 5: "Essential" };

export default function HackathonForm({ initial, submitLabel, onSubmit }) {
  const catalog = useApi("/analytics/meta/skills");
  const [form, setForm] = useState(() => ({
    event_name: initial?.event_name || "",
    theme: initial?.theme || "",
    description: initial?.description || "",
    start_date: toLocalInput(initial?.start_date),
    end_date: toLocalInput(initial?.end_date),
    shortlist_threshold: initial?.shortlist_threshold ?? 60,
    max_team_size: initial?.max_team_size ?? 4,
    requirements: initial?.requirements?.map(({ skill, priority, description }) => ({ skill, priority, description })) || [
      { skill: "", priority: 3, description: "" },
    ],
  }));
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const setReq = (i, k, v) => setForm({ ...form, requirements: form.requirements.map((r, j) => (j === i ? { ...r, [k]: v } : r)) });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        ...form,
        theme: form.theme || null,
        description: form.description || null,
        start_date: fromLocalInput(form.start_date),
        end_date: fromLocalInput(form.end_date),
        shortlist_threshold: Number(form.shortlist_threshold),
        max_team_size: Number(form.max_team_size),
        requirements: form.requirements
          .filter((r) => r.skill.trim())
          .map((r) => ({ skill: r.skill.trim(), priority: Number(r.priority), description: r.description || null })),
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-6">
      <ErrorBanner>{error}</ErrorBanner>
      <Card className="space-y-4 p-5">
        <h2 className="font-semibold">Event</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name">
            <Input required minLength={3} value={form.event_name} onChange={set("event_name")} />
          </Field>
          <Field label="Theme">
            <Input value={form.theme} onChange={set("theme")} placeholder="e.g. AI for Healthcare" />
          </Field>
        </div>
        <Field label="Description">
          <Textarea rows={3} value={form.description} onChange={set("description")} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Starts" hint="Coding and telemetry tracking begin.">
            <Input type="datetime-local" required value={form.start_date} onChange={set("start_date")} />
          </Field>
          <Field label="Ends" hint="Submission deadline; only commits before this are scanned.">
            <Input type="datetime-local" required value={form.end_date} onChange={set("end_date")} />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Shortlist threshold" hint="Applicants at or above this match score (0–100) are shortlisted.">
            <Input type="number" min={0} max={100} required value={form.shortlist_threshold} onChange={set("shortlist_threshold")} />
          </Field>
          <Field label="Max team size">
            <Input type="number" min={1} max={10} required value={form.max_team_size} onChange={set("max_team_size")} />
          </Field>
        </div>
      </Card>

      <Card className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="font-semibold">Required skills</h2>
            <p className="text-sm text-ink-2">Applicants are scored against these. Higher priority weighs more.</p>
          </div>
          <Button type="button" variant="secondary" size="sm" onClick={() => setForm({ ...form, requirements: [...form.requirements, { skill: "", priority: 3, description: "" }] })}>
            <Plus className="size-4" aria-hidden /> Add skill
          </Button>
        </div>
        <datalist id="skills-catalog">
          {catalog.data?.skills.map((s) => (
            <option key={s.name} value={s.name} />
          ))}
        </datalist>
        <div className="space-y-3">
          {form.requirements.map((r, i) => (
            <div key={i} className="grid items-end gap-3 sm:grid-cols-[1fr_180px_auto]">
              <Field label={i === 0 ? "Skill" : ""}>
                <Input list="skills-catalog" value={r.skill} onChange={(e) => setReq(i, "skill", e.target.value)} placeholder="Start typing, e.g. React" />
              </Field>
              <Field label={i === 0 ? "Priority" : ""}>
                <Select value={r.priority} onChange={(e) => setReq(i, "priority", e.target.value)}>
                  {Object.entries(PRIORITY).map(([v, l]) => (
                    <option key={v} value={v}>
                      {v} · {l}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button
                type="button"
                variant="ghost"
                aria-label="Remove skill"
                onClick={() => setForm({ ...form, requirements: form.requirements.filter((_, j) => j !== i) })}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
        </div>
      </Card>
      <div className="flex justify-end">
        <Button type="submit" busy={busy}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
