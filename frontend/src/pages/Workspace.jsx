import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { LogOut, Square, RotateCcw, Zap, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import Header from "@/components/Header";
import AgentTimeline from "@/components/AgentTimeline";
import ChatPanel from "@/components/ChatPanel";
import FileTree from "@/components/FileTree";
import CodeViewer from "@/components/CodeViewer";
import LivePreview from "@/components/LivePreview";
import StatusBar from "@/components/StatusBar";
import SettingsDialog from "@/components/SettingsDialog";
import PRDialog from "@/components/PRDialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Projects, openProjectSocket } from "@/lib/amk-api";
import { useAuth } from "@/lib/auth-context";

export default function WorkspacePage() {
  const { projectId } = useParams();
  const { logout } = useAuth();
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
  const [finalizing, setFinalizing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [tab, setTab] = useState("preview");

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
    } else if (evt.type === "build_complete") {
      Projects.get(projectId).then(setProject);
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
    } else if (evt.type === "pr_opened") {
      setProject((p) => p ? { ...p, pr_url: evt.data.pr_url } : p);
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
      toast.success("Build stopped.");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to stop build");
    } finally {
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
      toast.error(e.response?.data?.detail || "Failed to finalize");
    } finally {
      setFinalizing(false);
    }
  };

  const submitPR = async (body) => {
    return Projects.openPR(projectId, body);
  };

  const busy = project?.status === "running" || project?.status === "queued";
  const failed = project?.status === "failed" || project?.status === "cancelled";

  return (
    <div className="h-screen flex flex-col bg-amk-base">
      <Header
        projectName={project?.name}
        status={project?.status}
        repoUrl={project?.repo_url}
        prUrl={project?.pr_url}
        hasGithub={!!project?.github}
        onOpenPR={() => setPrOpen(true)}
        finalizing={finalizing}
        onFinalize={finalize}
        onOpenSettings={() => setSettingsOpen(true)}
        rightExtra={
          <div className="flex items-center gap-1">
            {busy && (
              <button
                data-testid="stop-build-btn"
                onClick={stopBuild}
                disabled={cancelling}
                title="Stops the pipeline after the current model request and prevents further GenX credit usage."
                className="inline-flex items-center gap-1.5 px-3 h-8 border border-red-700 hover:bg-red-900/30 font-mono text-[10px] uppercase tracking-wider text-red-400 hover:text-red-300 disabled:opacity-50"
              >
                <Square className="w-3 h-3" strokeWidth={1.5} />
                {cancelling ? "stopping..." : "Stop Build"}
              </button>
            )}
            {failed && (
              <>
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
    </div>
  );
}
