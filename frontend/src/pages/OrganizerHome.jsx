import { Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, Card, Empty, ErrorBanner, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../lib/useApi";
import { HackathonCard } from "./Hackathons";

export default function OrganizerHome() {
  const { data, error, loading } = useApi("/hackathons/mine");
  const newButton = (
    <Link to="/organizer/new">
      <Button>
        <Plus className="size-4" aria-hidden /> Create hackathon
      </Button>
    </Link>
  );
  return (
    <>
      <PageHeader title="My hackathons" subtitle="Shortlist applicants, form teams, and review originality reports." action={newButton} />
      <ErrorBanner>{error}</ErrorBanner>
      {loading ? (
        <Spinner />
      ) : !data?.length ? (
        <Card>
          <Empty title="You haven't created a hackathon yet" action={newButton}>
            Define the skills you need and VERIQO will score every applicant's resume and GitHub profile against them.
          </Empty>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((h) => (
            <HackathonCard key={h.id} h={h} href={`/manage/${h.id}`} cta="Manage" />
          ))}
        </div>
      )}
    </>
  );
}
