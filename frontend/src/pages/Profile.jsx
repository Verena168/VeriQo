import { useState } from "react";
import { Button, Card, ErrorBanner, Field, Input, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function Profile() {
  const { user, refresh } = useAuth();
  const participant = user.role === "participant";
  const [form, setForm] = useState({
    name: user.name,
    github_url: user.github_url || "",
    date_of_birth: user.date_of_birth || "",
    is_student: user.is_student,
    institution: user.institution || "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const set = (k) => (e) => {
    setSaved(false);
    setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/me", {
        method: "PATCH",
        body: participant
          ? {
              ...form,
              github_url: form.github_url.trim() || null,
              date_of_birth: form.date_of_birth || null,
              institution: form.institution.trim() || null,
            }
          : { name: form.name },
      });
      await refresh();
      setSaved(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Your profile" subtitle={participant ? "Hackathons use these details to check eligibility." : user.email} />
      <ErrorBanner>{error}</ErrorBanner>
      <form onSubmit={submit}>
        <Card className="space-y-4 p-5">
          <Field label="Full name">
            <Input required minLength={2} value={form.name} onChange={set("name")} />
          </Field>
          {participant && (
            <>
              <Field label="GitHub profile">
                <Input placeholder="https://github.com/username" value={form.github_url} onChange={set("github_url")} />
              </Field>
              <Field label="Date of birth" hint="Used only to check a hackathon's age limits.">
                <Input type="date" value={form.date_of_birth} onChange={set("date_of_birth")} />
              </Field>
              <label className="flex items-start gap-3 text-sm">
                <input type="checkbox" className="mt-1" checked={form.is_student} onChange={set("is_student")} />
                <span>
                  <span className="font-medium">I am currently a student</span>
                  <span className="block text-ink-2">Required for students-only hackathons. Organizers may ask for proof.</span>
                </span>
              </label>
              <Field label="College / institution">
                <Input value={form.institution} onChange={set("institution")} placeholder="e.g. St. Francis Institute of Technology" />
              </Field>
            </>
          )}
          <div className="flex items-center justify-end gap-3">
            {saved && <span className="text-sm text-good">Saved</span>}
            <Button type="submit" busy={busy}>
              Save profile
            </Button>
          </div>
        </Card>
      </form>
    </div>
  );
}
