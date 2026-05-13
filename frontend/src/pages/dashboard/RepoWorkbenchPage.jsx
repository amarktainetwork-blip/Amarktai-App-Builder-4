import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Github, LockKeyhole, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Projects, Settings, System } from "@/lib/amk-api";

export default function RepoWorkbenchPage() {
  const navigate = useNavigate();
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState({});
  const [capabilities, setCapabilities] = useState(null);

  useEffect(() => {
    Settings.get().then(setSettings).catch(() => setSettings({}));
    System.capabilitiesStatus().then(setCapabilities).catch(() => setCapabilities(null));
  }, []);

  const githubConfigured = !!settings.GITHUB_PAT?.configured || !!capabilities?.summary?.github_integration?.available;

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

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <section className="border border-amk-line bg-amk-panel">
        <div className="border-b border-amk-line p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">Repo Workbench</div>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-white">Import, analyze, repair, and route a repository.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-amk-fg2">
            Public repo import can work without a token. Private repos, GitHub PRs, and repository creation require a configured GitHub PAT.
          </p>
        </div>

        <form onSubmit={importRepo} className="space-y-5 p-5" data-testid="import-repo-form">
          <div>
            <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-amk-fg3">GitHub repo URL</label>
            <input data-testid="repo-url-input" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/owner/repo" className="field-input" />
          </div>
          <div>
            <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Branch optional</label>
            <input data-testid="repo-branch-input" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" className="field-input" />
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <TruthBox title="Public import" value="Available" ok copy="Imports public repos and creates a workspace for analysis." />
            <TruthBox title="Private repo / PR" value={githubConfigured ? "Available" : "Requires setup"} ok={githubConfigured} copy="Needs GITHUB_PAT in Settings before private operations can run." />
          </div>

          <Button type="submit" disabled={busy} data-testid="import-repo-btn" className="h-11 w-full bg-white font-mono text-xs uppercase tracking-wider text-black hover:bg-zinc-200">
            {busy ? "Importing..." : "Import repo"} <Github className="ml-2 h-4 w-4" />
          </Button>
        </form>
      </section>

      <aside className="space-y-4">
        <div className="border border-amk-line bg-amk-panel p-4">
          <LockKeyhole className="h-5 w-5 text-amk-accent" />
          <h2 className="mt-3 font-display text-xl text-white">GitHub PAT state</h2>
          <div className="mt-2 font-mono text-xs uppercase tracking-wider" style={{ color: githubConfigured ? "#00E676" : "#FFC107" }}>
            {githubConfigured ? "Available" : "Requires setup"}
          </div>
          <p className="mt-2 text-xs leading-5 text-amk-fg3">
            Missing PAT is not treated as success. The workbench will still allow public import, but private repo and PR actions remain setup-dependent.
          </p>
        </div>
        <div className="border border-amk-line bg-amk-panel p-4">
          <Sparkles className="h-5 w-5 text-amk-accent" />
          <h2 className="mt-3 font-display text-xl text-white">After import</h2>
          <p className="mt-2 text-xs leading-5 text-amk-fg3">The workspace exposes repo analysis, coverage, preview fallback, files, chat, QA, and PR actions when supported.</p>
        </div>
      </aside>
    </div>
  );
}

function TruthBox({ title, value, ok, copy }) {
  return (
    <div className="border border-amk-line bg-amk-base p-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{title}</div>
      <div className="mt-1 font-mono text-xs uppercase tracking-wider" style={{ color: ok ? "#00E676" : "#FFC107" }}>{value}</div>
      <p className="mt-2 text-xs leading-5 text-amk-fg3">{copy}</p>
    </div>
  );
}
