import { Link } from "react-router-dom";
import { Settings as SettingsIcon, Github, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Header({ projectName, status, onOpenSettings, onFinalize, finalizing, repoUrl }) {
  return (
    <header
      data-testid="app-header"
      className="h-14 border-b border-emergent-line flex items-center justify-between px-4 bg-emergent-base/90 backdrop-blur-md sticky top-0 z-50"
    >
      <div className="flex items-center gap-3">
        <Link to="/" data-testid="header-logo" className="flex items-center gap-2 group">
          <div className="w-7 h-7 grid place-items-center border border-emergent-line bg-emergent-panel">
            <span className="font-mono text-[13px] font-bold tracking-tight">E</span>
          </div>
          <span className="font-mono text-sm tracking-tight text-emergent-fg group-hover:text-white">
            EMERGENT
          </span>
          <span className="font-mono text-[10px] text-emergent-fg3 uppercase tracking-[0.18em] hidden sm:inline">
            // autonomous ide
          </span>
        </Link>
        {projectName && (
          <>
            <div className="h-5 w-px bg-emergent-line mx-1" />
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-emergent-fg2">{projectName}</span>
              {status && <StatusPill status={status} />}
            </div>
          </>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button
          data-testid="header-settings-btn"
          variant="ghost"
          size="sm"
          className="text-emergent-fg2 hover:text-white hover:bg-emergent-surface font-mono text-xs"
          onClick={onOpenSettings}
        >
          <SettingsIcon className="w-3.5 h-3.5 mr-1.5" strokeWidth={1.5} /> Settings
        </Button>
        {repoUrl ? (
          <a
            data-testid="header-repo-link"
            href={repoUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 h-8 px-3 border border-emergent-line bg-emergent-panel hover:bg-emergent-surface font-mono text-xs text-emergent-fg"
          >
            <Github className="w-3.5 h-3.5" strokeWidth={1.5} /> View Repo
          </a>
        ) : onFinalize && (
          <Button
            data-testid="header-finalize-btn"
            size="sm"
            disabled={finalizing}
            className="bg-white text-black hover:bg-zinc-200 font-mono text-xs h-8"
            onClick={onFinalize}
          >
            <Github className="w-3.5 h-3.5 mr-1.5" strokeWidth={1.5} />
            {finalizing ? "Pushing..." : "Finalize & Push"}
          </Button>
        )}
      </div>
    </header>
  );
}

function StatusPill({ status }) {
  const map = {
    queued:  { color: "#A1A1AA", label: "queued" },
    running: { color: "#FFC107", label: "running" },
    ready:   { color: "#00E676", label: "ready" },
    failed:  { color: "#FF5722", label: "failed" },
  };
  const s = map[status] || map.queued;
  return (
    <span
      data-testid={`status-pill-${status}`}
      className="inline-flex items-center gap-1.5 px-2 h-6 border border-emergent-line bg-emergent-panel font-mono text-[10px] uppercase tracking-wider"
      style={{ color: s.color }}
    >
      {status === "running" ? (
        <span className="pulse-dot" style={{ background: s.color }} />
      ) : (
        <Activity className="w-3 h-3" strokeWidth={1.5} />
      )}
      {s.label}
    </span>
  );
}
