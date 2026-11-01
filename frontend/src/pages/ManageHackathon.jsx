import { useState } from "react";
import { useParams } from "react-router-dom";
import HackathonForm from "../components/HackathonForm";
import { Card, ErrorBanner, PageHeader, Spinner, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fmtDate } from "../lib/format";
import { useApi } from "../lib/useApi";
import { PhaseChip } from "./Hackathons";
import Applicants from "./manage/Applicants";
import Corpus from "./manage/Corpus";
import Evaluation from "./manage/Evaluation";
import Overview from "./manage/Overview";
import Teams from "./manage/Teams";

export default function ManageHackathon() {
  const { id } = useParams();
  const { user } = useAuth();
  const { data: h, error, loading, setData } = useApi(`/hackathons/${id}`);
  const organizer = user.role === "organizer";
  const [tab, setTab] = useState("overview");
  if (loading) return <Spinner />;
  if (error) return <ErrorBanner>{error}</ErrorBanner>;

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "applicants", label: "Applicants" },
    { id: "teams", label: "Teams" },
    { id: "evaluation", label: "Evaluation" },
    { id: "corpus", label: "Plagiarism corpus" },
    ...(organizer ? [{ id: "settings", label: "Settings" }] : []),
  ];

  return (
    <>
      <PageHeader
        eyebrow={h.theme}
        title={h.event_name}
        subtitle={`${fmtDate(h.start_date)} – ${fmtDate(h.end_date)} · shortlist at ${h.shortlist_threshold}+ · teams of ${h.max_team_size}`}
        action={<PhaseChip phase={h.phase} />}
      />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" && <Overview hackathon={h} />}
      {tab === "applicants" && <Applicants hackathon={h} canEdit={organizer} />}
      {tab === "teams" && <Teams hackathon={h} canEdit={organizer} />}
      {tab === "evaluation" && <Evaluation hackathon={h} canScan={organizer} />}
      {tab === "corpus" && <Corpus hackathon={h} canEdit={organizer} />}
      {tab === "settings" && (
        <Card className="p-5">
          <HackathonForm
            initial={h}
            submitLabel="Save changes"
            onSubmit={async (body) => setData(await api(`/hackathons/${id}`, { method: "PATCH", body }))}
          />
        </Card>
      )}
    </>
  );
}
