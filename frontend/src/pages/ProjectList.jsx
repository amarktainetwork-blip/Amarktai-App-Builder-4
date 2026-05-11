import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Trash2, Sparkles, ArrowRight, Github, LogOut, Activity, ShieldCheck, Users, Image, Video, Palette, Cpu } from "lucide-react";
import { toast } from "sonner";

import Header from "@/components/Header";
import SettingsDialog from "@/components/SettingsDialog";
import ClarificationModal from "@/components/ClarificationModal";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Projects, System, Clarify } from "@/lib/amk-api";
import { useAuth } from "@/lib/auth-context";

const PROMPT_TEMPLATES = [
  { name: "Lead Desk",   prompt: "Create a worldwide lead-gen PWA called 'Lead Desk' with a bright design, hero search, and a contact-capture form." },
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
  const [mode, setMode] = useState("web_app");
  const [qualityTier, setQualityTier] = useState("balanced");
  const [mediaChoice, setMediaChoice] = useState("auto");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [upgradeModal, setUpgradeModal] = useState(null);
  const [clarification, setClarification] = useState(null); // { questions, assumptions }
  const [pendingCreate, setPendingCreate] = useState(null); // { upgradeAcknowledged }
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [creating, setCreating] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [readiness, setReadiness] = useState(null);

  const refresh = () => Projects.list().then(setProjects).catch(() => setProjects([]));
  const refreshReadiness = () => System.readiness().then(setReadiness).catch(() => setReadiness(null));

  useEffect(() => { refresh(); refreshReadiness(); }, []);

  const doCreate = async (enrichedPrompt, upgradeAcknowledged = false, extraParams = {}) => {
    if (readiness?.overall !== "PASS") {
      toast.error("GenX readiness must pass before starting Amarktai Coding Agents.");
      return;
    }
    if (!name.trim() || !enrichedPrompt.trim()) {
      toast.error("Name and prompt are required.");
      return;
    }
    setCreating(true);
    try {
      const mediaRequirements = mediaChoice !== "auto" ? mediaChoice : undefined;
      const proj = await Projects.create(name.trim(), enrichedPrompt.trim(), {
        mode,
        quality_tier: qualityTier,
        upgrade_confirmation_acknowledged: upgradeAcknowledged,
        media_requirements: mediaRequirements,
        ...extraParams,
      });
      toast.success("Agents launched.");
      nav(`/workspace/${proj.id}`);
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (e.response?.status === 402 && detail?.requires_upgrade_confirmation) {
        setUpgradeModal({ ...detail, enrichedPrompt, extraParams });
        setCreating(false);
        return;
      }
      toast.error(detail || "Failed to create project");
    } finally {
      setCreating(false);
    }
  };

  const create = async (e) => {
    e?.preventDefault();
    if (!name.trim() || !prompt.trim()) {
      toast.error("Name and prompt are required.");
      return;
    }
    if (readiness?.overall !== "PASS") {
      toast.error("GenX readiness must pass before starting Amarktai Coding Agents.");
      return;
    }
    // Phase 1: Check if clarification is needed before launching the build
    try {
      const clarifyResult = await Clarify.check(prompt.trim(), mode);
      if (clarifyResult.needs_clarification && clarifyResult.questions?.length > 0) {
        setClarification({ questions: clarifyResult.questions, assumptions: clarifyResult.assumptions || [] });
        setPendingCreate({ upgradeAcknowledged: false });
        return;
      }
    } catch (err) {
      // If clarification check fails (e.g. backend down), proceed without it
      console.debug("Clarification check failed, proceeding:", err?.message);
    }
    await doCreate(prompt.trim(), false);
  };

  const handleClarificationConfirm = async (answers) => {
    setClarification(null);
    try {
      const res = await Clarify.apply(prompt.trim(), answers);
      await doCreate(res.enriched_prompt, pendingCreate?.upgradeAcknowledged || false, res.params || {});
    } catch (err) {
      console.debug("Clarification apply failed, using original prompt:", err?.message);
      await doCreate(prompt.trim(), pendingCreate?.upgradeAcknowledged || false);
    }
    setPendingCreate(null);
  };

  const handleClarificationSkip = async () => {
    setClarification(null);
    await doCreate(prompt.trim(), pendingCreate?.upgradeAcknowledged || false);
    setPendingCreate(null);
  };

  const handleUpgradeAndCreate = () => {
    const tier = upgradeModal?.recommended_tier;
    const ep = upgradeModal?.enrichedPrompt || prompt;
    const params = upgradeModal?.extraParams || {};
    setUpgradeModal(null);
    if (tier) setQualityTier(tier);
    doCreate(ep, true, params);
  };

  const handleContinueAnyway = () => {
    const ep = upgradeModal?.enrichedPrompt || prompt;
    const params = upgradeModal?.extraParams || {};
    setUpgradeModal(null);
    doCreate(ep, true, params);
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
      {/* Clarification modal — shown before starting a build when prompt is vague */}
      {clarification && (
        <ClarificationModal
          questions={clarification.questions}
          assumptions={clarification.assumptions}
          onConfirm={handleClarificationConfirm}
          onSkip={handleClarificationSkip}
        />
      )}

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
              Start from a prompt or pull in a GitHub repo. Amarktai Coding Agents collaborate,
              files appear in real time, and Amarktai Assistant keeps iteration moving.
            </p>
            <ReadinessStrip readiness={readiness} onRefresh={refreshReadiness} />

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
                    placeholder="e.g. Lead Desk"
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

                  {/* Mode selector */}
                  <FieldLabel>Build mode</FieldLabel>
                  <select
                    data-testid="build-mode-select"
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                    className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg"
                  >
                    <optgroup label="── Static / Marketing ──">
                      <option value="landing_page">Landing page — static, images, hero</option>
                      <option value="website">Website — multi-section, content site</option>
                      <option value="media_page">Media page — image/video/music friendly</option>
                    </optgroup>
                    <optgroup label="── Apps ──">
                      <option value="web_app">Web app — interactive, localStorage</option>
                      <option value="pwa">Progressive Web App (PWA) — installable</option>
                    </optgroup>
                    <optgroup label="── Full Stack / Services ──">
                      <option value="full_stack">Full-stack app — frontend + backend + DB</option>
                      <option value="dashboard">Dashboard — charts, tables, admin UI</option>
                      <option value="admin_panel">Admin panel — CRUD, user management</option>
                      <option value="api_service">API / Backend service — REST + health endpoint</option>
                    </optgroup>
                    <optgroup label="── Bots / Automation ──">
                      <option value="automation_bot">Automation bot — worker/scheduler scaffold</option>
                      <option value="trading_bot_scaffold">Trading bot scaffold — paper mode, risk controls</option>
                    </optgroup>
                    <optgroup label="── Research / Import ──">
                      <option value="research">Research — brief + recommended build prompt</option>
                      <option value="repo_fix">Repo fix — imported repo edits only</option>
                    </optgroup>
                  </select>

                  {/* Quality tier selector */}
                  <FieldLabel>Quality tier</FieldLabel>
                  <div className="grid grid-cols-3 gap-2" data-testid="quality-tier-selector">
                    {[
                      { id: "cheap", label: "Cheap", desc: "Fast · simple · low credit" },
                      { id: "balanced", label: "Balanced", desc: "Recommended · best value" },
                      { id: "premium", label: "Premium", desc: "Best for complex apps" },
                    ].map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        data-testid={`tier-${t.id}`}
                        onClick={() => setQualityTier(t.id)}
                        className={`p-3 border text-left transition-colors duration-150 ${
                          qualityTier === t.id
                            ? "border-amk-accent bg-amk-surface text-white"
                            : "border-amk-line bg-amk-panel text-amk-fg2 hover:bg-amk-surface"
                        }`}
                      >
                        <div className="font-mono text-xs font-medium">{t.label}</div>
                        <div className="text-[10px] text-amk-fg3 leading-relaxed mt-0.5">{t.desc}</div>
                      </button>
                    ))}
                  </div>

                  {/* Phase 3: Media source choice */}
                  <MediaChoiceSelect value={mediaChoice} onChange={setMediaChoice} />

                  <Button data-testid="create-project-btn" type="submit" disabled={creating}
                    className="w-full bg-amk-accent text-black hover:bg-emerald-300 font-mono text-xs h-11 mt-4">
                    {creating ? "STARTING AGENTS..." : "BEGIN BUILD"}
                    <Sparkles className="w-3.5 h-3.5 ml-2" strokeWidth={2} />
                  </Button>
                </form>

                {/* Upgrade confirmation modal */}
                {upgradeModal && (
                  <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
                    <div className="bg-amk-panel border border-amk-line max-w-md w-full p-6 space-y-4">
                      <div className="font-mono text-[10px] uppercase tracking-wider text-agent-scout">[ upgrade suggested ]</div>
                      <p className="text-sm text-amk-fg leading-relaxed">{upgradeModal.upgrade_reason}</p>
                      <p className="text-sm text-amk-fg2">
                        Recommended: <span className="text-white font-mono">{upgradeModal.recommended_tier}</span>
                        {" "}tier for this <span className="text-white">{upgradeModal.complexity}</span> project.
                      </p>
                      <div className="flex gap-2">
                        <Button
                          data-testid="upgrade-confirm-btn"
                          onClick={handleUpgradeAndCreate}
                          className="flex-1 bg-amk-accent text-black hover:bg-emerald-300 font-mono text-xs h-9"
                        >
                          Upgrade to {upgradeModal.recommended_tier}
                        </Button>
                        <Button
                          data-testid="upgrade-continue-btn"
                          onClick={handleContinueAnyway}
                          variant="outline"
                          className="flex-1 font-mono text-xs h-9 border-amk-line hover:bg-amk-surface"
                        >
                          Continue anyway
                        </Button>
                      </div>
                      <button
                        onClick={() => setUpgradeModal(null)}
                        className="w-full text-center font-mono text-[10px] text-amk-fg3 hover:text-white py-1"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
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
                    Public repos import without a token. Private repos, PRs, and repo creation require
                    a GitHub PAT in Settings.
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
              <div className="flex items-center gap-2">
                <button onClick={() => nav("/system")} className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white inline-flex items-center gap-1.5">
                  <Activity className="w-3 h-3" /> health
                </button>
                {user?.role === "admin" && (
                  <button onClick={() => nav("/admin/users")} className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white inline-flex items-center gap-1.5">
                    <Users className="w-3 h-3" /> users
                  </button>
                )}
                <span className="font-mono text-[11px] text-amk-fg3">{projects.length} total</span>
              </div>
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

function ReadinessStrip({ readiness, onRefresh }) {
  const overall = readiness?.overall || "FAIL";
  const genx = readiness?.checks?.find((c) => c.name.toLowerCase().includes("genx"));
  const github = readiness?.checks?.find((c) => c.name === "GitHub PAT");
  const brave = readiness?.checks?.find((c) => c.name === "Brave Search key");
  const color = overall === "PASS" ? "#00E676" : "#FF5722";
  return (
    <div className="border border-amk-line bg-amk-panel p-3 mb-5">
      <div className="flex items-center justify-between gap-3">
        <div className="font-mono text-[10px] uppercase tracking-wider inline-flex items-center gap-2" style={{ color }}>
          <ShieldCheck className="w-3.5 h-3.5" />
          readiness {overall}
        </div>
        <button onClick={onRefresh} className="font-mono text-[10px] text-amk-fg3 hover:text-white uppercase">refresh</button>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 font-mono text-[10px] text-amk-fg3">
        <span>GenX: {genx?.status || "unknown"}</span>
        <span>GitHub: {github?.status === "WARN" ? "optional" : github?.status || "unknown"}</span>
        <span>Brave: {brave?.status === "WARN" ? "optional" : brave?.status || "unknown"}</span>
      </div>
      {readiness?.blockers?.length > 0 && (
        <p className="mt-2 font-mono text-[10px] text-agent-scout">
          Fix: {readiness.blockers[0]}
        </p>
      )}
    </div>
  );
}

function StatusDot({ status }) {
  const colors = { running: "#FFC107", ready: "#00E676", failed: "#FF5722", queued: "#A1A1AA" };
  return <span title={status} className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: colors[status] || "#71717A" }} />;
}

const MEDIA_OPTIONS = [
  {
    id: "auto",
    label: "Auto",
    desc: "Agents pick the best option",
    icon: <Cpu className="w-3.5 h-3.5" strokeWidth={1.5} />,
  },
  {
    id: "AI-generated images (GenX)",
    label: "AI Images",
    desc: "GenX image models",
    icon: <Sparkles className="w-3.5 h-3.5" strokeWidth={1.5} />,
  },
  {
    id: "Stock images from Pixabay",
    label: "Pixabay",
    desc: "Free stock photos/video",
    icon: <Image className="w-3.5 h-3.5" strokeWidth={1.5} />,
  },
  {
    id: "SVG / CSS visuals only (no external images)",
    label: "CSS/SVG only",
    desc: "No external images",
    icon: <Palette className="w-3.5 h-3.5" strokeWidth={1.5} />,
  },
];

function MediaChoiceSelect({ value, onChange }) {
  return (
    <div data-testid="media-choice-selector">
      <label className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 block mb-1.5">
        Media source
      </label>
      <div className="grid grid-cols-2 gap-2">
        {MEDIA_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            data-testid={`media-choice-${opt.id.replace(/[^a-z0-9]/gi, "-").toLowerCase().slice(0, 20)}`}
            onClick={() => onChange(opt.id)}
            className={`p-2.5 border text-left flex items-start gap-2 transition-colors duration-100 ${
              value === opt.id
                ? "border-amk-accent bg-amk-surface text-white"
                : "border-amk-line bg-amk-panel text-amk-fg2 hover:bg-amk-surface"
            }`}
          >
            <span className="mt-0.5 shrink-0">{opt.icon}</span>
            <div>
              <div className="font-mono text-xs font-medium">{opt.label}</div>
              <div className="text-[10px] text-amk-fg3 mt-0.5">{opt.desc}</div>
            </div>
          </button>
        ))}
      </div>
      {value === "Stock images from Pixabay" && (
        <p className="font-mono text-[10px] text-amk-fg3 mt-1.5">
          Requires <span className="text-amk-fg">PIXABAY_API_KEY</span> in Settings. Attribution is shown on all Pixabay assets.
        </p>
      )}
      {value === "AI-generated images (GenX)" && (
        <p className="font-mono text-[10px] text-amk-fg3 mt-1.5">
          Uses GenX image models. Requires balanced/premium tier and explicit confirmation before generating.
        </p>
      )}
    </div>
  );
}
