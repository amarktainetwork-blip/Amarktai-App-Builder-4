import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Activity, Boxes, Github, Image, LayoutDashboard, LogOut, Plus, Settings, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

const NAV = [
  { to: "/dashboard", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/dashboard/new", label: "New Build", icon: Plus },
  { to: "/dashboard/projects", label: "Projects", icon: Boxes },
  { to: "/dashboard/repo", label: "Repo Workbench", icon: Github },
  { to: "/dashboard/media", label: "Media", icon: Image },
  { to: "/dashboard/settings", label: "Settings", icon: Settings },
  { to: "/system", label: "System", icon: Activity },
];

export default function DashboardShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-amk-base text-amk-fg">
      <header className="sticky top-0 z-50 border-b border-amk-line bg-amk-base/95 backdrop-blur">
        <div className="flex min-h-14 items-center justify-between gap-3 px-4 lg:px-6">
          <Link to="/dashboard" className="flex min-w-0 items-center gap-2.5">
            <div className="grid h-8 w-8 shrink-0 place-items-center border border-amk-line bg-amk-panel">
              <span className="font-mono text-sm font-bold">A</span>
            </div>
            <div className="min-w-0">
              <div className="truncate font-display text-sm font-semibold tracking-tight text-white">Amarktai App Builder</div>
              <div className="hidden font-mono text-[9px] uppercase tracking-[0.2em] text-amk-fg3 sm:block">Private beta command center</div>
            </div>
          </Link>

          <div className="hidden items-center gap-2 lg:flex">
            <button onClick={() => navigate("/dashboard/new")} className="inline-flex h-9 items-center gap-2 bg-amk-accent px-4 font-mono text-[10px] uppercase tracking-wider text-black hover:bg-emerald-300">
              <Sparkles className="h-3.5 w-3.5" /> Start build
            </button>
            <button data-testid="dashboard-logout-btn" onClick={logout} title={user?.email} className="inline-flex h-9 items-center gap-2 border border-amk-line px-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:bg-amk-surface hover:text-white">
              <LogOut className="h-3.5 w-3.5" /> Sign out
            </button>
          </div>
        </div>

        <nav data-testid="dashboard-top-nav" className="overflow-x-auto border-t border-amk-line px-3 lg:px-6">
          <div className="flex min-w-max items-center gap-1 py-2">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `inline-flex h-9 items-center gap-2 border px-3 font-mono text-[10px] uppercase tracking-wider transition ${
                    isActive
                      ? "border-amk-accent bg-amk-accent/10 text-amk-accent"
                      : "border-transparent text-amk-fg3 hover:border-amk-line hover:bg-amk-panel hover:text-white"
                  }`
                }
              >
                <Icon className="h-3.5 w-3.5" /> {label}
              </NavLink>
            ))}
            <button data-testid="dashboard-mobile-logout-btn" onClick={logout} className="inline-flex h-9 items-center gap-2 border border-transparent px-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:border-amk-line hover:bg-amk-panel hover:text-white lg:hidden">
              <LogOut className="h-3.5 w-3.5" /> Sign out
            </button>
          </div>
        </nav>
      </header>

      <main className="mx-auto w-full max-w-7xl px-4 py-6 lg:px-6">
        <Outlet />
      </main>
    </div>
  );
}
