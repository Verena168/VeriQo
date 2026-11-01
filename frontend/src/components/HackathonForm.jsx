import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { fromLocalInput, toLocalInput } from "../lib/format";
import { useApi } from "../lib/useApi";
import { Button, Card, ErrorBanner, Field, Input, Select, Textarea } from "./ui";

const PRIORITY = { 1: "Nice to have", 2: "Useful", 3: "Important", 4: "Very important", 5: "Essential" };

const numOrNull = (v) => (v === "" || v === null || v === undefined ? null : Number(v));

function Checkbox({ checked, onChange, label, hint }) {
  return (
    <label className="flex items-start gap-3 text-sm">
      <input type="checkbox" className="mt-1" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>
        <span className="font-medium">{label}</span>
        {hint && <span className="block text-ink-2">{hint}</span>}
      </span>
    </label>
  );
}

export default function HackathonForm({ initial, submitLabel, onSubmit }) {
  const catalog = useApi("/analytics/meta/skills");
  const [form, setForm] = useState(() => ({
    event_name: initial?.event_name || "",
    theme: initial?.theme || "",
    description: initial?.description || "",
    problem_statement: initial?.problem_statement || "",
    theme_importance: initial?.theme_importance || "normal",
    start_date: toLocalInput(initial?.start_date),
    end_date: toLocalInput(initial?.end_date),
    registration_opens_at: toLocalInput(initial?.registration_opens_at),
    registration_closes_at: toLocalInput(initial?.registration_closes_at),
    participation_mode: initial?.participation_mode || "team",
    min_team_size: initial?.min_team_size ?? 1,
    max_team_size: initial?.max_team_size ?? 4,
    age_min: initial?.age_min ?? "",
    age_max: initial?.age_max ?? "",
    student_only: initial?.student_only ?? false,
    fee_amount: initial?.fee_amount ?? 0,
    prizes: initial?.prizes?.map((p) => ({ title: p.title, amount: p.amount ?? "", note: p.note ?? "" })) || [],
    shortlist_threshold: initial?.shortlist_threshold ?? 60,
    is_score_published: initial?.is_score_published ?? false,
    requirements: initial?.requirements?.map(({ skill, priority, description }) => ({ skill, priority, description })) || [
      { skill: "", priority: 3, description: "" },
    ],
  }));
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const setVal = (k) => (v) => setForm({ ...form, [k]: v });
  const setReq = (i, k, v) => setForm({ ...form, requirements: form.requirements.map((r, j) => (j === i ? { ...r, [k]: v } : r)) });
  const setPrize = (i, k, v) => setForm({ ...form, prizes: form.prizes.map((p, j) => (j === i ? { ...p, [k]: v } : p)) });
  const solo = form.participation_mode === "solo";

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        ...form,
        theme: form.theme || null,
        description: form.description || null,
        problem_statement: form.problem_statement || null,
        start_date: fromLocalInput(form.start_date),
        end_date: fromLocalInput(form.end_date),
        registration_opens_at: fromLocalInput(form.registration_opens_at),
        registration_closes_at: fromLocalInput(form.registration_closes_at),
        min_team_size: solo ? 1 : Number(form.min_team_size),
        max_team_size: solo ? 1 : Number(form.max_team_size),
        age_min: numOrNull(form.age_min),
        age_max: numOrNull(form.age_max),
        fee_amount: Number(form.fee_amount || 0),
        prizes: form.prizes
          .filter((p) => p.title.trim())
          .map((p) => ({ title: p.title.trim(), amount: numOrNull(p.amount), note: p.note.trim() || null })),
        shortlist_threshold: Number(form.shortlist_threshold),
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
        <Field label="Problem statement" hint="What teams should build. Also used by the AI to spot related past projects.">
          <Textarea rows={3} value={form.problem_statement} onChange={set("problem_statement")} />
        </Field>
        <Field label="Theme relevance" hint="How much the AI weighs past projects related to your theme and problem statement.">
          <Select value={form.theme_importance} onChange={set("theme_importance")}>
            <option value="off">Off: ignore past projects</option>
            <option value="normal">Normal</option>
            <option value="high">High: strongly prefer related experience</option>
          </Select>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Starts" hint="Coding and telemetry tracking begin.">
            <Input type="datetime-local" required value={form.start_date} onChange={set("start_date")} />
          </Field>
          <Field label="Ends" hint="Submission deadline; only commits before this are scanned.">
            <Input type="datetime-local" required value={form.end_date} onChange={set("end_date")} />
          </Field>
          <Field label="Registration opens" hint="Optional. Leave empty to open now.">
            <Input type="datetime-local" value={form.registration_opens_at} onChange={set("registration_opens_at")} />
          </Field>
          <Field label="Registration closes" hint="Optional. Leave empty to keep it open until the event ends.">
            <Input type="datetime-local" value={form.registration_closes_at} onChange={set("registration_closes_at")} />
          </Field>
        </div>
      </Card>

      <Card className="space-y-4 p-5">
        <h2 className="font-semibold">Participation &amp; eligibility</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Format">
            <Select value={form.participation_mode} onChange={set("participation_mode")}>
              <option value="team">Teams</option>
              <option value="solo">Solo</option>
            </Select>
          </Field>
          <Field label="Min team size">
            <Input type="number" min={1} max={10} required disabled={solo} value={solo ? 1 : form.min_team_size} onChange={set("min_team_size")} />
          </Field>
          <Field label="Max team size">
            <Input type="number" min={1} max={10} required disabled={solo} value={solo ? 1 : form.max_team_size} onChange={set("max_team_size")} />
          </Field>
          <Field label="Minimum age" hint="Optional. Checked at the start date.">
            <Input type="number" min={8} max={100} value={form.age_min} onChange={set("age_min")} />
          </Field>
          <Field label="Maximum age" hint="Optional.">
            <Input type="number" min={8} max={100} value={form.age_max} onChange={set("age_max")} />
          </Field>
        </div>
        <Checkbox
          checked={form.student_only}
          onChange={setVal("student_only")}
          label="Students only"
          hint="Applicants must mark themselves as students in their profile (self-declared)."
        />
      </Card>

      <Card className="space-y-4 p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Prizes &amp; fee</h2>
          <Button type="button" variant="secondary" size="sm" onClick={() => setForm({ ...form, prizes: [...form.prizes, { title: "", amount: "", note: "" }] })}>
            <Plus className="size-4" aria-hidden /> Add prize
          </Button>
        </div>
        <Field label="Registration fee (INR)" hint="0 for a free event. Payments are not collected through VERIQO yet.">
          <Input type="number" min={0} max={100000} step="1" value={form.fee_amount} onChange={set("fee_amount")} />
        </Field>
        {form.prizes.map((p, i) => (
          <div key={i} className="grid items-end gap-3 sm:grid-cols-[1fr_140px_1.4fr_auto]">
            <Field label={i === 0 ? "Prize" : ""}>
              <Input required value={p.title} onChange={(e) => setPrize(i, "title", e.target.value)} placeholder="e.g. Winner" />
            </Field>
            <Field label={i === 0 ? "Amount (INR)" : ""}>
              <Input type="number" min={0} value={p.amount} onChange={(e) => setPrize(i, "amount", e.target.value)} />
            </Field>
            <Field label={i === 0 ? "Note" : ""}>
              <Input value={p.note} onChange={(e) => setPrize(i, "note", e.target.value)} placeholder="Optional, e.g. + internship interview" />
            </Field>
            <Button type="button" variant="ghost" aria-label="Remove prize" onClick={() => setForm({ ...form, prizes: form.prizes.filter((_, j) => j !== i) })}>
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))}
      </Card>

      <Card className="space-y-4 p-5">
        <h2 className="font-semibold">Shortlisting</h2>
        <Field label="Suggested shortlist threshold" hint="The AI suggests shortlisting applicants at or above this match score (0–100). You make the final decision.">
          <Input type="number" min={0} max={100} required value={form.shortlist_threshold} onChange={set("shortlist_threshold")} />
        </Field>
        <Checkbox
          checked={form.is_score_published}
          onChange={setVal("is_score_published")}
          label="Share AI match feedback with applicants after publishing"
          hint="Off by default: applicants only see their outcome, never their score."
        />
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
