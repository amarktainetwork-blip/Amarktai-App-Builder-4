import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Plus, FolderOpen, ArrowRight, Github, GitBranch, Image, Settings } from "lucide-react";
import { Projects } from "@/lib/amk-api";

function StatusDot({ status }) {
  const colors = {
    running: "#FFC107",
    ready: "#00E676",
    failed: "#FF5722",
    queued: "#A1A1AA",
  };
  return (
    <span
      title={status}
      className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
      style={{ background: colors[status] || "#71717A" }}
    />
  );
}

export default function DashboardHome() {
  const nav = useNavigate();
  const [projects, setProjects] = useState([]);

  useEffect(() => {
    Projects.list()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, []);

  const recent = projects.slice(0, 5);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="p-6 lg:p-10 max-w-4xl"
    >
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-3">
        [ overview ]
      </div>
      <h1 className="font-display font-semibold text-3xl tracking-tight mb-2">
        Dashboard
      </h1>
      <p className="text-sm text-amk-fg2 mb-10 leading-relaxed">
        Welcome back. Start a new build or open a recent project.
      </p>

      {/* Quick-action cards */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-12">
        <QuickCard
          to="/dashboard/new"
          icon={<Plus className="w-4 h-4 text-amk-accent" strokeWidth={1.5} />}
          title="New Build"
          desc="Describe an app and launch AI coding agents."
          accent
        />
        <QuickCard
          to="/dashboard/projects"
          icon={<FolderOpen className="w-4 h-4 text-amk-fg2" strokeWidth={1.5} />}
          title="Projects"
          desc={`${projects.length} project${projects.length !== 1 ? "s" : ""} total.`}
        />
        <QuickCard
          to="/dashboard/repo"
          icon={<GitBranch className="w-4 h-4 text-amk-fg2" strokeWidth={1.5} />}
          title="Repo Workbench"
          desc="Import a GitHub repo for agents to analyse."
        />
        <QuickCard
          to="/dashboard/media"
          icon={<Image className="w-4 h-4 text-amk-fg2" strokeWidth={1.5} />}
          title="Media Library"
          desc="Manage uploaded assets and Pixabay images."
        />
        <QuickCard
          to="/dashboard/settings"
          icon={<Settings className="w-4 h-4 text-amk-fg2" strokeWidth={1.5} />}
          title="Settings"
          desc="Configure API keys, models, and GitHub PAT."
        />
      </div>

      {/* Recent projects */}
      {recent.length > 0 && (
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-3">
            [ recent builds ]
          </div>
          <ul className="space-y-2">
            {recent.map((p) => (
              <li key={p.id}>
                <button
                  onClick={() => nav(`/workspace/${p.id}`)}
                  className="w-full text-left border border-amk-line bg-amk-panel hover:bg-amk-surface transition-colors duration-150 p-3 flex items-center gap-3 group"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-mono text-sm text-white truncate">
                        {p.name}
                      </span>
                      {p.github && (
                        <Github
                          className="w-3 h-3 text-amk-fg3 shrink-0"
                          strokeWidth={1.5}
                        />
                      )}
                      <StatusDot status={p.status} />
                    </div>
                    <div className="font-mono text-[10px] text-amk-fg3 truncate">
                      {p.prompt}
                    </div>
                  </div>
                  <ArrowRight
                    className="w-4 h-4 text-amk-fg3 group-hover:text-white transition-colors shrink-0"
                    strokeWidth={1.5}
                  />
                </button>
              </li>
            ))}
          </ul>
          {projects.length > 5 && (
            <Link
              to="/dashboard/projects"
              className="mt-3 inline-flex items-center gap-1.5 font-mono text-[10px] text-amk-fg3 hover:text-white uppercase tracking-wider"
            >
              View all {projects.length} projects{" "}
              <ArrowRight className="w-3 h-3" strokeWidth={1.5} />
            </Link>
          )}
        </div>
      )}

      {projects.length === 0 && (
        <div className="grid-bg border border-amk-line p-10 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-amk-fg3 mb-2">
            [ empty ]
          </div>
          <p className="text-sm text-amk-fg2 mb-4">
            No projects yet. Describe an app or import a repo to get started.
          </p>
          <Link
            to="/dashboard/new"
            className="inline-flex items-center gap-2 px-4 h-9 bg-amk-accent text-black font-mono text-xs hover:bg-emerald-300 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" strokeWidth={2} /> Start first build
          </Link>
        </div>
      )}
    </motion.div>
  );
}

function QuickCard({ to, icon, title, desc, accent }) {
  return (
    <Link
      to={to}
      className={`border ${accent ? "border-amk-accent/40" : "border-amk-line"} bg-amk-panel hover:bg-amk-surface transition-colors p-5 flex items-start gap-3 group`}
    >
      <div
        className={`w-8 h-8 border ${accent ? "border-amk-accent/50" : "border-amk-line"} bg-amk-base grid place-items-center shrink-0 group-hover:border-amk-accent transition-colors`}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <div className="font-mono text-xs font-medium mb-1">{title}</div>
        <p className="text-[11px] text-amk-fg2 leading-relaxed">{desc}</p>
      </div>
    </Link>
  );
}
