import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Trash2, Sparkles, ArrowRight, Github, LogOut } from "lucide-react";
import { toast } from "sonner";

import Header from "@/components/Header";
import SettingsDialog from "@/components/SettingsDialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Projects } from "@/lib/amk-api";
import { useAuth } from "@/lib/auth-context";

const PROMPT_TEMPLATES = [
  { name: "AmarktAI Leads",   prompt: "Create a worldwide lead-gen PWA called 'AmarktAI Leads' with a bright design, hero search, and a contact-capture form." },
  { name: "Pomodoro Focus",   prompt: "Build a minimal pomodoro timer with task list, dark mode, and gentle audio cue at the end of each interval." },
  { name: "Cosmic Dashboard", prompt: "An astronomy 'sky tonight' dashboard showing moon phase, constellation highlights, and tonight's astronomical events." },
  { name: "Recipe Roulette",  prompt: "A playful recipe roulette where users spin to get a random dinner idea with ingredients and a 6-step method." },
];

export default function ProjectListPage() {
  const nav = useNavigate();
  const { user, logout } = useAuth();
  const [projects, setProjects] = useState([]);
  const [tab, setTab] = useState("prompt");
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [creating, setCreating] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const refresh = () => Projects.list().then(setProjects).catch(() => setProjects([]));

  useEffect(() => { refresh(); }, []);

  const create = async (e) => {
    e?.preventDefault();
    if (!name.trim() || !prompt.trim()) {
      toast.error("Name and prompt are required.");
      return;
    }
    setCreating(true);
    try {
      const proj = await Projects.create(name.trim(), prompt.trim());
      toast.success("Agents launched.");
      nav(`/workspace/${proj.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to create project");
    } finally {
      setCreating(false);
    }
  };

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
    } catch (e) {
      toast.error(e.response?.data?.detail || "Import failed");
    } finally {
      setCreating(false);
    }
  };

  const remove = async (id) => {
    await Projects.remove(id);
    refresh();
  };

  const applyTemplate = (t) => { setName(t.name); setPrompt(t.prompt); };

  return (
    <div className="min-h-screen flex flex-col">
      <Header
        onOpenSettings={() => setSettingsOpen(true)}
        rightExtra={
          <button
            data-testid="header-logout-btn"
            onClick={logout}
            title={user?.email}
            className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white"
          >
            <LogOut className="w-3 h-3" strokeWidth={1.5} /> sign out
          </button>
        }
      />

      <main className="flex-1 grid lg:grid-cols-2 gap-px bg-amk-line">
        <section className="bg-amk-base p-8 lg:p-12">
          <div className="max-w-xl">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-3">[ new build ]</div>
            <h1 className="font-display font-semibold text-3xl lg:text-5xl tracking-tight leading-[1.05] mb-3">
              Describe.<br />
              <span className="text-amk-fg2">Or import.</span><br />
              <span className="text-amk-accent">Watch agents ship.<span className="blink ml-1" /></span>
            </h1>
            <p className="text-sm text-amk-fg2 mb-8 leading-relaxed">
              Start from a prompt or pull in a public GitHub repo. Four agents collaborate, files
              appear in real-time, and you can iterate or open a PR with one click.
            </p>

            <Tabs value={tab} onValueChange={setTab} data-testid="new-build-tabs">
              <TabsList className="bg-transparent p-0 gap-0 border border-amk-line w-full justify-start">
                <TabsTrigger value="prompt" data-testid="tab-prompt"
                  className="font-mono text-[10px] uppercase tracking-wider px-4 h-9 rounded-none border-r border-amk-line data-[state=active]:bg-amk-panel data-[state=active]:text-white data-[state=active]:shadow-none text-amk-fg3 flex-1">
                  <Sparkles className="w-3 h-3 mr-1.5" /> Prompt
                </TabsTrigger>
                <TabsTrigger value="repo" data-testid="tab-repo"
                  className="font-mono text-[10px] uppercase tracking-wider px-4 h-9 rounded-none data-[state=active]:bg-amk-panel data-[state=active]:text-white data-[state=active]:shadow-none text-amk-fg3 flex-1">
                  <Github className="w-3 h-3 mr-1.5" /> GitHub repo
                </TabsTrigger>
              </TabsList>

              <TabsContent value="prompt" className="mt-4">
                <form onSubmit={create} className="space-y-3" data-testid="create-project-form">
                  <FieldLabel>Project name</FieldLabel>
                  <input
                    data-testid="project-name-input"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. AmarktAI Leads"
                    className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                  />
                  <FieldLabel>Build prompt</FieldLabel>
                  <textarea
                    data-testid="project-prompt-input"
                    rows={5}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Build a worldwide lead-gen PWA with a bright design..."
                    className="w-full bg-amk-panel border border-amk-line p-3 font-sans text-sm resize-none focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                  />
                  <div>
                    <FieldLabel>Or pick a starter</FieldLabel>
                    <div className="grid grid-cols-2 gap-2">
                      {PROMPT_TEMPLATES.map((t) => (
                        <button
                          type="button"
                          key={t.name}
                          data-testid={`template-${t.name.replace(/\s+/g, "-").toLowerCase()}`}
                          onClick={() => applyTemplate(t)}
                          className="text-left p-3 border border-amk-line bg-amk-panel hover:bg-amk-surface transition-colors duration-150"
                        >
                          <div className="font-mono text-xs text-white mb-1">{t.name}</div>
                          <div className="text-[11px] text-amk-fg3 leading-relaxed line-clamp-2">{t.prompt}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                  <Button data-testid="create-project-btn" type="submit" disabled={creating}
                    className="w-full bg-amk-accent text-black hover:bg-emerald-300 font-mono text-xs h-11 mt-4">
                    {creating ? "STARTING AGENTS..." : "BEGIN AUTONOMOUS BUILD"}
                    <Sparkles className="w-3.5 h-3.5 ml-2" strokeWidth={2} />
                  </Button>
                </form>
              </TabsContent>

              <TabsContent value="repo" className="mt-4">
                <form onSubmit={importRepo} className="space-y-3" data-testid="import-repo-form">
                  <FieldLabel>Public GitHub repo URL</FieldLabel>
                  <input
                    data-testid="repo-url-input"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    placeholder="https://github.com/owner/repo"
                    className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                  />
                  <FieldLabel>Branch <span className="text-amk-fg3 normal-case">(optional — defaults to repo's default)</span></FieldLabel>
                  <input
                    data-testid="repo-branch-input"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    placeholder="main"
                    className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                  />
                  <p className="font-mono text-[10px] text-amk-fg3 leading-relaxed">
                    We'll mirror text files from the default branch into your sandbox. To open a PR
                    later, save your <span className="text-amk-fg2">GitHub PAT</span> in Settings.
                  </p>
                  <Button data-testid="import-repo-btn" type="submit" disabled={creating}
                    className="w-full bg-white text-black hover:bg-zinc-200 font-mono text-xs h-11 mt-2">
                    {creating ? "IMPORTING..." : "IMPORT REPO"}
                    <Github className="w-3.5 h-3.5 ml-2" strokeWidth={2} />
                  </Button>
                </form>
              </TabsContent>
            </Tabs>
          </div>
        </section>

        <section className="bg-amk-panel p-8 lg:p-12">
          <div className="max-w-xl">
            <div className="flex items-baseline justify-between mb-6">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-2">[ recent builds ]</div>
                <h2 className="font-display font-semibold text-2xl tracking-tight">Projects</h2>
              </div>
              <span className="font-mono text-[11px] text-amk-fg3">{projects.length} total</span>
            </div>

            {projects.length === 0 ? (
              <div data-testid="projects-empty" className="grid-bg border border-amk-line p-10 text-center">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-amk-fg3 mb-2">[ empty ]</div>
                <p className="text-sm text-amk-fg2">No projects yet. Describe an app or import a repo to get started.</p>
              </div>
            ) : (
              <ul className="space-y-2" data-testid="projects-list">
                {projects.map((p) => (
                  <li key={p.id} data-testid={`project-row-${p.id}`}
                      className="group border border-amk-line bg-amk-base hover:bg-amk-surface transition-colors duration-150">
                    <div className="p-3 flex items-center gap-3">
                      <button onClick={() => nav(`/workspace/${p.id}`)} className="flex-1 text-left min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="font-mono text-sm text-white truncate">{p.name}</span>
                          {p.github && <Github className="w-3 h-3 text-amk-fg3" strokeWidth={1.5} />}
                          <StatusDot status={p.status} />
                        </div>
                        <div className="font-mono text-[10px] text-amk-fg3 truncate">{p.prompt}</div>
                      </button>
                      <button data-testid={`project-delete-${p.id}`} onClick={() => remove(p.id)}
                              className="opacity-0 group-hover:opacity-100 transition-opacity text-amk-fg3 hover:text-agent-scout p-1"
                              aria-label="delete project">
                        <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                      </button>
                      <ArrowRight className="w-4 h-4 text-amk-fg3 group-hover:text-white transition-colors" strokeWidth={1.5} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </main>

      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}

function FieldLabel({ children }) {
  return <label className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 block mb-1.5">{children}</label>;
}

function StatusDot({ status }) {
  const colors = { running: "#FFC107", ready: "#00E676", failed: "#FF5722", queued: "#A1A1AA" };
  return <span title={status} className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: colors[status] || "#71717A" }} />;
}
