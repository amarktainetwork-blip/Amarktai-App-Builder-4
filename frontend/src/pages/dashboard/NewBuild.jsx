import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Sparkles,
  Github,
  ShieldCheck,
  Cpu,
  Image,
  Palette,
} from "lucide-react";
import { toast } from "sonner";
import ClarificationModal from "@/components/ClarificationModal";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Projects, System, Clarify } from "@/lib/amk-api";

const PROMPT_TEMPLATES = [
  {
    name: "Lead Desk",
    prompt:
      "Create a worldwide lead-gen PWA called 'Lead Desk' with a bright design, hero search, and a contact-capture form.",
  },
  {
    name: "Pomodoro Focus",
    prompt:
      "Build a minimal pomodoro timer with task list, dark mode, and gentle audio cue at the end of each interval.",
  },
  {
    name: "Cosmic Dashboard",
    prompt:
      "An astronomy 'sky tonight' dashboard showing moon phase, constellation highlights, and tonight's astronomical events.",
  },
  {
    name: "Recipe Roulette",
    prompt:
      "A playful recipe roulette where users spin to get a random dinner idea with ingredients and a 6-step method.",
  },
];

const BUILD_MODE_HINTS = {
  landing_page:
    "A single polished page for a business, product, event, or idea. Fast to build, easy to deploy.",
  website:
    "A complete website with separate pages like Home, About, Services, Pricing, and Contact.",
  media_page:
    "A visual-first page optimized for image galleries, video showcases, or music portfolios.",
  web_app:
    "An interactive browser app with forms, state, local data, or custom workflows.",
  pwa: "An installable app with mobile-friendly layout, home screen icon, and optional offline support.",
  full_stack:
    "Frontend, backend, secure login, dashboard, database notes, Docker deployment, and README.",
  dashboard:
    "A control panel with charts, tables, metric cards, settings, and admin views.",
  admin_panel:
    "A CRUD admin interface with user management, data tables, and access control scaffold.",
  api_service:
    "A backend REST API with routes, health checks, OpenAPI docs, and deployment notes.",
  automation_bot:
    "A worker or scheduler scaffold with job queue, logging, and error handling.",
  trading_bot_scaffold:
    "A paper-trading bot with risk controls, market data hooks, and backtesting scaffold.",
  research:
    "A research brief with target audience, feature opportunities, and a recommended build prompt.",
  repo_fix:
    "Import an existing GitHub repo, analyse it, fix it, and prepare a branch or PR.",
};

const MEDIA_OPTIONS = [
  {
    id: "auto",
    label: "Auto",
    desc: "Use the best available source. AI if available, otherwise Pixabay or SVG.",
    icon: <Cpu className="w-3.5 h-3.5" strokeWidth={1.5} />,
  },
  {
    id: "AI-generated images (GenX)",
    label: "AI Images",
    desc: "Use configured GenX/Qwen image models when available.",
    icon: <Sparkles className="w-3.5 h-3.5" strokeWidth={1.5} />,
  },
  {
    id: "Stock images from Pixabay",
    label: "Pixabay",
    desc: "Use Pixabay stock images/videos. Requires Pixabay API key.",
    icon: <Image className="w-3.5 h-3.5" strokeWidth={1.5} />,
  },
  {
    id: "SVG / CSS visuals only (no external images)",
    label: "CSS/SVG only",
    desc: "No external images. Generate premium CSS/SVG visuals.",
    icon: <Palette className="w-3.5 h-3.5" strokeWidth={1.5} />,
  },
];

const MULTI_PAGE_PATTERN =
  /\b(?:\d\s*pages?|multi[-\s]?page|complete\s+website|full\s+website)\b/i;

export default function NewBuild() {
  const nav = useNavigate();
  const [tab, setTab] = useState("prompt");
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState("web_app");
  const [qualityTier, setQualityTier] = useState("balanced");
  const [mediaChoice, setMediaChoice] = useState("auto");
  const [creating, setCreating] = useState(false);
  const [upgradeModal, setUpgradeModal] = useState(null);
  const [clarification, setClarification] = useState(null);
  const [pendingCreate, setPendingCreate] = useState(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [readiness, setReadiness] = useState(null);

  const refreshReadiness = () =>
    System.readiness()
      .then(setReadiness)
      .catch(() => setReadiness(null));

  useEffect(() => {
    refreshReadiness();
  }, []);

  const doCreate = async (
    enrichedPrompt,
    upgradeAcknowledged = false,
    extraParams = {}
  ) => {
    if (readiness?.overall !== "PASS") {
      toast.error(
        "GenX readiness must pass before starting Amarktai Coding Agents."
      );
      return;
    }
    if (!name.trim() || !enrichedPrompt.trim()) {
      toast.error("Name and prompt are required.");
      return;
    }
    setCreating(true);
    try {
      const mediaRequirements =
        mediaChoice !== "auto" ? mediaChoice : undefined;
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
      if (
        e.response?.status === 402 &&
        detail?.requires_upgrade_confirmation
      ) {
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
      toast.error(
        "GenX readiness must pass before starting Amarktai Coding Agents."
      );
      return;
    }
    try {
      const clarifyResult = await Clarify.check(prompt.trim(), mode);
      if (
        clarifyResult.needs_clarification &&
        clarifyResult.questions?.length > 0
      ) {
        setClarification({
          questions: clarifyResult.questions,
          assumptions: clarifyResult.assumptions || [],
        });
        setPendingCreate({ upgradeAcknowledged: false });
        return;
      }
    } catch (err) {
      console.debug("Clarification check failed, proceeding:", err?.message);
    }
    await doCreate(prompt.trim(), false);
  };

  const handleClarificationConfirm = async (answers) => {
    setClarification(null);
    try {
      const res = await Clarify.apply(prompt.trim(), answers);
      await doCreate(
        res.enriched_prompt,
        pendingCreate?.upgradeAcknowledged || false,
        res.params || {}
      );
    } catch (err) {
      console.debug(
        "Clarification apply failed, using original prompt:",
        err?.message
      );
      await doCreate(
        prompt.trim(),
        pendingCreate?.upgradeAcknowledged || false
      );
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
      const proj = await Projects.fromRepo(
        repoUrl.trim(),
        branch.trim() || null,
        null
      );
      toast.success(`Imported ${proj.name}`);
      nav(`/workspace/${proj.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Import failed");
    } finally {
      setCreating(false);
    }
  };

  const applyTemplate = (t) => {
    setName(t.name);
    setPrompt(t.prompt);
    setTab("prompt");
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="p-6 lg:p-10"
    >
      {clarification && (
        <ClarificationModal
          questions={clarification.questions}
          assumptions={clarification.assumptions}
          onConfirm={handleClarificationConfirm}
          onSkip={handleClarificationSkip}
        />
      )}

      <div className="max-w-2xl">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-3">
          [ new build ]
        </div>
        <h1 className="font-display font-semibold text-3xl lg:text-4xl tracking-tight leading-[1.05] mb-3">
          Describe what{" "}
          <span className="text-amk-fg2">you want to build.</span>
          <br />
          <span className="text-amk-accent">
            Watch agents ship it.
            <span className="blink ml-1" />
          </span>
        </h1>
        <p className="text-sm text-amk-fg2 mb-8 leading-relaxed">
          Describe a landing page, multi-page website, PWA, dashboard, API, or
          SaaS app. Four AI agents plan, code, review, and validate — files
          stream live.
        </p>

        <ReadinessStrip readiness={readiness} onRefresh={refreshReadiness} />

        {/* Template prompts */}
        <div className="mb-5">
          <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-2">
            Quick start
          </div>
          <div className="flex flex-wrap gap-2">
            {PROMPT_TEMPLATES.map((t) => (
              <button
                key={t.name}
                onClick={() => applyTemplate(t)}
                className="px-3 py-1.5 border border-amk-line bg-amk-panel hover:bg-amk-surface font-mono text-[10px] text-amk-fg2 hover:text-white transition-colors"
              >
                {t.name}
              </button>
            ))}
          </div>
        </div>

        <Tabs value={tab} onValueChange={setTab} data-testid="new-build-tabs">
          <TabsList className="bg-transparent p-0 gap-0 border border-amk-line w-full justify-start">
            <TabsTrigger
              value="prompt"
              data-testid="tab-prompt"
              className="font-mono text-[10px] uppercase tracking-wider px-4 h-9 rounded-none border-r border-amk-line data-[state=active]:bg-amk-panel data-[state=active]:text-white data-[state=active]:shadow-none text-amk-fg3 flex-1"
            >
              <Sparkles className="w-3 h-3 mr-1.5" /> Prompt
            </TabsTrigger>
            <TabsTrigger
              value="repo"
              data-testid="tab-repo"
              className="font-mono text-[10px] uppercase tracking-wider px-4 h-9 rounded-none data-[state=active]:bg-amk-panel data-[state=active]:text-white data-[state=active]:shadow-none text-amk-fg3 flex-1"
            >
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

              <FieldLabel>Build mode</FieldLabel>
              <select
                data-testid="build-mode-select"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg"
              >
                <optgroup label="── Static / Marketing ──">
                  <option value="landing_page">
                    Landing page — static, images, hero
                  </option>
                  <option value="website">
                    Website — multi-section, content site
                  </option>
                  <option value="media_page">
                    Media page — image/video/music friendly
                  </option>
                </optgroup>
                <optgroup label="── Apps ──">
                  <option value="web_app">
                    Web app — interactive, localStorage
                  </option>
                  <option value="pwa">
                    Progressive Web App (PWA) — installable
                  </option>
                </optgroup>
                <optgroup label="── Full Stack / Services ──">
                  <option value="full_stack">
                    Full-stack app — frontend + backend + DB
                  </option>
                  <option value="dashboard">
                    Dashboard — charts, tables, admin UI
                  </option>
                  <option value="admin_panel">
                    Admin panel — CRUD, user management
                  </option>
                  <option value="api_service">
                    API / Backend service — REST + health endpoint
                  </option>
                </optgroup>
                <optgroup label="── Bots / Automation ──">
                  <option value="automation_bot">
                    Automation bot — worker/scheduler scaffold
                  </option>
                  <option value="trading_bot_scaffold">
                    Trading bot scaffold — paper mode, risk controls
                  </option>
                </optgroup>
                <optgroup label="── Research / Import ──">
                  <option value="research">
                    Research — brief + recommended build prompt
                  </option>
                  <option value="repo_fix">
                    Repo fix — imported repo edits only
                  </option>
                </optgroup>
              </select>
              <BuildModeHint mode={mode} />
              <MultiPageWarning prompt={prompt} mode={mode} />

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
                    <div className="text-[10px] text-amk-fg3 leading-relaxed mt-0.5">
                      {t.desc}
                    </div>
                  </button>
                ))}
              </div>

              <MediaChoiceSelect value={mediaChoice} onChange={setMediaChoice} />

              <Button
                data-testid="create-project-btn"
                type="submit"
                disabled={creating}
                className="w-full bg-amk-accent text-black hover:bg-emerald-300 font-mono text-xs h-11 mt-4"
              >
                {creating ? "STARTING AGENTS..." : "BEGIN BUILD"}
                <Sparkles className="w-3.5 h-3.5 ml-2" strokeWidth={2} />
              </Button>
            </form>

            {upgradeModal && (
              <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
                <div className="bg-amk-panel border border-amk-line max-w-md w-full p-6 space-y-4">
                  <div className="font-mono text-[10px] uppercase tracking-wider text-agent-scout">
                    [ upgrade suggested ]
                  </div>
                  <p className="text-sm text-amk-fg leading-relaxed">
                    {upgradeModal.upgrade_reason}
                  </p>
                  <p className="text-sm text-amk-fg2">
                    Recommended:{" "}
                    <span className="text-white font-mono">
                      {upgradeModal.recommended_tier}
                    </span>{" "}
                    tier for this{" "}
                    <span className="text-white">{upgradeModal.complexity}</span>{" "}
                    project.
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
            <form
              onSubmit={importRepo}
              className="space-y-3"
              data-testid="import-repo-form"
            >
              <FieldLabel>Public GitHub repo URL</FieldLabel>
              <input
                data-testid="repo-url-input"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
              />
              <FieldLabel>
                Branch{" "}
                <span className="text-amk-fg3 normal-case">
                  (optional — defaults to repo's default)
                </span>
              </FieldLabel>
              <input
                data-testid="repo-branch-input"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="main"
                className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
              />
              <p className="font-mono text-[10px] text-amk-fg3 leading-relaxed">
                Public repos import without a token. Private repos, PRs, and
                repo creation require a GitHub PAT in Settings.
              </p>
              <Button
                data-testid="import-repo-btn"
                type="submit"
                disabled={creating}
                className="w-full bg-white text-black hover:bg-zinc-200 font-mono text-xs h-11 mt-2"
              >
                {creating ? "IMPORTING..." : "IMPORT REPO"}
                <Github className="w-3.5 h-3.5 ml-2" strokeWidth={2} />
              </Button>
            </form>
          </TabsContent>
        </Tabs>
      </div>
    </motion.div>
  );
}

function FieldLabel({ children }) {
  return (
    <label className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 block mb-1.5">
      {children}
    </label>
  );
}

function ReadinessStrip({ readiness, onRefresh }) {
  const overall = readiness?.overall || "FAIL";
  const genx = readiness?.checks?.find((c) =>
    c.name.toLowerCase().includes("genx")
  );
  const github = readiness?.checks?.find((c) => c.name === "GitHub PAT");
  const brave = readiness?.checks?.find((c) => c.name === "Brave Search key");
  const color = overall === "PASS" ? "#00E676" : "#FF5722";
  return (
    <div className="border border-amk-line bg-amk-panel p-3 mb-5">
      <div className="flex items-center justify-between gap-3">
        <div
          className="font-mono text-[10px] uppercase tracking-wider inline-flex items-center gap-2"
          style={{ color }}
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          readiness {overall}
        </div>
        <button
          onClick={onRefresh}
          className="font-mono text-[10px] text-amk-fg3 hover:text-white uppercase"
        >
          refresh
        </button>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 font-mono text-[10px] text-amk-fg3">
        <span>GenX: {genx?.status || "unknown"}</span>
        <span>
          GitHub:{" "}
          {github?.status === "WARN" ? "optional" : github?.status || "unknown"}
        </span>
        <span>
          Brave:{" "}
          {brave?.status === "WARN" ? "optional" : brave?.status || "unknown"}
        </span>
      </div>
      {readiness?.blockers?.length > 0 && (
        <p className="mt-2 font-mono text-[10px] text-agent-scout">
          Fix: {readiness.blockers[0]}
        </p>
      )}
    </div>
  );
}

function BuildModeHint({ mode }) {
  const hint = BUILD_MODE_HINTS[mode];
  if (!hint) return null;
  return (
    <p
      data-testid="build-mode-hint"
      className="font-mono text-[10px] text-amk-fg3 mt-1.5 leading-relaxed"
    >
      {hint}
    </p>
  );
}

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
            data-testid={`media-choice-${opt.id
              .replace(/[^a-z0-9]/gi, "-")
              .toLowerCase()
              .slice(0, 20)}`}
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
          Requires <span className="text-amk-fg">PIXABAY_API_KEY</span> in
          Settings. Attribution is shown on all Pixabay assets.
        </p>
      )}
      {value === "AI-generated images (GenX)" && (
        <p className="font-mono text-[10px] text-amk-fg3 mt-1.5">
          Uses GenX image models. Requires balanced/premium tier and explicit
          confirmation before generating.
        </p>
      )}
    </div>
  );
}

function MultiPageWarning({ prompt, mode }) {
  const needsWarning = MULTI_PAGE_PATTERN.test(prompt) && mode !== "website";
  if (!needsWarning) return null;
  return (
    <p
      data-testid="multi-page-warning"
      className="font-mono text-[10px] mt-1.5 leading-relaxed"
      style={{ color: "#FFC107" }}
    >
      ⚠ Your prompt mentions multiple pages. Consider switching build mode to{" "}
      <strong>Website</strong> for a complete multi-page site with separate
      pages.
    </p>
  );
}
