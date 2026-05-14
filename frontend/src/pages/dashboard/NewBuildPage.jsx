import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Cpu, Image, Palette, Sparkles } from "lucide-react";
import { toast } from "sonner";
import ClarificationModal from "@/components/ClarificationModal";
import CapabilityStatus from "@/components/CapabilityStatus";
import { Button } from "@/components/ui/button";
import { Clarify, Projects, System } from "@/lib/amk-api";
import { readinessBlockMessage, readinessBlocksBuild } from "@/lib/readiness";

const MODES = [
  ["landing_page", "Landing page", "Static, image-rich page"],
  ["website", "Website", "Multi-page content site"],
  ["web_app", "Web app", "Interactive local app"],
  ["pwa", "PWA", "Installable mobile-friendly app"],
  ["dashboard", "Dashboard", "Charts, tables, admin UI"],
  ["full_stack", "Full stack", "Frontend, backend, docs"],
  ["api_service", "API service", "REST API scaffold"],
  ["repo_fix", "Repo fix", "Imported repo changes"],
];

const MEDIA_OPTIONS = [
  ["auto", "Let AI decide", "Use the best configured source and fall back honestly.", Cpu],
  ["AI-generated images (GenX)", "AI images", "Requires GENX_API_KEY and explicit model availability.", Sparkles],
  ["Stock images from Pixabay", "Pixabay stock", "Requires PIXABAY_API_KEY.", Image],
  ["SVG / CSS visuals only (no external images)", "CSS/SVG only", "No external media dependency.", Palette],
];

export default function NewBuildPage() {
  const nav = useNavigate();
  const location = useLocation();
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState("web_app");
  const [qualityTier, setQualityTier] = useState("balanced");
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
    if (state.qualityTier) setQualityTier(state.qualityTier);
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
        quality_tier: qualityTier,
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
    <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
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

      <section className="border border-amk-line bg-amk-panel">
        <div className="border-b border-amk-line p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">New build</div>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-white">Describe the product. Let the system route the build.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-amk-fg2">Prompt-first creation with explicit mode, quality, and media constraints. Provider-backed options stay marked as setup-dependent.</p>
        </div>

        <form onSubmit={create} className="space-y-5 p-5" data-testid="create-project-form">
          <Field label="Project name">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Lead Desk" className="field-input" data-testid="project-name-input" />
          </Field>

          <Field label="Build prompt">
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={7} placeholder="Build a private beta SaaS dashboard with..." className="field-input resize-none leading-6" data-testid="project-prompt-input" />
          </Field>

          <div>
            <Label>Build mode</Label>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {MODES.map(([id, label, desc]) => (
                <button key={id} type="button" onClick={() => setMode(id)} className={`border p-3 text-left ${mode === id ? "border-amk-accent bg-amk-accent/10" : "border-amk-line bg-amk-base hover:bg-amk-surface"}`}>
                  <div className="font-mono text-xs text-white">{label}</div>
                  <div className="mt-1 text-[10px] text-amk-fg3">{desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label>Quality tier</Label>
            <div className="grid gap-2 sm:grid-cols-3">
              {["cheap", "balanced", "premium"].map((tier) => (
                <button key={tier} type="button" onClick={() => setQualityTier(tier)} className={`border p-3 text-left font-mono text-xs capitalize ${qualityTier === tier ? "border-amk-accent bg-amk-accent/10 text-white" : "border-amk-line bg-amk-base text-amk-fg2 hover:bg-amk-surface"}`}>
                  {tier}
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label>Media options</Label>
            <div className="grid gap-2 md:grid-cols-2">
              {MEDIA_OPTIONS.map(([id, label, desc, Icon]) => (
                <button key={id} type="button" onClick={() => setMediaChoice(id)} className={`flex items-start gap-3 border p-3 text-left ${mediaChoice === id ? "border-amk-accent bg-amk-accent/10" : "border-amk-line bg-amk-base hover:bg-amk-surface"}`}>
                  <Icon className="mt-0.5 h-4 w-4 shrink-0 text-amk-accent" />
                  <span>
                    <span className="block font-mono text-xs text-white">{label}</span>
                    <span className="mt-1 block text-[10px] leading-4 text-amk-fg3">{desc}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          <Button type="submit" disabled={creating} className="h-11 w-full bg-amk-accent font-mono text-xs uppercase tracking-wider text-black hover:bg-emerald-300" data-testid="create-project-btn">
            {creating ? "Starting agents..." : "Begin build"} <Sparkles className="ml-2 h-4 w-4" />
          </Button>
        </form>
      </section>

      <aside className="space-y-4">
        <div className="border border-amk-line bg-amk-panel p-4">
          <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Readiness</div>
          <div className="mt-2 font-mono text-sm uppercase tracking-wider" style={{ color: readiness?.overall === "PASS" ? "#00E676" : "#FFC107" }}>
            {readiness?.overall || "Unknown"}
          </div>
          {readiness?.blockers?.length > 0 && <p className="mt-2 text-xs leading-5 text-agent-scout">{readiness.blockers[0]}</p>}
        </div>
        <CapabilityStatus compact />
      </aside>

      {upgradeModal && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4">
          <div className="w-full max-w-md border border-amk-line bg-amk-panel p-5">
            <div className="font-mono text-[10px] uppercase tracking-wider text-agent-scout">Upgrade suggested</div>
            <p className="mt-3 text-sm leading-6 text-amk-fg2">{upgradeModal.upgrade_reason}</p>
            <div className="mt-4 flex gap-2">
              <Button onClick={() => { const data = upgradeModal; setUpgradeModal(null); if (data.recommended_tier) setQualityTier(data.recommended_tier); doCreate(data.enrichedPrompt || prompt, true, data.extraParams || {}); }} className="flex-1 bg-amk-accent text-black hover:bg-emerald-300">
                Use {upgradeModal.recommended_tier}
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
