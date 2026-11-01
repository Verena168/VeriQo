import { BadgeCheck, Plug } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ActivityHeatmap, RankedBars, SimpleBars, SimpleLine } from "../components/charts";
import { ApplicationBadge, Card, CardHeader, Chip, Empty, ErrorBanner, Notice, PageHeader, RiskBadge, Select, Spinner, Stat } from "../components/ui";
import { fmtDate, fmtNum, fmtRatio } from "../lib/format";
import { useApi } from "../lib/useApi";

const CATEGORY = {
  language: "Languages", frontend: "Frontend", backend: "Backend", mobile: "Mobile", database: "Databases",
  ml: "ML & AI", data: "Data", devops: "DevOps & Cloud", security: "Security", blockchain: "Blockchain",
  design: "Design", iot: "IoT", tools: "Tools",
};

export default function YearInCode() {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const { data, error, loading } = useApi(`/analytics/year-in-code?year=${year}`);

  return (
    <>
      <PageHeader
        eyebrow="Your developer profile"
        title={`${year} in Code`}
        subtitle="Coding activity verified by the VERIQO extension, plus your hackathon record."
        action={
          <div className="w-32">
            <Select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Year">
              {[thisYear, thisYear - 1, thisYear - 2].map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </Select>
          </div>
        }
      />
      <ErrorBanner>{error}</ErrorBanner>
      {loading || !data ? (
        <Spinner />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Active coding" value={`${data.totals.active_hours} h`} sub={`${data.totals.active_days} active days · ${data.totals.sessions} sessions`} />
            <Stat label="Longest streak" value={`${data.totals.longest_streak_days} days`} />
            <Stat label="Typed by hand" value={fmtRatio(data.totals.typed_share)} sub={`${fmtNum(data.totals.typed_chars)} characters typed`} />
            <Stat
              label="Hackathons"
              value={data.totals.hackathons}
              sub={`${data.totals.shortlisted} shortlisted · ${data.totals.verified_projects} verified project${data.totals.verified_projects === 1 ? "" : "s"}`}
            />
          </div>

          {data.daily.length === 0 && (
            <Notice icon={Plug}>
              No coding activity recorded for {year} yet.{" "}
              <Link to="/extension" className="font-medium text-accent hover:underline">
                Install the VS Code extension
              </Link>{" "}
              and track your next hackathon.
            </Notice>
          )}

          <Card>
            <CardHeader title="Daily activity" subtitle="Active coding minutes per day" />
            <div className="p-5">
              <ActivityHeatmap year={year} daily={data.daily} />
            </div>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Active hours per month" />
              <div className="p-4">
                {data.monthly.length ? (
                  <SimpleLine data={data.monthly} x="month" y="active_hours" name="Active hours" valueFormatter={(v) => `${v} h`} />
                ) : (
                  <Empty title="No data yet" />
                )}
              </div>
            </Card>
            <Card>
              <CardHeader title="When you code" subtitle="Active minutes by hour of day" />
              <div className="p-4">
                {data.hours.length ? (
                  <SimpleBars data={data.hours} x="hour" y="active_minutes" name="Active minutes" xFormatter={(h) => `${String(h).padStart(2, "0")}:00`} valueFormatter={(v) => `${v} min`} />
                ) : (
                  <Empty title="No data yet" />
                )}
              </div>
            </Card>
            <Card>
              <CardHeader title="Languages" subtitle="Characters typed per language" />
              <div className="p-4">
                {data.languages.length ? (
                  <RankedBars data={data.languages} label="language" value="chars" name="Characters" valueFormatter={(v) => `${fmtNum(v)} chars`} />
                ) : (
                  <Empty title="No data yet" />
                )}
              </div>
            </Card>
            <Card>
              <CardHeader title="Skills" subtitle="Extracted from your resume and GitHub profile" />
              <div className="space-y-4 p-5">
                {data.skill_categories.length ? (
                  <>
                    <RankedBars
                      data={data.skill_categories.map((c) => ({ ...c, label: CATEGORY[c.category] || c.category }))}
                      label="label"
                      value="count"
                      name="Skills"
                    />
                    <div className="flex flex-wrap gap-1.5">
                      {data.skills.map((s) => (
                        <Chip key={s.name} tone={s.sources?.includes("github") ? "accent" : "neutral"} title={s.sources?.includes("github") ? "Seen in your GitHub repos" : "From your resume"}>
                          {s.sources?.includes("github") && <BadgeCheck className="size-3" aria-hidden />}
                          {s.name}
                        </Chip>
                      ))}
                    </div>
                  </>
                ) : (
                  <Empty title="No skills yet">Apply to a hackathon with your resume to build your skill profile.</Empty>
                )}
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title="Hackathon history" />
            {!data.hackathons.length ? (
              <Empty title={`No hackathons in ${year}`} />
            ) : (
              <ul className="divide-y divide-line">
                {data.hackathons.map((h) => (
                  <li key={h.hackathon_id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                    <div>
                      <Link to={`/hackathons/${h.hackathon_id}`} className="font-medium hover:underline">
                        {h.event_name}
                      </Link>
                      <div className="text-sm text-ink-2">
                        {fmtDate(h.start_date)}
                        {h.team_name && ` · ${h.team_name}`}
                        {h.project_title && ` · ${h.project_title}`}
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <ApplicationBadge status={h.application_status} />
                      {h.project_title && <RiskBadge level={h.risk_level} />}
                      {h.verified && (
                        <Chip tone="accent">
                          <BadgeCheck className="size-3.5" aria-hidden /> Verified
                        </Chip>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
