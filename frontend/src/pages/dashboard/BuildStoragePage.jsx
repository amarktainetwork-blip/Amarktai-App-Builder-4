import { useEffect, useState } from "react";
import { Archive, Database, FolderOpen, Github, RefreshCw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/amk-api";

const STATUS_COLORS = {
  cloned: "text-blue-400",
  building: "text-yellow-400",
  built: "text-green-400",
  incomplete: "text-orange-400",
  failed: "text-red-400",
  audited: "text-purple-400",
  repaired: "text-cyan-400",
  release_ready: "text-emerald-400",
  deployed: "text-green-300",
  archived: "text-amk-fg3",
  pending: "text-amk-fg3",
};

const TYPE_LABELS = {
  repos: "Imported Repo",
  generated: "Generated App",
  incomplete: "Incomplete",
  releases: "Release-Ready",
  release: "Release-Ready",
  repo: "Imported Repo",
};

const FILTER_OPTIONS = [
  { value: "", label: "All builds" },
  { value: "repos", label: "Imported repos" },
  { value: "generated", label: "Generated apps" },
  { value: "incomplete", label: "Incomplete" },
  { value: "releases", label: "Release-ready" },
];

function StorageBar({ usageMb, label }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[10px] text-amk-fg3 w-24 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-amk-surface rounded-full overflow-hidden">
        <div
          className="h-full bg-amk-accent rounded-full"
          style={{ width: `${Math.min(100, usageMb)}%` }}
        />
      </div>
      <span className="font-mono text-[10px] text-amk-fg2 w-16 text-right">{usageMb.toFixed(1)} MB</span>
    </div>
  );
}

function BuildCard({ workspace, onArchive }) {
  const statusColor = STATUS_COLORS[workspace.build_status] || "text-amk-fg3";
  const typeLabel = TYPE_LABELS[workspace.workspace_type] || workspace.workspace_type;

  return (
    <div className="border border-amk-line bg-amk-panel p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 border border-amk-line px-1.5 py-0.5">
              {typeLabel}
            </span>
            <span className={`font-mono text-[10px] uppercase tracking-wider ${statusColor}`}>
              {workspace.build_status}
            </span>
          </div>
          <div className="mt-1.5 font-mono text-sm font-semibold text-white truncate">
            {workspace.github_repo
              ? `${workspace.github_owner}/${workspace.github_repo}`
              : workspace.project_id}
          </div>
          {workspace.branch && (
            <div className="mt-0.5 font-mono text-[10px] text-amk-fg3">
              branch: {workspace.branch}
              {workspace.commit_sha && ` @ ${workspace.commit_sha.slice(0, 7)}`}
            </div>
          )}
        </div>
        <button
          onClick={() => onArchive(workspace)}
          title="Archive workspace"
          className="shrink-0 p-1.5 border border-amk-line text-amk-fg3 hover:text-white hover:bg-amk-surface"
        >
          <Archive className="h-3.5 w-3.5" />
        </button>
      </div>

      {workspace.detected_stack && Object.keys(workspace.detected_stack).length > 0 && (
        <div className="flex flex-wrap gap-1">
          {workspace.detected_stack.has_react && (
            <span className="font-mono text-[9px] bg-blue-900/30 border border-blue-800/50 text-blue-300 px-1.5 py-0.5">React</span>
          )}
          {workspace.detected_stack.has_next && (
            <span className="font-mono text-[9px] bg-gray-900/30 border border-gray-700/50 text-gray-300 px-1.5 py-0.5">Next.js</span>
          )}
          {workspace.detected_stack.has_vite && (
            <span className="font-mono text-[9px] bg-purple-900/30 border border-purple-800/50 text-purple-300 px-1.5 py-0.5">Vite</span>
          )}
          {workspace.detected_stack.has_fastapi && (
            <span className="font-mono text-[9px] bg-green-900/30 border border-green-800/50 text-green-300 px-1.5 py-0.5">FastAPI</span>
          )}
          {workspace.detected_stack.has_dockerfile && (
            <span className="font-mono text-[9px] bg-cyan-900/30 border border-cyan-800/50 text-cyan-300 px-1.5 py-0.5">Docker</span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
        {workspace.last_audit_status && (
          <div className="font-mono text-[10px] text-amk-fg3">
            Audit: <span className="text-amk-fg2">{workspace.last_audit_status}</span>
          </div>
        )}
        {workspace.last_deploy_status && (
          <div className="font-mono text-[10px] text-amk-fg3">
            Deploy: <span className="text-amk-fg2">{workspace.last_deploy_status}</span>
          </div>
        )}
        {workspace.github_pr_url && (
          <div className="col-span-2 font-mono text-[10px] truncate">
            <a
              href={workspace.github_pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-amk-accent hover:underline"
            >
              View PR →
            </a>
          </div>
        )}
      </div>

      <div className="border-t border-amk-line pt-2 font-mono text-[9px] text-amk-fg3 truncate">
        {workspace.local_path}
      </div>

      {workspace.updated_at && (
        <div className="font-mono text-[9px] text-amk-fg3">
          Updated {new Date(workspace.updated_at).toLocaleString()}
        </div>
      )}
    </div>
  );
}

export default function BuildStoragePage() {
  const [workspaces, setWorkspaces] = useState([]);
  const [storage, setStorage] = useState(null);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [archiving, setArchiving] = useState(null);

  const fetchBuilds = async (type = "") => {
    setLoading(true);
    try {
      const params = type ? { workspace_type: type } : {};
      const { data } = await api.get("/builds", { params });
      setWorkspaces(data.workspaces || []);
      setStorage(data.storage || null);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to load builds");
      setWorkspaces([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBuilds(filter);
  }, [filter]);

  const handleArchive = async (workspace) => {
    if (!window.confirm(`Archive workspace for ${workspace.project_id}? It will be moved to the archived folder.`)) return;
    setArchiving(workspace.local_path);
    try {
      await api.post("/builds/archive", {
        workspace_path: workspace.local_path,
        confirmed: true,
      });
      toast.success("Workspace archived.");
      fetchBuilds(filter);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Archive failed");
    } finally {
      setArchiving(null);
    }
  };

  const filtered = workspaces.filter((ws) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      ws.project_id?.toLowerCase().includes(q) ||
      ws.github_repo?.toLowerCase().includes(q) ||
      ws.github_owner?.toLowerCase().includes(q) ||
      ws.branch?.toLowerCase().includes(q) ||
      ws.build_status?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border border-amk-line bg-amk-panel">
        <div className="border-b border-amk-line p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">Build Storage</div>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-white">
            GitHub Builds Workbench
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-amk-fg2">
            All imported repos and generated apps saved to the VPS. Continue half-built work,
            run audits, push to GitHub, and create PRs from one place.
          </p>
        </div>

        {/* Storage summary */}
        {storage && (
          <div className="p-5 border-b border-amk-line">
            <div className="flex items-center gap-2 mb-3">
              <Database className="h-4 w-4 text-amk-fg3" />
              <span className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">
                Storage: {storage.root}
              </span>
              <span className="ml-auto font-mono text-xs text-amk-fg2">
                {storage.total_mb} MB total
              </span>
            </div>
            <div className="space-y-1.5">
              {Object.entries(storage.per_type || {}).map(([type, info]) => (
                <StorageBar key={type} label={type} usageMb={info.mb || 0} />
              ))}
            </div>
          </div>
        )}

        {/* Filters and search */}
        <div className="p-4 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 border border-amk-line bg-amk-surface px-2">
            <Search className="h-3.5 w-3.5 text-amk-fg3" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search builds..."
              className="bg-transparent font-mono text-xs text-white placeholder-amk-fg3 outline-none py-1.5 px-1 w-48"
            />
          </div>

          <div className="flex gap-1 flex-wrap">
            {FILTER_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setFilter(opt.value)}
                className={`font-mono text-[10px] uppercase tracking-wider px-2.5 py-1.5 border transition ${
                  filter === opt.value
                    ? "border-amk-accent bg-amk-accent/10 text-amk-accent"
                    : "border-amk-line text-amk-fg3 hover:border-amk-line/70 hover:text-white"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <button
            onClick={() => fetchBuilds(filter)}
            disabled={loading}
            className="ml-auto flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider px-3 py-1.5 border border-amk-line text-amk-fg3 hover:text-white hover:bg-amk-surface disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Empty state */}
      {!loading && filtered.length === 0 && (
        <div className="border border-amk-line bg-amk-panel p-10 text-center">
          <FolderOpen className="h-10 w-10 text-amk-fg3 mx-auto mb-3" />
          <div className="font-mono text-sm text-amk-fg3">
            {workspaces.length === 0
              ? "No builds saved yet. Import a GitHub repo from the Repo Workbench."
              : "No builds match your search."}
          </div>
          {workspaces.length === 0 && (
            <a
              href="/dashboard/repo"
              className="mt-4 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-amk-accent hover:underline"
            >
              <Github className="h-3.5 w-3.5" /> Go to Repo Workbench
            </a>
          )}
        </div>
      )}

      {/* Build grid */}
      {filtered.length > 0 && (
        <div>
          <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg3">
            {filtered.length} workspace{filtered.length !== 1 ? "s" : ""}
            {search && ` matching "${search}"`}
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {filtered.map((ws) => (
              <BuildCard
                key={ws.local_path || ws.project_id}
                workspace={ws}
                onArchive={handleArchive}
                archiving={archiving === ws.local_path}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
