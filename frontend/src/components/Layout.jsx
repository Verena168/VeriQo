import { BarChart3, Code2, LayoutGrid, LogOut, Plug, ShieldCheck } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import ThemeToggle from "./ThemeToggle";

const NAV = {
  participant: [
    { to: "/hackathons", label: "Hackathons", icon: LayoutGrid },
    { to: "/year-in-code", label: "Year in Code", icon: BarChart3 },
    { to: "/extension", label: "VS Code extension", icon: Plug },
  ],
  organizer: [
    { to: "/organizer", label: "My hackathons", icon: ShieldCheck },
    { to: "/hackathons", label: "All hackathons", icon: LayoutGrid },
  ],
  judge: [{ to: "/hackathons", label: "Hackathons", icon: LayoutGrid }],
};

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
          <NavLink to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="grid size-7 place-items-center rounded-lg bg-accent text-white">
              <Code2 className="size-4" aria-hidden />
            </span>
            VERIQO
          </NavLink>
          <nav className="flex flex-1 gap-1 overflow-x-auto">
            {(NAV[user.role] || []).map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    isActive ? "bg-surface-2 text-ink" : "text-ink-2 hover:text-ink"
                  }`
                }
              >
                <Icon className="size-4" aria-hidden />
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <div className="hidden text-right text-sm leading-tight md:block">
              <div className="font-medium">{user.name}</div>
              <div className="text-xs capitalize text-muted">{user.role}</div>
            </div>
            <button
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="rounded-lg p-2 text-ink-2 hover:bg-surface-2"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="size-4" />
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
