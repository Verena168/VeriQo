import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Card, CardHeader, Empty, ErrorBanner, Field, Input, Select, Spinner, StatusBadge, Table, Td, Th } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtDateTime, shortSha } from "../../lib/format";
import { useApi } from "../../lib/useApi";

const STATUS = { ready: ["good", "Analysed"], pending: ["neutral", "Analysing…"], failed: ["critical", "Failed"] };

export default function Corpus({ hackathon, canEdit }) {
  const [poll, setPoll] = useState(null);
  const { data, error, loading, reload } = useApi(`/hackathons/${hackathon.id}/references`, { poll });
  const [form, setForm] = useState({ repo_url: "", label: "", kind: "reference" });
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const pending = (data || []).some((r) => r.status === "pending");
  useEffect(() => setPoll(pending ? 4000 : null), [pending]);

  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    setActionError(null);
    try {
      await api(`/hackathons/${hackathon.id}/references`, { method: "POST", body: form });
      setForm({ repo_url: "", label: "", kind: form.kind });
      reload();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async (id) => {
    try {
      await api(`/references/${id}`, { method: "DELETE" });
      reload();
    } catch (err) {
      setActionError(err.message);
    }
  };

  if (loading) return <Spinner />;
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Plagiarism corpus"
          subtitle="Every submission is compared with every other submission automatically. Add past-event projects or known public repos as references, and your official starter code as a template so using it is never flagged."
        />
        <ErrorBanner>{error || actionError}</ErrorBanner>
        {!data.length ? (
          <Empty title="No reference repositories">Submissions will still be compared against each other.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Repository</Th>
                <Th>Type</Th>
                <Th>Status</Th>
                <Th>Added</Th>
                {canEdit && <Th />}
              </tr>
            </thead>
            <tbody>
              {data.map((r) => {
                const [s, label] = STATUS[r.status] || ["neutral", r.status];
                return (
                  <tr key={r.id}>
                    <Td>
                      <div className="font-medium">{r.label}</div>
                      <a href={r.repo_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                        {r.repo_url.replace("https://github.com/", "")} @ {shortSha(r.commit_sha)} <ExternalLink className="size-3" aria-hidden />
                      </a>
                    </Td>
                    <Td className="capitalize">{r.kind === "template" ? "Allowed template" : "Reference"}</Td>
                    <Td>
                      <StatusBadge status={s}>{label}</StatusBadge>
                      {r.error && <div className="mt-1 max-w-xs text-xs text-bad">{r.error}</div>}
                    </Td>
                    <Td className="text-ink-2">{fmtDateTime(r.created_at)}</Td>
                    {canEdit && (
                      <Td className="text-right">
                        <Button size="sm" variant="ghost" onClick={() => remove(r.id)} aria-label={`Remove ${r.label}`}>
                          <Trash2 className="size-4" />
                        </Button>
                      </Td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
      {canEdit && (
        <Card className="p-5">
          <form onSubmit={add} className="grid items-end gap-4 md:grid-cols-[2fr_1fr_160px_auto]">
            <Field label="GitHub repository">
              <Input required placeholder="https://github.com/owner/repo" value={form.repo_url} onChange={(e) => setForm({ ...form, repo_url: e.target.value })} />
            </Field>
            <Field label="Label">
              <Input required placeholder="e.g. 2025 winner" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
            </Field>
            <Field label="Type">
              <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="reference">Reference</option>
                <option value="template">Allowed template</option>
              </Select>
            </Field>
            <Button type="submit" busy={busy}>
              <Plus className="size-4" aria-hidden /> Add
            </Button>
          </form>
        </Card>
      )}
    </div>
  );
}
