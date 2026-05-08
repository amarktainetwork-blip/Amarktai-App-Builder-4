import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Trash2, Sparkles, ArrowRight } from "lucide-react";
import { toast } from "sonner";

import Header from "@/components/Header";
import SettingsDialog from "@/components/SettingsDialog";
import { Button } from "@/components/ui/button";
import { Projects } from "@/lib/emergent-api";

const PROMPT_TEMPLATES = [
  { name: "AmarktAI Leads", prompt: "Create a worldwide lead-gen PWA called 'AmarktAI Leads' with a bright design, hero search, and a contact-capture form." },
  { name: "Pomodoro Focus", prompt: "Build a minimal pomodoro timer with task list, dark mode, and gentle audio cue at the end of each interval." },
  { name: "Cosmic Dashboard", prompt: "An astronomy 'sky tonight' dashboard showing moon phase, constellation highlights, and tonight's astronomical events." },
  { name: "Recipe Roulette", prompt: "A playful recipe roulette where users spin to get a random dinner idea with ingredients and a 6-step method." },
];

export default function ProjectListPage() {
  const nav = useNavigate();
  const [projects, setProjects] = useState([]);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
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
      toast.success("Project created — agents are starting.");
      nav(`/workspace/${proj.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to create project");
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
      <Header onOpenSettings={() => setSettingsOpen(true)} />

      <main className="flex-1 grid lg:grid-cols-2 gap-px bg-emergent-line">
        {/* Left: Create */}
        <section className="bg-emergent-base p-8 lg:p-12">
          <div className="max-w-xl">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-emergent-fg3 mb-3">
              [ new build ]
            </div>
            <h1 className="font-mono text-3xl lg:text-4xl tracking-tight leading-none mb-3">
              Describe.<br />
              <span className="text-emergent-fg2">Watch.</span><br />
              <span className="text-emergent-fg3">Ship.</span>
              <span className="blink ml-1" />
            </h1>
            <p className="text-sm text-emergent-fg2 mb-8 leading-relaxed">
              Four specialised agents — Scout, Architect, Coder, Reviewer — collaborate
              to turn your prompt into a runnable web app. You watch every file appear
              in real-time.
            </p>

            <form onSubmit={create} className="space-y-3" data-testid="create-project-form">
              <div>
                <label className="font-mono text-[10px] uppercase tracking-wider text-emergent-fg3 block mb-1.5">
                  Project name
                </label>
                <input
                  data-testid="project-name-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. AmarktAI Leads"
                  className="w-full bg-emergent-panel border border-emergent-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-emergent-fg placeholder:text-emergent-fg3"
                />
              </div>
              <div>
                <label className="font-mono text-[10px] uppercase tracking-wider text-emergent-fg3 block mb-1.5">
                  Build prompt
                </label>
                <textarea
                  data-testid="project-prompt-input"
                  rows={5}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Build a worldwide lead-gen PWA with a bright design..."
                  className="w-full bg-emergent-panel border border-emergent-line p-3 font-sans text-sm resize-none focus:outline-none focus:border-white text-emergent-fg placeholder:text-emergent-fg3"
                />
              </div>

              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-emergent-fg3 mb-2">
                  Or pick a starter
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {PROMPT_TEMPLATES.map((t) => (
                    <button
                      type="button"
                      key={t.name}
                      data-testid={`template-${t.name.replace(/\s+/g, "-").toLowerCase()}`}
                      onClick={() => applyTemplate(t)}
                      className="text-left p-3 border border-emergent-line bg-emergent-panel hover:bg-emergent-surface transition-colors duration-150"
                    >
                      <div className="font-mono text-xs text-white mb-1">{t.name}</div>
                      <div className="text-[11px] text-emergent-fg3 leading-relaxed line-clamp-2">{t.prompt}</div>
                    </button>
                  ))}
                </div>
              </div>

              <Button
                data-testid="create-project-btn"
                type="submit"
                disabled={creating}
                className="w-full bg-white text-black hover:bg-zinc-200 font-mono text-xs h-11 mt-4"
              >
                {creating ? "STARTING AGENTS..." : "BEGIN AUTONOMOUS BUILD"}
                <Sparkles className="w-3.5 h-3.5 ml-2" strokeWidth={2} />
              </Button>
            </form>
          </div>
        </section>

        {/* Right: Project List */}
        <section className="bg-emergent-panel p-8 lg:p-12">
          <div className="max-w-xl">
            <div className="flex items-baseline justify-between mb-6">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-emergent-fg3 mb-2">
                  [ recent builds ]
                </div>
                <h2 className="font-mono text-2xl tracking-tight">Projects</h2>
              </div>
              <span className="font-mono text-[11px] text-emergent-fg3">
                {projects.length} total
              </span>
            </div>

            {projects.length === 0 ? (
              <div data-testid="projects-empty" className="grid-bg border border-emergent-line p-10 text-center">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-emergent-fg3 mb-2">
                  [ empty ]
                </div>
                <p className="text-sm text-emergent-fg2">
                  No projects yet. Describe an app on the left to get started.
                </p>
              </div>
            ) : (
              <ul className="space-y-2" data-testid="projects-list">
                {projects.map((p) => (
                  <li
                    key={p.id}
                    data-testid={`project-row-${p.id}`}
                    className="group border border-emergent-line bg-emergent-base hover:bg-emergent-surface transition-colors duration-150"
                  >
                    <div className="p-3 flex items-center gap-3">
                      <button
                        onClick={() => nav(`/workspace/${p.id}`)}
                        className="flex-1 text-left min-w-0"
                      >
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="font-mono text-sm text-white truncate">{p.name}</span>
                          <StatusDot status={p.status} />
                        </div>
                        <div className="font-mono text-[10px] text-emergent-fg3 truncate">
                          {p.prompt}
                        </div>
                      </button>
                      <button
                        data-testid={`project-delete-${p.id}`}
                        onClick={() => remove(p.id)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-emergent-fg3 hover:text-agent-scout p-1"
                        aria-label="delete project"
                      >
                        <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                      </button>
                      <ArrowRight
                        className="w-4 h-4 text-emergent-fg3 group-hover:text-white transition-colors"
                        strokeWidth={1.5}
                      />
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

function StatusDot({ status }) {
  const colors = { running: "#FFC107", ready: "#00E676", failed: "#FF5722", queued: "#A1A1AA" };
  return (
    <span
      title={status}
      className="inline-block w-1.5 h-1.5 rounded-full"
      style={{ background: colors[status] || "#71717A" }}
    />
  );
}
