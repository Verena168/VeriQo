import { CalendarDays, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, Card, Chip, Empty, ErrorBanner, PageHeader, Spinner } from "../components/ui";
import { useAuth } from "../lib/auth";
import { fmtDate } from "../lib/format";
import { useApi } from "../lib/useApi";

export function PhaseChip({ phase }) {
  const label = { upcoming: "Upcoming", live: "Live now", ended: "Ended" }[phase] || phase;
  return (
    <Chip tone={phase === "live" ? "accent" : "neutral"}>
      {phase === "live" && <span className="size-1.5 rounded-full bg-accent" aria-hidden />}
      {label}
    </Chip>
  );
}

export function HackathonCard({ h, href, cta }) {
  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{h.event_name}</h3>
          {h.theme && <p className="text-sm text-ink-2">{h.theme}</p>}
        </div>
        <PhaseChip phase={h.phase} />
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-sm text-ink-2">
        <CalendarDays className="size-4" aria-hidden />
        {fmtDate(h.start_date)} – {fmtDate(h.end_date)}
      </div>
      {h.description && <p className="mt-3 line-clamp-2 text-sm text-ink-2">{h.description}</p>}
      <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
        <Chip tone="accent">{h.participation_mode === "solo" ? "Solo" : `Teams up to ${h.max_team_size}`}</Chip>
        {h.student_only && <Chip tone="accent">Students only</Chip>}
        <Chip tone="accent">{Number(h.fee_amount) > 0 ? `₹${Number(h.fee_amount).toLocaleString()} fee` : "Free"}</Chip>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {h.requirements.slice(0, 6).map((r) => (
          <Chip key={r.id}>{r.skill}</Chip>
        ))}
        {h.requirements.length > 6 && <Chip>+{h.requirements.length - 6}</Chip>}
      </div>
      <div className="mt-auto pt-5">
        <Link to={href}>
          <Button variant="secondary" className="w-full">
            {cta}
          </Button>
        </Link>
      </div>
    </Card>
  );
}

export default function Hackathons() {
  const { user } = useAuth();
  const { data, error, loading } = useApi("/hackathons");
  const staff = user.role !== "participant";

  return (
    <>
      <PageHeader
        title="Hackathons"
        subtitle={staff ? "Every event on the platform." : "Apply with your resume; VERIQO matches your skills to each event."}
        action={
          user.role === "organizer" && (
            <Link to="/organizer/new">
              <Button>
                <Plus className="size-4" aria-hidden /> Create hackathon
              </Button>
            </Link>
          )
        }
      />
      <ErrorBanner>{error}</ErrorBanner>
      {loading ? (
        <Spinner />
      ) : !data?.length ? (
        <Card>
          <Empty title="No hackathons yet">Organizers can create one from their dashboard.</Empty>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((h) => {
            const own = user.role === "judge" || (user.role === "organizer" && h.organizer_id === user.id);
            return (
              <HackathonCard
                key={h.id}
                h={h}
                href={staff ? (own ? `/manage/${h.id}` : `/hackathons/${h.id}`) : `/hackathons/${h.id}`}
                cta={staff ? (own ? (user.role === "judge" ? "Evaluate" : "Manage") : "View") : "View & apply"}
              />
            );
          })}
        </div>
      )}
    </>
  );
}
