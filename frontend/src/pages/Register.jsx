import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button, ErrorBanner, Field, Input, Select } from "../components/ui";
import { useAuth } from "../lib/auth";
import AuthShell from "./AuthShell";

export default function Register() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "participant", github_url: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({ ...form, github_url: form.github_url.trim() || null });
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Create your account" subtitle="Join as a participant, organizer or judge.">
      <ErrorBanner>{error}</ErrorBanner>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Full name">
          <Input required minLength={2} value={form.name} onChange={set("name")} autoComplete="name" />
        </Field>
        <Field label="Email">
          <Input type="email" required value={form.email} onChange={set("email")} autoComplete="email" />
        </Field>
        <Field label="Password" hint="At least 8 characters.">
          <Input type="password" required minLength={8} maxLength={72} value={form.password} onChange={set("password")} autoComplete="new-password" />
        </Field>
        <Field label="Role">
          <Select value={form.role} onChange={set("role")}>
            <option value="participant">Participant</option>
            <option value="organizer">Organizer</option>
            <option value="judge">Judge</option>
          </Select>
        </Field>
        {form.role === "participant" && (
          <Field label="GitHub profile" hint="Optional. Used to verify your skills.">
            <Input placeholder="https://github.com/username" value={form.github_url} onChange={set("github_url")} />
          </Field>
        )}
        <Button type="submit" busy={busy} className="w-full">
          Create account
        </Button>
      </form>
      <p className="mt-6 text-sm text-ink-2">
        Already registered?{" "}
        <Link to="/login" className="font-medium text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}
