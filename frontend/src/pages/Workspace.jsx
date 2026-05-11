import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { LogOut, Square, RotateCcw, Zap, RefreshCw, Home, PlusSquare } from "lucide-react";
import { toast } from "sonner";

import Header from "@/components/Header";
import AgentTimeline from "@/components/AgentTimeline";
import ChatPanel from "@/components/ChatPanel";
import FileTree from "@/components/FileTree";
import CodeViewer from "@/components/CodeViewer";
import LivePreview from "@/components/LivePreview";
import StatusBar from "@/components/StatusBar";
import ValidationPanel from "@/components/ValidationPanel";
import RepoCollisionModal from "@/components/RepoCollisionModal";
import RepoWorkbenchPanel from "@/components/RepoWorkbenchPanel";
import SettingsDialog from "@/components/SettingsDialog";
import PRDialog from "@/components/PRDialog";
import MediaLibraryDialog from "@/components/MediaLibraryDialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Projects, openProjectSocket } from "@/lib/amk-api";
import { useAuth } from "@/lib/auth-context";

export default function WorkspacePage() {
  const { projectId } = useParams();
  const { logout } = useAuth();
  const nav = useNavigate();
  const [project, setProject] = useState(null);
  const [messages, setMessages] = useState([]);
  const [events, setEvents] = useState([]);
  const [files, setFiles] = useState([]);
  const [activePath, setActivePath] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [connected, setConnected] = useState(false);
  const [lastModel, setLastModel] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [prOpen, setPrOpen] = useState(false);
  const [mediaLibraryOpen, setMediaLibraryOpen] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [tab, setTab] = useState("preview");
  // Tracks the current pipeline sub-phase for the preview panel ("validating" | "repairing" | null)
  const [buildPhase, setBuildPhase] = useState(null);
  // Validation result surfaced from the last quality/design/security pass
  const [lastValidation, setLastValidation] = useState(null);
  // GitHub name collision state
  const [collisionModal, setCollisionModal] = useState(null); // { repoName, owner }
  const [collisionBusy, setCollisionBusy] = useState(false);
  // Phase 4/5/7: Repo workbench + coverage state (live-updated via WS events)
  const [repoAnalysis, setRepoAnalysis] = useState(null);
  const [coverageResult, setCoverageResult] = useState(null);
  // Phase 3: Preview fallback object
  const [previewFallback, setPreviewFallback] = useState(null);
  // Iteration result: changedFiles, addedFiles
  const [iterationResult, setIterationResult] = useState(null);

  const wsRef = useRef(null);

  // ---------- initial load ----------
  useEffect(() => {
    let alive = true;
    Promise.all([
      Projects.get(projectId),
      Projects.messages(projectId),
      Projects.events(projectId),
      Projects.files(projectId),
    ]).then(([p, m, e, f]) => {
      if (!alive) return;
      setProject(p);
      setMessages(m);
      setEvents(e);
      setFiles(f);
      if (f.length && !activePath) {
        const idx = f.find((x) => x.path === "index.html") || f[0];
        setActivePath(idx.path);
      }
    }).catch(() => toast.error("Failed to load project"));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // ---------- live updates ----------
  const handleEvent = useCallback((evt) => {
    if (evt.type === "hello") {
      setConnected(true);
      return;
    }
    if (evt.type === "message") {
      setMessages((cur) => [...cur, evt.data]);
    } else if (evt.type === "agent_event") {
      setEvents((cur) => [...cur, evt.data]);
    } else if (evt.type === "file_written") {
      Projects.files(projectId).then(setFiles);
      setRefreshKey((k) => k + 1);
      setActivePath((cur) => cur || evt.data.path);
    } else if (evt.type === "project_status") {
      setProject((p) => p ? {
        ...p,
        status: evt.data.status,
        error: evt.data.error ?? p.error,
        failed_agent: evt.data.failed_agent ?? p.failed_agent,
      } : p);
      // Clear build phase when project finishes
      if (["ready", "failed", "cancelled"].includes(evt.data.status)) {
        setBuildPhase(null);
        setCancelling(false);
        if (evt.data.status === "cancelled") toast.success("Build cancelled.");
      }
    } else if (evt.type === "validation_started") {
      setBuildPhase("validating");
    } else if (evt.type === "validation_passed" || evt.type === "validation_failed" || evt.type === "validation_exhausted") {
      setBuildPhase(null);
      // Capture quality/design/security scores from validation events
      if (evt.data) {
        setLastValidation((prev) => ({ ...prev, ...evt.data }));
      }
    } else if (
      evt.type === "quality_validation_passed" ||
      evt.type === "quality_validation_failed" ||
      evt.type === "security_validation_passed" ||
      evt.type === "security_validation_failed"
    ) {
      // All score events merge into the same validation state
      if (evt.data) setLastValidation((prev) => ({ ...prev, ...evt.data }));
    } else if (evt.type === "design_direction") {
      if (evt.data) setLastValidation((prev) => ({ ...prev, designDirection: evt.data }));
    } else if (evt.type === "repair_started") {
      setBuildPhase("repairing");
    } else if (evt.type === "repair_applied" || evt.type === "repair_failed") {
      setBuildPhase(null);
    } else if (evt.type === "build_complete") {
      Projects.get(projectId).then((p) => {
        setProject(p);
        // If project has last_validation, show it
        if (p?.last_validation) setLastValidation(p.last_validation);
      });
      Projects.files(projectId).then(setFiles);
      setRefreshKey((k) => k + 1);
    } else if (evt.type === "usage") {
      setLastModel(evt.data.model);
      setProject((p) => p ? {
        ...p,
        usage: {
          ...(p.usage || {}),
          tokens: (p.usage?.tokens || 0) + (evt.data.delta_tokens || 0),
          cost_usd: (p.usage?.cost_usd || 0) + (evt.data.delta_cost || 0),
          last_model: evt.data.model,
        },
      } : p);
    } else if (evt.type === "finalized") {
      setProject((p) => p ? { ...p, repo_url: evt.data.url } : p);
    } else if (evt.type === "pr_opened" || evt.type === "github_pr_created") {
      setProject((p) => p ? { ...p, pr_url: evt.data.pr_url } : p);
      toast.success("Pull request opened.");
    } else if (evt.type === "github_repo_exists") {
      // Backend signals that the repo name already exists on GitHub
      setCollisionModal({ repoName: evt.data.repo_name, owner: evt.data.owner });
    } else if (evt.type === "job_ready") {
      setProject((p) => p ? { ...p, status: "ready" } : p);
    } else if (evt.type === "job_failed") {
      setProject((p) => p ? { ...p, status: "failed", error: evt.data?.reason } : p);
    } else if (evt.type === "clarification_needed") {
      // Backend signals clarification during an in-progress build (future support)
      toast.info("Build agents need clarification — see conversation panel.");
    } else if (evt.type === "media_choice_needed") {
      toast.info("Media: agents are choosing the best source for your project.");
    } else if (evt.type === "repo_import_started") {
      // Repo import/fix started — clear stale fallback
      setPreviewFallback(null);
    } else if (evt.type === "repo_analysis_complete") {
      // Live repo analysis result from orchestrator
      if (evt.data) setRepoAnalysis((prev) => ({ ...(prev || {}), ...evt.data }));
    } else if (evt.type === "coverage_score") {
      // Live coverage score from orchestrator
      if (evt.data) setCoverageResult(evt.data);
    } else if (evt.type === "request_coverage_passed") {
      if (evt.data) setCoverageResult(evt.data);
      toast.success("Coverage check passed.");
    } else if (evt.type === "request_coverage_failed") {
      if (evt.data) setCoverageResult(evt.data);
      toast.warning("Coverage below 80 — finalize is locked until requirements are met.");
    } else if (evt.type === "preview_ready") {
      if (evt.data) setPreviewFallback(null); // live preview available, clear fallback
    } else if (evt.type === "preview_fallback_ready") {
      if (evt.data) setPreviewFallback(evt.data);
    } else if (evt.type === "preview_failed") {
      toast.warning("Preview failed — see fallback panel for commands and blockers.");
    } else if (evt.type === "repo_update_plan_complete") {
      toast.info("Repo update plan complete — see agent timeline.");
    } else if (evt.type === "repo_patch_complete") {
      Projects.files(projectId).then(setFiles);
      setRefreshKey((k) => k + 1);
    } else if (evt.type === "job_cancel_requested") {
      setCancelling(true);
    } else if (evt.type === "iteration_complete") {
      if (evt.data) {
        setIterationResult(evt.data);
        // Notify user if iteration left unsatisfied changes
        const unsatisfied = evt.data.unsatisfiedChanges;
        if (Array.isArray(unsatisfied) && unsatisfied.length > 0) {
          toast.warning(
            `${unsatisfied.length} requested change${unsatisfied.length > 1 ? "s" : ""} could not be applied — see iteration panel.`,
            { duration: 6000 }
          );
        }
      }
    }
  }, [projectId]);

  useEffect(() => {
    const ws = openProjectSocket(projectId, handleEvent);
    wsRef.current = ws;
    ws.addEventListener("open", () => setConnected(true));
    ws.addEventListener("close", () => setConnected(false));
    return () => ws.close();
  }, [projectId, handleEvent]);

  // ---------- actions ----------
  const send = async (content) => {
    try {
      await Projects.send(projectId, content);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to send");
    }
  };

  const stopBuild = async () => {
    setCancelling(true);
    try {
      await Projects.cancel(projectId);
      // Keep cancelling=true until a WebSocket status event confirms cancellation
      // so the button stays disabled and shows "Cancelling…"
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to stop build");
      setCancelling(false);
    }
  };

  const retryAgent = async (agent, quality_tier) => {
    setRetrying(true);
    try {
      await Projects.retry(projectId, agent, quality_tier);
      toast.success(`Retry queued: ${agent}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Retry failed");
    } finally {
      setRetrying(false);
    }
  };

  const finalize = async () => {
    setFinalizing(true);
    try {
      await Projects.finalize(projectId);
      toast.success("Created GitHub repository.");
    } catch (e) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail;
      // Phase 9: Handle repo name collision gracefully
      if (status === 409 && detail?.repo_exists) {
        setCollisionModal({ repoName: detail.repo_name, owner: detail.owner });
      } else {
        toast.error(detail || "Failed to finalize");
      }
    } finally {
      setFinalizing(false);
    }
  };

  const handleCollisionBranchPR = async () => {
    setCollisionBusy(true);
    try {
      const result = await Projects.finalizeAsBranch(projectId);
      setCollisionModal(null);
      toast.success("Branch created and PR opened.");
      if (result?.pr_url) {
        setProject((p) => p ? { ...p, pr_url: result.pr_url } : p);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to create branch PR");
    } finally {
      setCollisionBusy(false);
    }
  };

  const handleCollisionRename = async (newName) => {
    setCollisionBusy(true);
    try {
      const result = await Projects.finalize(projectId, { repo_name_override: newName });
      setCollisionModal(null);
      toast.success("Repository created.");
      if (result?.url) {
        setProject((p) => p ? { ...p, repo_url: result.url } : p);
      }
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (e.response?.status === 409 && detail?.repo_exists) {
        setCollisionModal({ repoName: detail.repo_name, owner: detail.owner });
      } else {
        toast.error(detail || "Failed to create repository");
      }
    } finally {
      setCollisionBusy(false);
    }
  };

  const submitPR = async (body) => {
    return Projects.openPR(projectId, body);
  };

  const busy = project?.status === "running" || project?.status === "queued";
  const failed = project?.status === "failed" || project?.status === "cancelled";
  const ready = project?.status === "ready";
  // Phase 2: Gate finalize on validation scores
  const validation = lastValidation || project?.last_validation;
  // Phase 6: Also gate on coverage for repo-update intents
  const _COVERAGE_INTENTS = new Set(["full_app_completion", "repo_migration", "full_rebuild_inside_repo"]);
  const updateIntent = project?.update_intent || coverageResult?.intent;
  const coverageOk = !updateIntent || !_COVERAGE_INTENTS.has(updateIntent)
    || (coverageResult?.coverageScore ?? 100) >= 80;
  const canFinalize = ready && (!validation || validation.canFinalize !== false) && coverageOk;

  // Phase 3: action to fetch preview fallback on demand
  const runPreviewFallback = async () => {
    try {
      const fb = await Projects.previewFallback(projectId);
      setPreviewFallback(fb);
    } catch {
      toast.error("Could not fetch preview info.");
    }
  };

  // Continue building missing requirements (coverage < 80)
  const continueMissingRequirements = async (missingReqs) => {
    const msg = `Continue building the missing requirements: ${missingReqs.join(", ")}`;
    try {
      if (project?.mode === "repo_fix" || project?.github) {
        await Projects.iterate(projectId, msg);
      } else {
        await Projects.send(projectId, msg);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to continue building");
    }
  };

  // Determine if this is a repo-imported project
  const isRepoProject = !!(project?.mode === "repo_fix" || project?.github);

  return (
    <div className="h-screen flex flex-col bg-amk-base">
      {/* Phase 9: GitHub repo name collision modal */}
      {collisionModal && (
        <RepoCollisionModal
          repoName={collisionModal.repoName}
          owner={collisionModal.owner}
          onBranchPR={handleCollisionBranchPR}
          onRename={handleCollisionRename}
          onCancel={() => setCollisionModal(null)}
          busy={collisionBusy}
        />
      )}
      <Header
        projectName={project?.name}
        status={project?.status}
        repoUrl={project?.repo_url}
        prUrl={project?.pr_url}
        hasGithub={!!project?.github}
        onOpenPR={() => setPrOpen(true)}
        finalizing={finalizing}
        canFinalize={canFinalize}
        onFinalize={finalize}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenMediaLibrary={() => setMediaLibraryOpen(true)}
        rightExtra={
          <div className="flex items-center gap-1">
            {/* Workspace navigation */}
            <button
              data-testid="back-to-projects-btn"
              onClick={() => nav("/app")}
              title="Back to Projects"
              className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white"
            >
              <Home className="w-3 h-3" strokeWidth={1.5} /> Projects
            </button>
            <button
              data-testid="new-build-btn"
              onClick={() => nav("/app")}
              title="Start a new build"
              className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white"
            >
              <PlusSquare className="w-3 h-3" strokeWidth={1.5} /> New Build
            </button>
            {busy && (
              <button
                data-testid="stop-build-btn"
                onClick={stopBuild}
                disabled={cancelling}
                title="Stops the pipeline after the current model request and prevents further GenX credit usage."
                className="inline-flex items-center gap-1.5 px-3 h-8 border border-red-700 hover:bg-red-900/30 font-mono text-[10px] uppercase tracking-wider text-red-400 hover:text-red-300 disabled:opacity-50"
              >
                <Square className="w-3 h-3" strokeWidth={1.5} />
                {cancelling ? "Cancelling…" : "Stop Build"}
              </button>
            )}
            {failed && (
              <>
                <button
                  data-testid="retry-repair-btn"
                  onClick={() => retryAgent("repair")}
                  disabled={retrying}
                  title="Re-run Reviewer/Repair to patch missing or broken files."
                  className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white disabled:opacity-50"
                >
                  <RotateCcw className="w-3 h-3" strokeWidth={1.5} /> Retry Repair
                </button>
                <button
                  data-testid="retry-coder-btn"
                  onClick={() => retryAgent("coder")}
                  disabled={retrying}
                  title="Retry Coder using stored Scout/Architect outputs."
                  className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white disabled:opacity-50"
                >
                  <RotateCcw className="w-3 h-3" strokeWidth={1.5} /> Retry Coder
                </button>
                <button
                  data-testid="retry-premium-btn"
                  onClick={() => retryAgent("coder", "premium")}
                  disabled={retrying}
                  title="Retry Coder with premium model tier."
                  className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white disabled:opacity-50"
                >
                  <Zap className="w-3 h-3" strokeWidth={1.5} /> Retry Premium
                </button>
                <button
                  data-testid="restart-build-btn"
                  onClick={() => retryAgent("pipeline")}
                  disabled={retrying}
                  title="Restart the full build pipeline from scratch."
                  className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white disabled:opacity-50"
                >
                  <RefreshCw className="w-3 h-3" strokeWidth={1.5} /> Restart Build
                </button>
              </>
            )}
            <button
              data-testid="header-logout-btn"
              onClick={logout}
              className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white"
            >
              <LogOut className="w-3 h-3" strokeWidth={1.5} /> sign out
            </button>
          </div>
        }
      />

      {/* Workspace */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* LEFT 35% — chat & timeline */}
        <aside className="w-[35%] min-w-[360px] border-r border-amk-line bg-amk-base flex flex-col overflow-hidden">
          <AgentTimeline events={events} />
          {!connected && (
            <div className="border-y border-amk-line bg-amk-panel px-3 py-2 font-mono text-[10px] text-agent-scout">
              WebSocket disconnected. Reopen the workspace or check the backend if updates stop streaming.
            </div>
          )}
          {failed && project?.error && (
            <div className="border-y border-red-900 bg-red-950/30 px-3 py-2 font-mono text-[10px] text-red-400">
              {project.failed_agent && <span className="font-semibold">{project.failed_agent}: </span>}
              {project.error}
            </div>
          )}
          {/* Phase 2: Quality/design/security validation scores */}
          <ValidationPanel validation={validation} />
          {/* Phase 4: Repo workbench (shown for imported repos) */}
          {isRepoProject && (
            <RepoWorkbenchPanel
              projectId={projectId}
              project={project}
              repoAnalysis={repoAnalysis}
              coverage={coverageResult}
              onRunPreview={runPreviewFallback}
              onContinueMissing={continueMissingRequirements}
              busy={busy}
            />
          )}
          {/* Coverage panel for regular (non-repo) projects */}
          {!isRepoProject && coverageResult && (
            <div
              data-testid="coverage-panel"
              className="border-y border-amk-line bg-amk-panel px-3 py-2 font-mono text-[10px]"
            >
              {(() => {
                const covScore = coverageResult.coverageScore ?? null;
                const covOk = covScore === null || covScore >= 80;
                const missing = coverageResult.missingRequirements || [];
                return (
                  <>
                    <div className="flex items-center gap-2">
                      <span
                        className="uppercase tracking-wider"
                        style={{ color: covOk ? "#00E676" : covScore >= 64 ? "#FFC107" : "#FF5722" }}
                      >
                        Coverage {covScore}/100
                      </span>
                      {!covOk && (
                        <span className="text-agent-scout text-[9px]">— finalize locked</span>
                      )}
                    </div>
                    <div className="mt-1 h-1 bg-white/10 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${Math.min(covScore ?? 0, 100)}%`,
                          background: covOk ? "#00E676" : covScore >= 64 ? "#FFC107" : "#FF5722",
                        }}
                      />
                    </div>
                    {missing.length > 0 && (
                      <div className="mt-1 space-y-0.5">
                        <span className="text-amk-fg3">Missing requirements:</span>
                        {missing.slice(0, 4).map((m, i) => (
                          <div key={i} className="flex items-start gap-1 text-amk-fg2">
                            <span className="shrink-0">·</span><span>{m}</span>
                          </div>
                        ))}
                        <button
                          type="button"
                          data-testid="continue-missing-requirements-btn"
                          disabled={busy}
                          onClick={() => continueMissingRequirements(missing)}
                          className="mt-1 px-2 py-0.5 border border-agent-coder text-[9px] uppercase tracking-wider text-agent-coder bg-agent-coder/10 hover:bg-agent-coder/20 disabled:opacity-50 transition-colors"
                        >
                          Continue building missing requirements
                        </button>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}
          {/* Iteration result: show changed/added files after a successful iteration */}
          {(() => {
            const hasIterationResult = iterationResult && !busy && (
              iterationResult.changedFiles?.length > 0 || iterationResult.addedFiles?.length > 0
            );
            if (!hasIterationResult) return null;
            const unsatisfied = iterationResult.unsatisfiedChanges || [];
            return (
              <div
                data-testid="iteration-result-panel"
                className="border-y border-amk-line bg-amk-panel px-3 py-2 font-mono text-[10px]"
              >
                <div className="flex items-center justify-between">
                  <span
                    className="uppercase tracking-wider"
                    style={{ color: unsatisfied.length > 0 ? "#FFC107" : "#00E676" }}
                  >
                    {unsatisfied.length > 0 ? "Iteration finished — changes still needed" : "Iteration complete"}
                  </span>
                  <button
                    type="button"
                    onClick={() => setIterationResult(null)}
                    className="text-amk-fg3 hover:text-white text-[9px] uppercase tracking-wider"
                  >
                    dismiss
                  </button>
                </div>
                {iterationResult.changedFiles?.length > 0 && (
                  <div className="mt-1 text-amk-fg2">
                    Changed: {iterationResult.changedFiles.join(", ")}
                  </div>
                )}
                {iterationResult.addedFiles?.length > 0 && (
                  <div className="mt-0.5 text-amk-fg2">
                    Added: {iterationResult.addedFiles.join(", ")}
                  </div>
                )}
                {unsatisfied.length > 0 && (
                  <div
                    data-testid="iteration-unsatisfied-panel"
                    className="mt-2 border border-agent-scout/40 bg-agent-scout/10 px-2 py-1.5 rounded-sm"
                  >
                    <div className="text-agent-scout uppercase tracking-wider mb-1">
                      {unsatisfied.length} change{unsatisfied.length > 1 ? "s" : ""} not applied
                    </div>
                    <ul className="space-y-0.5 text-amk-fg2">
                      {unsatisfied.map((item, i) => (
                        <li key={i} className="flex items-start gap-1">
                          <span className="text-agent-scout shrink-0">·</span>
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                    <button
                      type="button"
                      data-testid="continue-fixing-btn"
                      disabled={busy}
                      onClick={() => {
                        const msg = `Continue fixing the remaining changes: ${unsatisfied.join("; ")}`;
                        send(msg);
                        setIterationResult(null);
                      }}
                      className="mt-2 px-2 py-0.5 border border-agent-scout text-[9px] uppercase tracking-wider text-agent-scout bg-agent-scout/10 hover:bg-agent-scout/20 disabled:opacity-50 transition-colors"
                    >
                      Continue fixing remaining changes
                    </button>
                  </div>
                )}
              </div>
            );
          })()}
          <ChatPanel messages={messages} onSend={send} disabled={busy} busy={busy} />
        </aside>

        {/* RIGHT 65% — code & preview */}
        <section className="flex-1 flex flex-col bg-amk-panel overflow-hidden">
          <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
            <div className="h-9 border-b border-amk-line bg-amk-base flex items-center px-2 shrink-0">
              <TabsList className="bg-transparent h-9 p-0 gap-0">
                <TabsTrigger
                  value="preview"
                  data-testid="tab-preview"
                  className="font-mono text-[11px] uppercase tracking-wider px-3 h-9 rounded-none border-r border-amk-line data-[state=active]:bg-amk-panel data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-t-2 data-[state=active]:border-t-white text-amk-fg3"
                >
                  Live Preview
                </TabsTrigger>
                <TabsTrigger
                  value="code"
                  data-testid="tab-code"
                  className="font-mono text-[11px] uppercase tracking-wider px-3 h-9 rounded-none border-r border-amk-line data-[state=active]:bg-amk-panel data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-t-2 data-[state=active]:border-t-white text-amk-fg3"
                >
                  Code
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="preview" className="flex-1 m-0 min-h-0">
              <LivePreview
                projectId={projectId}
                refreshKey={refreshKey}
                projectStatus={project?.status}
                projectError={project?.error}
                failedAgent={project?.failed_agent}
                projectMode={project?.mode}
                previewStrategy={project?.preview_strategy}
                buildPhase={buildPhase}
                previewFallback={previewFallback}
              />
            </TabsContent>

            <TabsContent value="code" className="flex-1 m-0 min-h-0">
              <div className="h-full grid grid-cols-[260px,1fr]">
                <FileTree files={files} activePath={activePath} onSelect={setActivePath} />
                <CodeViewer projectId={projectId} path={activePath} />
              </div>
            </TabsContent>
          </Tabs>
        </section>
      </div>

      <StatusBar project={project} lastModel={lastModel} connected={connected} />
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
      <PRDialog open={prOpen} onOpenChange={setPrOpen} project={project} onSubmit={submitPR} />
      <MediaLibraryDialog
        open={mediaLibraryOpen}
        onOpenChange={setMediaLibraryOpen}
        projectId={projectId}
      />
    </div>
  );
}
