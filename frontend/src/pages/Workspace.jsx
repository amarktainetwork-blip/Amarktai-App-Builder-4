import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";

import Header from "@/components/Header";
import AgentTimeline from "@/components/AgentTimeline";
import ChatPanel from "@/components/ChatPanel";
import FileTree from "@/components/FileTree";
import CodeViewer from "@/components/CodeViewer";
import LivePreview from "@/components/LivePreview";
import StatusBar from "@/components/StatusBar";
import SettingsDialog from "@/components/SettingsDialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Projects, openProjectSocket } from "@/lib/emergent-api";

export default function WorkspacePage() {
  const { projectId } = useParams();
  const [project, setProject] = useState(null);
  const [messages, setMessages] = useState([]);
  const [events, setEvents] = useState([]);
  const [files, setFiles] = useState([]);
  const [activePath, setActivePath] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [connected, setConnected] = useState(false);
  const [lastModel, setLastModel] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
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
      setProject((p) => p ? { ...p, status: evt.data.status } : p);
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

  const finalize = async () => {
    setFinalizing(true);
    try {
      const res = await Projects.finalize(projectId);
      if (res.mocked) toast.message("Finalized (mock).", { description: "Add a GitHub PAT in Settings to push for real." });
      else toast.success("Pushed to GitHub.");
    } catch (e) {
      toast.error("Failed to finalize");
    } finally {
      setFinalizing(false);
    }
  };

  const busy = project?.status === "running";

  return (
    <div className="h-screen flex flex-col bg-emergent-base">
      <Header
        projectName={project?.name}
        status={project?.status}
        repoUrl={project?.repo_url}
        finalizing={finalizing}
        onFinalize={finalize}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      {/* Workspace */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* LEFT 35% — chat & timeline */}
        <aside className="w-[35%] min-w-[360px] border-r border-emergent-line bg-emergent-base flex flex-col overflow-hidden">
          <AgentTimeline events={events} />
          <ChatPanel messages={messages} onSend={send} disabled={busy} busy={busy} />
        </aside>

        {/* RIGHT 65% — code & preview */}
        <section className="flex-1 flex flex-col bg-emergent-panel overflow-hidden">
          <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
            <div className="h-9 border-b border-emergent-line bg-emergent-base flex items-center px-2 shrink-0">
              <TabsList className="bg-transparent h-9 p-0 gap-0">
                <TabsTrigger
                  value="preview"
                  data-testid="tab-preview"
                  className="font-mono text-[11px] uppercase tracking-wider px-3 h-9 rounded-none border-r border-emergent-line data-[state=active]:bg-emergent-panel data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-t-2 data-[state=active]:border-t-white text-emergent-fg3"
                >
                  Live Preview
                </TabsTrigger>
                <TabsTrigger
                  value="code"
                  data-testid="tab-code"
                  className="font-mono text-[11px] uppercase tracking-wider px-3 h-9 rounded-none border-r border-emergent-line data-[state=active]:bg-emergent-panel data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-t-2 data-[state=active]:border-t-white text-emergent-fg3"
                >
                  Code
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="preview" className="flex-1 m-0 min-h-0">
              <LivePreview projectId={projectId} refreshKey={refreshKey} />
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
    </div>
  );
}
