import { SimpleBars } from "../../components/charts";
import { Card, CardHeader, ErrorBanner, RiskBadge, Spinner, Stat } from "../../components/ui";
import { useApi } from "../../lib/useApi";

export default function Overview({ hackathon }) {
  const { data, error, loading } = useApi(`/analytics/hackathons/${hackathon.id}`);
  if (loading) return <Spinner />;
  if (error) return <ErrorBanner>{error}</ErrorBanner>;
  const s = data.by_status;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat label="Applications" value={data.applications} />
        <Stat label="Shortlisted" value={s.shortlisted || 0} sub={`${s.rejected || 0} not shortlisted`} />
        <Stat label="Needs review" value={s.needs_review || 0} sub="unreadable resumes" />
        <Stat label="Teams" value={data.teams} />
        <Stat label="Submissions" value={data.submissions} sub={`${data.scanned} scanned`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <CardHeader title="Applicant match scores" subtitle="Number of applicants per score band" />
          <div className="p-4">
            <SimpleBars data={data.score_histogram} x="bucket" y="count" name="Applicants" valueFormatter={(v) => `${v} applicant${v === 1 ? "" : "s"}`} />
          </div>
        </Card>
        <Card>
          <CardHeader title="Integrity results" subtitle="Submissions by risk band" />
          <ul className="divide-y divide-line">
            {["green", "amber", "red"].map((k) => (
              <li key={k} className="flex items-center justify-between px-5 py-3">
                <RiskBadge level={k} />
                <span className="tabular text-lg font-semibold">{data.risk[k]}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
