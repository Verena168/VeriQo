import { MailCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { fmtDateTime } from "../lib/format";
import { useApi } from "../lib/useApi";
import { Button, Card, CardHeader, ErrorBanner, Input } from "./ui";

function InvitationRow({ inv, onDone }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const act = async (kind) => {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "accept") await api(`/team-invitations/${inv.team_id}/verify`, { method: "POST", body: { code } });
      else await api(`/team-invitations/${inv.team_id}/decline`, { method: "POST" });
      onDone(kind);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <li className="space-y-3 px-5 py-4">
      <div className="text-sm">
        <b>{inv.lead_name}</b> invited you to join <b>{inv.team_name}</b> for <b>{inv.hackathon_name}</b>
        <span className="text-muted"> · {fmtDateTime(inv.invited_at)}</span>
      </div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          act("accept");
        }}
      >
        <div className="w-40">
          <Input
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder="6-digit code"
            aria-label="Code from your email"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          />
        </div>
        <Button type="submit" busy={busy === "accept"} disabled={code.length !== 6}>
          Confirm &amp; join
        </Button>
        <Button type="button" variant="ghost" busy={busy === "decline"} onClick={() => act("decline")}>
          Decline
        </Button>
      </form>
      <p className="text-xs text-muted">We emailed you the code. It expires 15 minutes after it was sent; ask your team lead to resend it if needed.</p>
    </li>
  );
}

/** Pending team invitations for the signed-in participant (optionally only for one hackathon). */
export default function Invitations({ hackathonId, onChange }) {
  const { data, reload } = useApi("/me/team-invitations", { poll: 30000 });
  const list = (data || []).filter((i) => !hackathonId || i.hackathon_id === hackathonId);
  if (!list.length) return null;
  return (
    <Card>
      <CardHeader
        title="Team invitations"
        subtitle="Confirm with the code from your email to join a team."
        action={<MailCheck className="size-5 text-muted" aria-hidden />}
      />
      <ul className="divide-y divide-line">
        {list.map((inv) => (
          <InvitationRow
            key={inv.team_id}
            inv={inv}
            onDone={(kind) => {
              reload();
              onChange?.(kind);
            }}
          />
        ))}
      </ul>
    </Card>
  );
}
