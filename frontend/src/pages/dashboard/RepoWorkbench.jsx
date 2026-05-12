import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { GitBranch, Github, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { Projects } from "@/lib/amk-api";

export default function RepoWorkbench() {
  const nav = useNavigate();
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [creating, setCreating] = useState(false);

  const importRepo = async (e) => {
    e?.preventDefault();
    if (!repoUrl.trim()) {
      toast.error("Repo URL required.");
      return;
    }
    setCreating(true);
    try {
      const proj = await Projects.fromRepo(repoUrl.trim(), branch.trim() || null, null);
      toast.success(`Imported ${proj.name}`);
      nav(`/workspace/${proj.id}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Import failed");
    } finally {
      setCreating(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="p-6 lg:p-10 max-w-2xl"
    >
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-3">
        [ repo workbench ]
      </div>
      <h1 className="font-display font-semibold text-3xl tracking-tight mb-2">
        Repo Workbench
      </h1>
      <p className="text-sm text-amk-fg2 mb-8 leading-relaxed">
        Import a GitHub repository. Agents will analyse, fix, and optionally prepare a branch or PR.
      </p>

      <form onSubmit={importRepo} className="space-y-4">
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-1.5">
            GitHub repo URL
          </label>
          <input
            data-testid="repo-url-input"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/org/repo"
            className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
          />
        </div>
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-1.5">
            Branch <span className="text-amk-fg3 normal-case">(optional, defaults to main)</span>
          </label>
          <input
            data-testid="repo-branch-input"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            placeholder="main"
            className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
          />
        </div>
        <button
          type="submit"
          data-testid="import-repo-btn"
          disabled={creating || !repoUrl.trim()}
          className="inline-flex items-center gap-2 px-5 h-10 bg-amk-accent text-black font-mono text-xs hover:bg-emerald-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Github className="w-3.5 h-3.5" strokeWidth={2} />
          {creating ? "Importing…" : "Import Repo"}
          {!creating && <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />}
        </button>
      </form>

      <div className="mt-10 border border-amk-line bg-amk-panel p-5">
        <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-3">
          [ what happens next ]
        </div>
        <ul className="space-y-2 text-sm text-amk-fg2">
          {[
            "Agents clone and analyse the repository structure.",
            "A full tech-stack profile is built including languages, frameworks, and dependencies.",
            "Missing or broken files are identified and patched.",
            "You can then finalize as a branch + pull request or push directly.",
          ].map((step, i) => (
            <li key={i} className="flex items-start gap-2">
              <GitBranch className="w-3.5 h-3.5 text-amk-fg3 mt-0.5 shrink-0" strokeWidth={1.5} />
              {step}
            </li>
          ))}
        </ul>
      </div>
    </motion.div>
  );
}
