import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  Plus,
  FolderOpen,
  GitBranch,
  Image,
  Settings,
  Menu,
  X,
  LogOut,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";

const NAV_ITEMS = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Overview", end: true },
  { to: "/dashboard/new", icon: Plus, label: "New Build" },
  { to: "/dashboard/projects", icon: FolderOpen, label: "Projects" },
  { to: "/dashboard/repo", icon: GitBranch, label: "Repo Workbench" },
  { to: "/dashboard/media", icon: Image, label: "Media Library" },
  { to: "/dashboard/settings", icon: Settings, label: "Settings" },
];

export default function DashboardLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex bg-amk-base text-amk-fg">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col w-56 border-r border-amk-line bg-amk-panel shrink-0 sticky top-0 h-screen">
        <SidebarContent user={user} onLogout={handleLogout} />
      </aside>

      {/* Mobile hamburger button */}
      <button
        onClick={() => setDrawerOpen(true)}
        className="lg:hidden fixed top-3 left-3 z-50 p-2 border border-amk-line bg-amk-panel text-amk-fg2 hover:text-white"
        aria-label="Open navigation"
      >
        <Menu className="w-4 h-4" />
      </button>

      {/* Mobile slide-in drawer */}
      <AnimatePresence>
        {drawerOpen && (
          <>
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="lg:hidden fixed inset-0 bg-black/60 z-40"
              onClick={() => setDrawerOpen(false)}
            />
            <motion.aside
              key="drawer"
              initial={{ x: -224 }}
              animate={{ x: 0 }}
              exit={{ x: -224 }}
              transition={{ type: "tween", duration: 0.22 }}
              className="lg:hidden fixed top-0 left-0 bottom-0 w-56 z-50 border-r border-amk-line bg-amk-panel flex flex-col"
            >
              <button
                onClick={() => setDrawerOpen(false)}
                className="absolute top-3 right-3 p-1 text-amk-fg3 hover:text-white"
                aria-label="Close navigation"
              >
                <X className="w-4 h-4" />
              </button>
              <SidebarContent
                user={user}
                onLogout={handleLogout}
                onNavClick={() => setDrawerOpen(false)}
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-amk-line flex items-center px-4 lg:px-6 bg-amk-base/90 backdrop-blur-md sticky top-0 z-30">
          <Link
            to="/"
            className="flex items-center gap-2 group ml-10 lg:ml-0"
          >
            <div className="w-7 h-7 grid place-items-center border border-amk-line bg-amk-panel">
              <span className="font-mono text-[13px] font-bold tracking-tight">
                A
              </span>
            </div>
            <span className="font-display font-semibold text-sm tracking-tight text-amk-fg group-hover:text-white">
              Amarktai <span className="text-amk-accent">App Builder</span>
            </span>
            <span className="font-mono text-[10px] text-amk-fg3 uppercase tracking-[0.18em] hidden sm:inline">
              // Amarktai Network
            </span>
          </Link>
        </header>
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function SidebarContent({ user, onLogout, onNavClick }) {
  return (
    <>
      <div className="h-14 flex items-center px-4 border-b border-amk-line shrink-0">
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-amk-fg3">
          [ dashboard ]
        </span>
      </div>

      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavClick}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 font-mono text-xs transition-colors duration-100 border-l-2 ${
                isActive
                  ? "bg-amk-surface text-white border-amk-accent"
                  : "text-amk-fg2 hover:text-white hover:bg-amk-surface border-transparent"
              }`
            }
          >
            <Icon className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-amk-line p-3 shrink-0">
        {user && (
          <div className="font-mono text-[10px] text-amk-fg3 truncate mb-2">
            {user.email}
          </div>
        )}
        <button
          onClick={onLogout}
          className="flex items-center gap-2 font-mono text-[10px] text-amk-fg3 hover:text-white uppercase tracking-wider"
        >
          <LogOut className="w-3 h-3" strokeWidth={1.5} />
          Sign out
        </button>
      </div>
    </>
  );
}
