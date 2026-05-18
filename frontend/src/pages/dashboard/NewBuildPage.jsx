import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Cpu, Image, Palette, Sparkles } from "lucide-react";
import { toast } from "sonner";
import ClarificationModal from "@/components/ClarificationModal";
import CapabilityStatus from "@/components/CapabilityStatus";
import { Button } from "@/components/ui/button";
import { Clarify, Projects, System } from "@/lib/amk-api";
import { readinessBlockMessage, readinessBlocksBuild } from "@/lib/readiness";
import { QUALITY_TIERS, normalizeQualityTier, tierLabel } from "@/lib/tiers";

const MODES = [
  ["landing_page", "Landing Page", "A polished one-page website"],
  ["website", "Website", "Multi-page content site"],
  ["pwa", "PWA", "Installable mobile-friendly app"],
  ["web_app", "Web App", "Interactive local app"],
  ["dashboard", "Dashboard", "Charts, tables, admin UI"],
  ["full_stack", "Full-Stack App", "Frontend, backend, docs"],
  ["api_service", "API Service", "REST API scaffold"],
  ["repo_fix", "Repo Fix", "Imported repo changes"],
  ["automation_bot", "Automation Bot", "Worker or scheduler scaffold"],
  ["admin_panel", "Admin/Internal Tool", "Internal CRUD and operations UI"],
  ["ecommerce_scaffold", "Ecommerce Scaffold", "Catalog, cart, checkout scaffold"],
  ["booking_portal", "Booking/Portal", "Booking flow and customer portal"],
  ["ai_chat_rag_app", "AI Chat/RAG App", "Chat, retrieval, and knowledge UX"],
  ["crm_dashboard", "CRM/Dashboard", "Pipeline, accounts, and reporting"],
];

const MEDIA_OPTIONS = [
  ["auto", "Auto", "Use the best live source and label fallbacks honestly.", Cpu],
  ["ai", "AI media", "Use configured GenX/Qwen media providers when live.", Sparkles],
  ["pixabay", "Stock/free media", "Use Pixabay stock media when available.", Image],
  ["css_svg", "CSS/SVG only", "No external media dependency.", Palette],
  ["uploaded", "Uploaded media", "Use assets you provide through Media Studio.", Image],
];

export default function NewBuildPage() {
  const nav = useNavigate();
  const location = useLocation();
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState("landing_page");
  const [qualityTier, setQualityTier] = useState("standard");
  const [mediaChoice, setMediaChoice] = useState("auto");
  const [readiness, setReadiness] = useState(null);
  const [creating, setCreating] = useState(false);
  const [upgradeModal, setUpgradeModal] = useState(null);
  const [clarification, setClarification] = useState(null);
  const [pendingCreate, setPendingCreate] = useState(null);

  useEffect(() => { System.readiness().then(setReadiness).catch(() => setReadiness(null)); }, []);
  useEffect(() => {
    const state = location.state || {};
    if (state.ideaPrompt) setPrompt(state.ideaPrompt);
    if (state.projectName) setName(state.projectName);
    if (state.mode) setMode(state.mode);
    if (state.qualityTier) setQualityTier(normalizeQualityTier(state.qualityTier));
    if (state.mediaChoice) setMediaChoice(state.mediaChoice);
  }, [location.state]);

  const doCreate = async (enrichedPrompt, upgradeAcknowledged = false, extraParams = {}) => {
    if (readinessBlocksBuild(readiness)) {
      toast.error(readinessBlockMessage(readiness));
      return;
    }
    if (!name.trim() || !enrichedPrompt.trim()) {
      toast.error("Name and prompt are required.");
      return;
    }
    setCreating(true);
    try {
      const proj = await Projects.create(name.trim(), enrichedPrompt.trim(), {
        mode,
        quality_tier: normalizeQualityTier(qualityTier),
        upgrade_confirmation_acknowledged: upgradeAcknowledged,
        media_requirements: mediaChoice !== "auto" ? mediaChoice : undefined,
        ...extraParams,
      });
      toast.success("Agents launched.");
      nav(`/workspace/${proj.id}`);
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (e.response?.status === 402 && detail?.requires_upgrade_confirmation) {
        setUpgradeModal({ ...detail, enrichedPrompt, extraParams });
        return;
      }
      toast.error(detail || "Failed to create project");
    } finally {
      setCreating(false);
    }
  };

  const create = async (e) => {
    e.preventDefault();
    if (!name.trim() || !prompt.trim()) {
      toast.error("Name and prompt are required.");
      return;
    }
    try {
      const result = await Clarify.check(prompt.trim(), mode);
      if (result.needs_clarification && result.questions?.length) {
        setClarification({ questions: result.questions, assumptions: result.assumptions || [] });
        setPendingCreate({ upgradeAcknowledged: false });
        return;
      }
    } catch {
      /* clarification is advisory; backend creation remains source of truth */
    }
    await doCreate(prompt.trim(), false);
  };

  const handleClarificationConfirm = async (answers) => {
    setClarification(null);
    try {
      const res = await Clarify.apply(prompt.trim(), answers);
      await doCreate(res.enriched_prompt, pendingCreate?.upgradeAcknowledged || false, res.params || {});
    } catch {
      await doCreate(prompt.trim(), pendingCreate?.upgradeAcknowledged || false);
    }
    setPendingCreate(null);
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_390px]">
      {clarification && (
        <ClarificationModal
          questions={clarification.questions}
          assumptions={clarification.assumptions}
          onConfirm={handleClarificationConfirm}
          onSkip={() => {
            setClarification(null);
            doCreate(prompt.trim(), pendingCreate?.upgradeAcknowledged || false);
            setPendingCreate(null);
          }}
        />
      )}

      <section className="premium-card overflow-hidden rounded-3xl">
        <div className="border-b border-amk-line p-6">
          <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-accent">New build</div>
          <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight text-white md:text-5xl">Describe the product. Aiva routes the build.</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-amk-fg2">Aiva plans it, designs it, builds it, tests it, repairs it, and prepares it for launch. Provider-backed media stays truth-gated.</p>
        </div>

        <form onSubmit={create} className="space-y-6 p-6" data-testid="create-project-form">
          <Field label="Project name">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Aiva Revenue Ops" className="field-input rounded-2xl" data-testid="project-name-input" />
          </Field>

          <Field label="Build prompt">
            <div className="rounded-3xl border border-amk-line bg-amk-base/70 p-3">
              <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={8} placeholder="Build a cinematic landing page for a private AI operations platform with hero, product sections, proof, media treatment, runtime truth badges, and a strong access CTA." className="min-h-56 w-full resize-none rounded-2xl border border-amk-line bg-[#030712] px-4 py-4 text-sm leading-7 text-white outline-none placeholder:text-amk-fg3 focus:border-amk-accent" data-testid="project-prompt-input" />
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                {["Build a cinematic landing page for...", "Build a SaaS dashboard for...", "Import this repo and fix..."].map((example) => (
                  <button key={example} type="button" onClick={() => setPrompt(example)} className="rounded-2xl border border-amk-line px-3 py-2 text-left text-xs text-amk-fg3 hover:border-amk-accent hover:text-white">{example}</button>
                ))}
              </div>
            </div>
          </Field>

          <div>
            <Label>Build mode</Label>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {MODES.map(([id, label, desc]) => (
                <button key={id} type="button" onClick={() => setMode(id)} className={`rounded-2xl border p-3 text-left transition ${mode === id ? "border-amk-accent bg-amk-accent/10 shadow-[0_0_28px_rgba(34,211,238,.12)]" : "border-amk-line bg-amk-base/70 hover:bg-amk-surface"}`}>
                  <div className="font-mono text-xs text-white">{label}</div>
                  <div className="mt-1 text-[10px] text-amk-fg3">{desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label>Quality tier</Label>
            <div className="grid gap-2 sm:grid-cols-2" data-testid="quality-tier-selector">
              {QUALITY_TIERS.map((tier) => (
                <button key={tier.id} type="button" data-testid={`tier-${tier.id}`} onClick={() => setQualityTier(tier.id)} className={`rounded-2xl border p-3 text-left transition ${qualityTier === tier.id ? "border-amk-violet bg-amk-violet/10 text-white" : "border-amk-line bg-amk-base/70 text-amk-fg2 hover:bg-amk-surface"}`}>
                  <span className="block font-mono text-xs">{tier.label}</span>
                  <span className="mt-1 block text-[10px] leading-4 text-amk-fg3">{tier.description}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label>Media options</Label>
            <div className="grid gap-2 md:grid-cols-2">
              {MEDIA_OPTIONS.map(([id, label, desc, Icon]) => (
                <button key={id} type="button" onClick={() => setMediaChoice(id)} className={`flex items-start gap-3 rounded-2xl border p-3 text-left transition ${mediaChoice === id ? "border-amk-magenta bg-amk-magenta/10" : "border-amk-line bg-amk-base/70 hover:bg-amk-surface"}`}>
                  <Icon className="mt-0.5 h-4 w-4 shrink-0 text-amk-accent" />
                  <span>
                    <span className="block font-mono text-xs text-white">{label}</span>
                    <span className="mt-1 block text-[10px] leading-4 text-amk-fg3">{desc}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-3xl border border-amk-line bg-amk-base/70 p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">What happens next</div>
            <p className="mt-2 text-xs leading-5 text-amk-fg2">
              Planner, Scout, Architect, Coder, Reviewer, Media, Motion, Runtime QA, and deployment gates run in order. Failures show a clear next action in the workspace.
            </p>
          </div>

          <Button type="submit" disabled={creating} className="h-12 w-full rounded-2xl bg-gradient-to-r from-amk-accent via-amk-blue to-amk-violet font-mono text-xs uppercase tracking-wider text-amk-base hover:opacity-95" data-testid="create-project-btn">
            {creating ? "Starting agents..." : "Begin build"} <Sparkles className="ml-2 h-4 w-4" />
          </Button>
        </form>
      </section>

      <aside className="space-y-4">
        <div className="glass-panel rounded-3xl p-5">
          <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Readiness</div>
          <div className="mt-2 font-mono text-sm uppercase tracking-wider" style={{ color: readiness?.overall === "PASS" ? "#00E676" : "#FFC107" }}>
            {readiness?.overall || "Unknown"}
          </div>
          {readiness?.blockers?.length > 0 && <p className="mt-2 text-xs leading-5 text-agent-scout">{readiness.blockers[0]}</p>}
        </div>
        <div className="glass-panel rounded-3xl p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Aiva build sequence</div>
          <div className="mt-4 space-y-2">
            {["Clarify intent", "Plan product architecture", "Design interface", "Generate files", "Apply media policy", "Preview and QA", "Repair and gate"].map((item, index) => (
              <div key={item} className="flex items-center gap-3 rounded-2xl bg-amk-base/70 p-3">
                <span className="grid h-7 w-7 place-items-center rounded-xl bg-amk-accent/15 font-mono text-[10px] text-amk-accent">{index + 1}</span>
                <span className="text-xs text-amk-fg2">{item}</span>
              </div>
            ))}
          </div>
        </div>
        <CapabilityStatus compact />
      </aside>

      {upgradeModal && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4">
          <div className="w-full max-w-md border border-amk-line bg-amk-panel p-5">
            <div className="font-mono text-[10px] uppercase tracking-wider text-agent-scout">Better fit suggested</div>
            <p className="mt-3 text-sm leading-6 text-amk-fg2">{upgradeModal.upgrade_reason}</p>
            <div className="mt-4 flex gap-2">
              <Button onClick={() => { const data = upgradeModal; setUpgradeModal(null); if (data.recommended_tier) setQualityTier(normalizeQualityTier(data.recommended_tier)); doCreate(data.enrichedPrompt || prompt, true, data.extraParams || {}); }} className="flex-1 bg-amk-accent text-black hover:bg-emerald-300">
                Use {tierLabel(upgradeModal.recommended_tier)}
              </Button>
              <Button variant="outline" onClick={() => { const data = upgradeModal; setUpgradeModal(null); doCreate(data.enrichedPrompt || prompt, true, data.extraParams || {}); }} className="flex-1 border-amk-line">
                Continue
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return <div><Label>{label}</Label>{children}</div>;
}

function Label({ children }) {
  return <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{children}</label>;
}
