import { useNavigate } from "react-router-dom";
import HackathonForm from "../components/HackathonForm";
import { PageHeader } from "../components/ui";
import { api } from "../lib/api";

export default function CreateHackathon() {
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Create hackathon" subtitle="Applicants will be matched against the skills you list." />
      <HackathonForm
        submitLabel="Create hackathon"
        onSubmit={async (body) => {
          const h = await api("/hackathons", { method: "POST", body });
          navigate(`/manage/${h.id}`);
        }}
      />
    </div>
  );
}
