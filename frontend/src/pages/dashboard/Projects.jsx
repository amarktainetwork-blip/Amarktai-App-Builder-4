import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Trash2, ArrowRight, Github, Activity, Users, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { Projects } from "@/lib/amk-api";
import { useAuth } from "@/lib/auth-context";

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

export default function ProjectsPage() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = () =>
    Projects.list()
      .then(setProjects)
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));

  useEffect(() => {
    refresh();
  }, []);

  const remove = async (id) => {
    await Projects.remove(id);
    refresh();
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="p-6 lg:p-10 max-w-4xl"
    >
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-3">
        [ projects ]
      </div>

      <div className="flex items-baseline justify-between mb-8">
        <div>
          <h1 className="font-display font-semibold text-3xl tracking-tight">
            Projects
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => nav("/system")}
            className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white inline-flex items-center gap-1.5"
          >
            <Activity className="w-3 h-3" strokeWidth={1.5} /> health
          </button>
          {user?.role === "admin" && (
            <button
              onClick={() => nav("/admin/users")}
              className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white inline-flex items-center gap-1.5"
            >
              <Users className="w-3 h-3" strokeWidth={1.5} /> users
            </button>
          )}
          <span className="font-mono text-[11px] text-amk-fg3">
            {projects.length} total
          </span>
        </div>
      </div>

      {loading ? (
        <div className="font-mono text-xs text-amk-fg3 animate-pulse">
          loading...
        </div>
      ) : projects.length === 0 ? (
        <div
          data-testid="projects-empty"
          className="grid-bg border border-amk-line p-10 text-center"
        >
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
            <Plus className="w-3.5 h-3.5" strokeWidth={2} /> New Build
          </Link>
        </div>
      ) : (
        <ul className="space-y-2" data-testid="projects-list">
          {projects.map((p) => (
            <li
              key={p.id}
              data-testid={`project-row-${p.id}`}
              className="group border border-amk-line bg-amk-panel hover:bg-amk-surface transition-colors duration-150"
            >
              <div className="p-3 flex items-center gap-3">
                <button
                  onClick={() => nav(`/workspace/${p.id}`)}
                  className="flex-1 text-left min-w-0"
                >
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
                </button>
                <button
                  data-testid={`project-delete-${p.id}`}
                  onClick={() => remove(p.id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-amk-fg3 hover:text-agent-scout p-1"
                  aria-label="delete project"
                >
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                </button>
                <ArrowRight
                  className="w-4 h-4 text-amk-fg3 group-hover:text-white transition-colors"
                  strokeWidth={1.5}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </motion.div>
  );
}
