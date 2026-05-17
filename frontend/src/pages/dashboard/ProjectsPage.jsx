import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Github, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Projects } from "@/lib/amk-api";

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    Projects.list().then(setProjects).catch(() => setProjects([])).finally(() => setLoading(false));
  };

  useEffect(() => { refresh(); }, []);

  const remove = async (project) => {
    if (!window.confirm(`Delete "${project.name}"?`)) return;
    try {
      await Projects.remove(project.id);
      toast.success("Project deleted.");
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  return (
    <section className="border border-amk-line bg-amk-panel">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-amk-line p-5">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">Projects</div>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-white">Build history and workspaces</h1>
        </div>
        <Link to="/dashboard/new" className="inline-flex h-10 items-center gap-2 bg-amk-accent px-4 font-mono text-xs uppercase tracking-wider text-black hover:bg-emerald-300">
          New build <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-8 font-mono text-xs text-amk-fg3">Loading projects...</div>
        ) : projects.length === 0 ? (
          <div data-testid="projects-empty" className="p-10 text-center">
            <p className="text-sm text-amk-fg2">No projects yet. Start a build or import a repo.</p>
          </div>
        ) : (
          <table className="w-full min-w-[720px] text-left" data-testid="projects-list">
            <thead className="border-b border-amk-line bg-amk-base font-mono text-[10px] uppercase tracking-wider text-amk-fg3">
              <tr>
                <th className="px-4 py-3">Project</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Mode</th>
                <th className="px-4 py-3">Updated</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.id} data-testid={`project-row-${project.id}`} className="border-b border-amk-line bg-amk-panel hover:bg-amk-surface">
                  <td className="max-w-[360px] px-4 py-3">
                    <button onClick={() => navigate(`/workspace/${project.id}`)} className="block w-full text-left">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-mono text-sm text-white">{project.name}</span>
                        {project.github && <Github className="h-3.5 w-3.5 shrink-0 text-amk-fg3" />}
                      </div>
                      <div className="mt-1 truncate font-mono text-[10px] text-amk-fg3">{project.prompt}</div>
                    </button>
                  </td>
                  <td className="px-4 py-3"><StatusPill status={project.status} /></td>
                  <td className="px-4 py-3 font-mono text-xs text-amk-fg2">{(project.mode || "web_app").replace(/_/g, " ")}</td>
                  <td className="px-4 py-3 font-mono text-xs text-amk-fg3">{formatDate(project.updated_at || project.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => navigate(`/workspace/${project.id}`)} className="inline-flex h-8 items-center gap-1.5 border border-amk-line px-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:bg-amk-base hover:text-white">
                        Open <ArrowRight className="h-3 w-3" />
                      </button>
                      <button data-testid={`project-delete-${project.id}`} onClick={() => remove(project)} className="inline-flex h-8 items-center gap-1.5 border border-amk-line px-2 font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:border-red-800 hover:bg-red-950/30 hover:text-red-300">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function StatusPill({ status = "queued" }) {
  const color = { running: "#FFC107", ready: "#00E676", ready_with_warnings: "#FFC107", failed: "#FF5722", cancelled: "#FF5722", queued: "#A1A1AA" }[status] || "#A1A1AA";
  return <span className="inline-flex border border-amk-line px-2 py-1 font-mono text-[10px] uppercase tracking-wider" style={{ color }}>{status}</span>;
}

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleDateString();
  } catch {
    return "-";
  }
}
