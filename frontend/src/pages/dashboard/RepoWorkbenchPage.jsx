import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GitBranch, Github, LockKeyhole, RefreshCw, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Builds, Projects, Settings, System } from "@/lib/amk-api";

export default function RepoWorkbenchPage() {
  const navigate = useNavigate();
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState({});
  const [capabilities, setCapabilities] = useState(null);
  const [repos, setRepos] = useState([]);
  const [repoSearch, setRepoSearch] = useState("");
  const [selectedRepo, setSelectedRepo] = useState(null);
  const [branches, setBranches] = useState([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [loadingBranches, setLoadingBranches] = useState(false);

  useEffect(() => {
    Settings.get().then(setSettings).catch(() => setSettings({}));
    System.capabilitiesStatus().then(setCapabilities).catch(() => setCapabilities(null));
  }, []);

  const githubCap = capabilities?.summary?.github_integration;
  const githubConfigured = !!settings.GITHUB_PAT?.configured || !!githubCap?.configured;
  const githubLive = githubCap?.live_status === "live_ok" || githubCap?.live_status === "key_present_live_ok";
  const githubLabel = githubLive ? "Available" : githubConfigured ? "Configured" : "Missing";

  const filteredRepos = useMemo(() => {
    const q = repoSearch.trim().toLowerCase();
    if (!q) return repos;
    return repos.filter((repo) =>
      repo.full_name?.toLowerCase().includes(q) ||
      repo.description?.toLowerCase().includes(q)
    );
  }, [repos, repoSearch]);

  const importRepo = async (e) => {
    e.preventDefault();
    if (!repoUrl.trim()) {
      toast.error("Repo URL is required.");
      return;
    }
    setBusy(true);
    try {
      const project = await Projects.fromRepo(repoUrl.trim(), branch.trim() || null, null);
      toast.success(`Imported ${project.name}`);
      navigate(`/workspace/${project.id}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const loadRepos = async () => {
    setLoadingRepos(true);
    try {
      const result = await System.githubRepos({ visibility: "all", per_page: 100 });
      if (!result.ok) {
        toast.error(result.error || "GitHub repo listing failed");
        setRepos([]);
        return;
      }
      setRepos(result.items || []);
      toast.success(`Loaded ${result.total || result.items?.length || 0} GitHub repos`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "GitHub repo listing failed");
    } finally {
      setLoadingRepos(false);
    }
  };

  const selectRepo = async (repo) => {
    setSelectedRepo(repo);
    setRepoUrl(repo.html_url || `https://github.com/${repo.full_name}`);
    setBranch(repo.default_branch || "main");
    setBranches([]);
    setLoadingBranches(true);
    try {
      const result = await System.githubBranches(repo.owner, repo.name);
      if (!result.ok) {
        toast.error(result.error || "Could not load branches");
        return;
      }
      setBranches(result.items || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not load branches");
    } finally {
      setLoadingBranches(false);
    }
  };

  const importSelectedToStorage = async () => {
    if (!selectedRepo) return;
    setBusy(true);
    try {
      const result = await Builds.importGit({
        repo_url: selectedRepo.html_url || `https://github.com/${selectedRepo.full_name}`,
        branch: branch || selectedRepo.default_branch || "main",
        confirm_overwrite: false,
      });
      toast.success("Repo cloned into build storage.");
      navigate("/dashboard/builds", { state: { imported: result } });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Build storage import failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="premium-card rounded-3xl p-6">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-accent">Repo Workbench</div>
          <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight text-white md:text-5xl">
            From GitHub repo to reviewed pull request.
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-amk-fg2">
            Browse repos through the dashboard-managed GitHub PAT, pick a branch, clone it into Build Storage,
            or paste a public repo URL directly.
          </p>
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-8">
          {["Connect", "Import", "Ask Aiva", "Analyze", "Plan", "Diff", "Commit", "Open PR"].map((step, index) => (
            <div key={step} className="rounded-2xl border border-amk-line bg-amk-base/70 p-3">
              <div className="font-mono text-[9px] uppercase tracking-wider text-amk-fg3">0{index + 1}</div>
              <div className="mt-2 font-display text-sm text-white">{step}</div>
            </div>
          ))}
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <TruthBox title="Public import" value="Available" ok copy="Imports public repos and creates a workspace for analysis." />
          <TruthBox title="Private repo / PR" value={githubLabel} ok={githubConfigured} copy={githubCap?.reason || "Needs GITHUB_PAT in Settings before private operations can run."} />
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="glass-panel overflow-hidden rounded-3xl">
          <div className="flex flex-wrap items-center gap-3 border-b border-amk-line p-5">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Connected GitHub</div>
              <h2 className="mt-1 font-display text-xl font-semibold text-white">Browse and clone a repo</h2>
            </div>
            <Button
              type="button"
              onClick={loadRepos}
              disabled={!githubConfigured || loadingRepos}
              className="ml-auto border border-amk-line bg-transparent font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:border-amk-accent hover:bg-transparent hover:text-amk-accent disabled:opacity-50"
              data-testid="load-github-repos-btn"
            >
              <RefreshCw className={`mr-2 h-3.5 w-3.5 ${loadingRepos ? "animate-spin" : ""}`} />
              Load repos
            </Button>
          </div>

          {repos.length === 0 ? (
            <div className="p-6 text-sm text-amk-fg3">
              {githubConfigured
                ? "Load repositories to select a branch from GitHub."
                : "Configure GitHub PAT in Settings to browse private repositories."}
            </div>
          ) : (
            <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_340px]">
              <div className="border-r border-amk-line">
                <div className="flex items-center gap-2 border-b border-amk-line px-3 py-2">
                  <Search className="h-3.5 w-3.5 text-amk-fg3" />
                  <input
                    value={repoSearch}
                    onChange={(e) => setRepoSearch(e.target.value)}
                    placeholder="Search repos..."
                    className="w-full bg-transparent py-1 font-mono text-xs text-white outline-none placeholder:text-amk-fg3"
                  />
                </div>
                <div className="max-h-[430px] overflow-y-auto">
                  {filteredRepos.map((repo) => (
                    <button
                      key={repo.full_name}
                      type="button"
                      onClick={() => selectRepo(repo)}
                      className={`w-full border-b border-amk-line px-3 py-3 text-left transition hover:bg-white/5 ${
                        selectedRepo?.full_name === repo.full_name ? "bg-amk-accent/10" : ""
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Github className="h-4 w-4 text-amk-fg3" />
                        <span className="font-mono text-sm text-white">{repo.full_name}</span>
                        <span className="ml-auto font-mono text-[9px] uppercase tracking-wider text-amk-fg3">
                          {repo.private ? "Private" : "Public"}
                        </span>
                      </div>
                      {repo.description && <p className="mt-1 line-clamp-1 text-xs text-amk-fg3">{repo.description}</p>}
                      <div className="mt-1 font-mono text-[10px] text-amk-fg3">
                        default: {repo.default_branch}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="p-4">
                <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Selected workspace</div>
                {selectedRepo ? (
                <div className="mt-3 space-y-3">
                    <div className="font-mono text-sm text-white">{selectedRepo.full_name}</div>
                    <label className="block">
                      <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Branch</span>
                      <select
                        value={branch}
                        onChange={(e) => setBranch(e.target.value)}
                        className="w-full border border-amk-line bg-amk-base px-3 py-2 font-mono text-xs text-white outline-none"
                        data-testid="github-branch-select"
                      >
                        {(branches.length ? branches : [{ name: selectedRepo.default_branch || "main" }]).map((item) => (
                          <option key={item.name} value={item.name}>{item.name}</option>
                        ))}
                      </select>
                    </label>
                    <div className="rounded-2xl border border-amk-line/70 p-3 font-mono text-[10px] text-amk-fg3">
                      Clone runs in Build Storage only. It does not edit production files.
                      {loadingBranches && <span className="block pt-1 text-amk-accent">Loading branches...</span>}
                    </div>
                    <Button
                      type="button"
                      onClick={importSelectedToStorage}
                      disabled={busy}
                      data-testid="clone-selected-repo-btn"
                      className="h-10 w-full bg-amk-accent font-mono text-[10px] uppercase tracking-wider text-black hover:bg-amk-accent/90 disabled:opacity-50"
                    >
                      <GitBranch className="mr-2 h-3.5 w-3.5" />
                      Clone selected repo
                    </Button>
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-amk-fg3">Select a repo to load branches and clone it.</p>
                )}
              </div>
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <div className="glass-panel rounded-3xl p-5">
            <LockKeyhole className="h-5 w-5 text-amk-accent" />
            <h2 className="mt-3 font-display text-xl text-white">GitHub PAT state</h2>
            <div className="mt-2 font-mono text-xs uppercase tracking-wider" style={{ color: githubConfigured ? "#00E676" : "#FFC107" }}>
              {githubLabel}
            </div>
            <p className="mt-2 text-xs leading-5 text-amk-fg3">
              Missing PAT is not treated as success. Private repo browsing, push, and PR actions remain setup-dependent.
            </p>
          </div>
          <div className="glass-panel rounded-3xl p-5">
            <Sparkles className="h-5 w-5 text-amk-accent" />
            <h2 className="mt-3 font-display text-xl text-white">After clone</h2>
            <p className="mt-2 text-xs leading-5 text-amk-fg3">
              Build Storage exposes detection, preview, install/build/test logs, quality gates, and GitHub PR actions when supported.
            </p>
          </div>
        </aside>
      </section>

      <section className="glass-panel rounded-3xl">
        <div className="border-b border-amk-line p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Manual public import</div>
          <h2 className="mt-1 font-display text-xl font-semibold text-white">Paste a GitHub URL</h2>
        </div>
        <form onSubmit={importRepo} className="space-y-5 p-5" data-testid="import-repo-form">
          <div>
            <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-amk-fg3">GitHub repo URL</label>
            <input data-testid="repo-url-input" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/owner/repo" className="field-input rounded-2xl" />
          </div>
          <div>
            <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Branch optional</label>
            <input data-testid="repo-branch-input" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" className="field-input rounded-2xl" />
          </div>
          <Button type="submit" disabled={busy} data-testid="import-repo-btn" className="h-11 w-full rounded-2xl bg-white font-mono text-xs uppercase tracking-wider text-black hover:bg-amk-accent">
            {busy ? "Importing..." : "Import repo"} <Github className="ml-2 h-4 w-4" />
          </Button>
        </form>
      </section>
    </div>
  );
}

function TruthBox({ title, value, ok, copy }) {
  return (
    <div className="rounded-3xl border border-amk-line bg-amk-base/70 p-4">
      <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{title}</div>
      <div className="mt-1 font-mono text-xs uppercase tracking-wider" style={{ color: ok ? "#00E676" : "#FFC107" }}>{value}</div>
      <p className="mt-2 text-xs leading-5 text-amk-fg3">{copy}</p>
    </div>
  );
}
