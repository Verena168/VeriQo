import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button, ErrorBanner, Field, Input } from "../components/ui";
import { useAuth } from "../lib/auth";
import AuthShell from "./AuthShell";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(form.email, form.password);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Sign in" subtitle="Welcome back to VERIQO.">
      <ErrorBanner>{error}</ErrorBanner>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            autoComplete="current-password"
            required
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </Field>
        <Button type="submit" busy={busy} className="w-full">
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-sm text-ink-2">
        New here?{" "}
        <Link to="/register" className="font-medium text-accent hover:underline">
          Create an account
        </Link>
      </p>
    </AuthShell>
  );
}
