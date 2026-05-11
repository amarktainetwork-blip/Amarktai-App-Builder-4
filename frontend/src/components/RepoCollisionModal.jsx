import { useState } from "react";
import { Github, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * RepoCollisionModal
 *
 * Shown when POST /projects/{id}/finalize returns a 409 with repo_exists=true.
 *
 * Props:
 *   repoName     – string (the repo name that already exists)
 *   owner        – string (GitHub username)
 *   onBranchPR   – fn() – create branch + PR in existing repo
 *   onRename     – fn(newName: string) – create new repo with different name
 *   onCancel     – fn()
 *   busy         – boolean
 */
export default function RepoCollisionModal({ repoName, owner, onBranchPR, onRename, onCancel, busy }) {
  const [customName, setCustomName] = useState(`${repoName}-v2`);
  const [tab, setTab] = useState("branch"); // "branch" | "rename"

  return (
    <div
      data-testid="repo-collision-modal"
      className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
    >
      <div className="bg-amk-panel border border-amk-line max-w-md w-full rounded-sm shadow-2xl">
        <div className="px-5 pt-5 pb-3 border-b border-amk-line">
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.22em] text-agent-scout mb-2">
            <AlertCircle className="w-3.5 h-3.5" strokeWidth={1.5} />
            Repository name already exists
          </div>
          <p className="text-sm text-amk-fg2 leading-relaxed">
            <span className="font-mono text-amk-fg">{owner}/{repoName}</span> already exists on GitHub. How would you like to proceed?
          </p>
        </div>

        {/* Tab selector */}
        <div className="flex border-b border-amk-line">
          <button
            data-testid="collision-tab-branch"
            onClick={() => setTab("branch")}
            className={`flex-1 px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider transition-colors ${
              tab === "branch"
                ? "bg-amk-panel text-white border-b-2 border-amk-accent"
                : "text-amk-fg3 hover:text-white"
            }`}
          >
            Branch + PR <span className="ml-1 text-amk-accent text-[9px]">(recommended)</span>
          </button>
          <button
            data-testid="collision-tab-rename"
            onClick={() => setTab("rename")}
            className={`flex-1 px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider transition-colors ${
              tab === "rename"
                ? "bg-amk-panel text-white border-b-2 border-amk-accent"
                : "text-amk-fg3 hover:text-white"
            }`}
          >
            Create new repo
          </button>
        </div>

        <div className="p-5">
          {tab === "branch" ? (
            <div className="space-y-3">
              <p className="text-sm text-amk-fg2 leading-relaxed">
                Create a new branch in <span className="font-mono text-amk-fg">{owner}/{repoName}</span> and open a Pull Request with your generated code. The existing repo is never overwritten.
              </p>
              <div className="border border-amk-line bg-amk-base/40 p-3 font-mono text-[10px] text-amk-fg3 space-y-1">
                <div>Branch: <span className="text-amk-fg">amarktai-builder/&lt;job-slug&gt;</span></div>
                <div>Action: commit + open PR</div>
                <div>Safety: existing files untouched</div>
              </div>
              <Button
                data-testid="collision-branch-pr-btn"
                onClick={onBranchPR}
                disabled={busy}
                className="w-full bg-amk-accent text-black hover:bg-emerald-300 font-mono text-xs h-9"
              >
                <Github className="w-3.5 h-3.5 mr-1.5" strokeWidth={2} />
                {busy ? "Creating branch..." : "Create branch + open PR"}
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-amk-fg2 leading-relaxed">
                Create a new GitHub repository with a different name.
              </p>
              <div>
                <label className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-1.5 block">
                  New repository name
                </label>
                <input
                  data-testid="collision-rename-input"
                  type="text"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value.replace(/[^a-z0-9-]/gi, "-").toLowerCase())}
                  className="w-full bg-amk-base border border-amk-line h-9 px-3 font-mono text-xs focus:outline-none focus:border-white text-amk-fg"
                />
                <p className="font-mono text-[10px] text-amk-fg3 mt-1">
                  Will create: <span className="text-amk-fg">{owner}/{customName || repoName}</span>
                </p>
              </div>
              <Button
                data-testid="collision-rename-btn"
                onClick={() => onRename(customName || `${repoName}-amarktai`)}
                disabled={busy || !customName.trim()}
                className="w-full bg-white text-black hover:bg-zinc-200 font-mono text-xs h-9"
              >
                <Github className="w-3.5 h-3.5 mr-1.5" strokeWidth={2} />
                {busy ? "Creating..." : "Create new repo"}
              </Button>
            </div>
          )}
        </div>

        <div className="px-5 pb-4 border-t border-amk-line pt-3">
          <button
            data-testid="collision-cancel-btn"
            onClick={onCancel}
            className="w-full text-center font-mono text-[10px] text-amk-fg3 hover:text-white py-1"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
