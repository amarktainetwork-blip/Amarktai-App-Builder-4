import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Activity, Boxes, Database, Github, Image, LayoutDashboard, Lightbulb, LogOut, Plus, Settings, ShieldCheck, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

const GROUPS = [
  ["Create", [
    { to: "/dashboard", label: "Overview", icon: LayoutDashboard, end: true },
    { to: "/dashboard/new", label: "New Build", icon: Plus },
    { to: "/dashboard/idea-builder", label: "Idea Builder", icon: Lightbulb },
  ]],
  ["Workspaces", [
    { to: "/dashboard/projects", label: "Projects", icon: Boxes },
    { to: "/dashboard/builds", label: "Build Storage", icon: Database },
    { to: "/dashboard/media", label: "Media", icon: Image },
  ]],
  ["Engineering", [
    { to: "/dashboard/repo", label: "Repo Workbench", icon: Github },
    { to: "/system", label: "Runtime QA", icon: Activity },
    { to: "/system", label: "Final Gate", icon: ShieldCheck },
  ]],
  ["Control", [
    { to: "/dashboard/settings", label: "Capability Center", icon: ShieldCheck },
    { to: "/dashboard/settings", label: "Settings", icon: Settings },
  ]],
];

export default function DashboardShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const flatNav = GROUPS.flatMap(([, items]) => items);

  return (
    <div className="command-shell min-h-screen text-amk-fg">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-72 border-r border-amk-line bg-[#030712]/88 p-4 backdrop-blur-2xl lg:flex lg:flex-col">
        <Link to="/dashboard" className="glass-panel rounded-3xl p-4">
          <div className="font-display text-lg font-semibold text-white">Amarktai Command Center</div>
          <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.22em] text-amk-accent">Amarktai App Builder</div>
        </Link>
        <div className="mt-5 flex-1 space-y-5 overflow-y-auto pr-1">
          {GROUPS.map(([group, items]) => (
            <nav key={group}>
              <div className="px-3 font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">{group}</div>
              <div className="mt-2 space-y-1">
                {items.map((item) => <SideLink key={item.to} item={item} />)}
              </div>
            </nav>
          ))}
        </div>
        <button data-testid="dashboard-logout-btn" onClick={logout} title={user?.email} className="mt-4 inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-amk-line bg-amk-panel/70 px-4 font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:border-amk-red hover:text-white">
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </aside>

      <div className="lg:pl-72">
        <header className="sticky top-0 z-30 border-b border-amk-line bg-[#030712]/78 backdrop-blur-2xl">
          <div className="flex min-h-16 items-center justify-between gap-3 px-4 lg:px-8">
            <div className="min-w-0">
              <div className="font-display text-lg font-semibold tracking-tight text-white">Amarktai Command Center</div>
              <div className="hidden font-mono text-[9px] uppercase tracking-[0.2em] text-amk-fg3 sm:block">Truth-gated AI software factory</div>
            </div>
            <div className="flex items-center gap-2">
              <span className="hidden rounded-full border border-amk-line bg-amk-panel/70 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-amk-fg3 md:inline-flex">
                Readiness unknown
              </span>
              <button onClick={() => navigate("/dashboard/new")} className="cta-primary inline-flex h-10 items-center gap-2 rounded-2xl px-4 font-mono text-[10px] uppercase tracking-wider">
                <Sparkles className="h-3.5 w-3.5" /> Start build
              </button>
              <button data-testid="dashboard-mobile-logout-btn" onClick={logout} className="inline-flex h-10 items-center gap-2 rounded-2xl border border-amk-line px-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:bg-amk-panel lg:hidden">
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <nav data-testid="dashboard-top-nav" className="overflow-x-auto border-t border-amk-line px-3 lg:hidden">
            <div className="flex min-w-max items-center gap-1 py-2">
              {flatNav.map((item) => <MobileLink key={item.to} item={item} />)}
            </div>
          </nav>
        </header>

        <main className="mx-auto w-full max-w-7xl px-4 py-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function SideLink({ item }) {
  const Icon = item.icon;
  return (
    <NavLink to={item.to} end={item.end} className={({ isActive }) =>
      `flex h-11 items-center gap-3 rounded-2xl border px-3 font-mono text-[11px] uppercase tracking-wider transition ${
        isActive
          ? "border-amk-accent bg-amk-accent/12 text-white shadow-[0_0_28px_rgba(34,211,238,.16)]"
          : "border-transparent text-amk-fg2 hover:border-amk-line hover:bg-amk-panel/70 hover:text-white"
      }`
    }>
      <Icon className="h-4 w-4" /> {item.label}
    </NavLink>
  );
}

function MobileLink({ item }) {
  const Icon = item.icon;
  return (
    <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) =>
      `inline-flex h-9 items-center gap-2 rounded-xl border px-3 font-mono text-[10px] uppercase tracking-wider transition ${
        isActive ? "border-amk-accent bg-amk-accent/12 text-amk-accent" : "border-transparent text-amk-fg3 hover:border-amk-line hover:bg-amk-panel hover:text-white"
      }`
    }>
      <Icon className="h-3.5 w-3.5" /> {item.label}
    </NavLink>
  );
}
