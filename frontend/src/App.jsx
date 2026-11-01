import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import { useAuth } from "./lib/auth";
import CreateHackathon from "./pages/CreateHackathon";
import ExtensionSetup from "./pages/ExtensionSetup";
import HackathonDetail from "./pages/HackathonDetail";
import Hackathons from "./pages/Hackathons";
import Login from "./pages/Login";
import ManageHackathon from "./pages/ManageHackathon";
import OrganizerHome from "./pages/OrganizerHome";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import ReportPage from "./pages/ReportPage";
import TeamRegistration from "./pages/TeamRegistration";
import YearInCode from "./pages/YearInCode";

function Protected({ roles, children }) {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
}

function Home() {
  const { user } = useAuth();
  return <Navigate to={user.role === "organizer" ? "/organizer" : "/hackathons"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<Home />} />
        <Route path="hackathons" element={<Hackathons />} />
        <Route path="hackathons/:id" element={<HackathonDetail />} />
        <Route path="hackathons/:id/register" element={<Protected roles={["participant"]}><TeamRegistration /></Protected>} />
        <Route path="profile" element={<Profile />} />
        <Route path="year-in-code" element={<Protected roles={["participant"]}><YearInCode /></Protected>} />
        <Route path="extension" element={<Protected roles={["participant"]}><ExtensionSetup /></Protected>} />
        <Route path="organizer" element={<Protected roles={["organizer"]}><OrganizerHome /></Protected>} />
        <Route path="organizer/new" element={<Protected roles={["organizer"]}><CreateHackathon /></Protected>} />
        <Route path="manage/:id" element={<Protected roles={["organizer", "judge"]}><ManageHackathon /></Protected>} />
        <Route path="reports/:id" element={<Protected roles={["organizer", "judge"]}><ReportPage /></Protected>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
