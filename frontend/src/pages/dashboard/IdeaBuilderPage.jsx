import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Lightbulb, Loader2, Send, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { IdeaBuilder } from "@/lib/amk-api";

const MODES = [
  ["website", "Website"],
  ["landing_page", "Landing page"],
  ["web_app", "Web app"],
  ["dashboard", "Dashboard"],
  ["full_stack", "Full stack"],
  ["api_service", "API service"],
];

export default function IdeaBuilderPage() {
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState(null);
  const [projectName, setProjectName] = useState("");
  const [mode, setMode] = useState("website");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([]);
  const [finalPrompt, setFinalPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [finalizing, setFinalizing] = useState(false);

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const session = await IdeaBuilder.createSession({ mode });
    setSessionId(session.id);
    setMessages(session.messages || []);
    return session.id;
  };

  const send = async (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setBusy(true);
    setFinalPrompt("");
    try {
      const id = await ensureSession();
      setMessages((current) => [...current, { role: "user", content: text, id: `local-${Date.now()}` }]);
      setDraft("");
      const result = await IdeaBuilder.sendMessage(id, text);
      setMessages(result.messages || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Idea Builder could not respond.");
    } finally {
      setBusy(false);
    }
  };

  const finalize = async () => {
    setFinalizing(true);
    try {
      const id = await ensureSession();
      const result = await IdeaBuilder.finalize(id, { project_name: projectName || undefined, mode });
      setFinalPrompt(result.final_prompt || "");
      toast.success("Build prompt generated.");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not finalize prompt.");
    } finally {
      setFinalizing(false);
    }
  };

  const startBuild = () => {
    if (!finalPrompt.trim()) return;
    navigate("/dashboard/new", {
      state: {
        ideaPrompt: finalPrompt,
        projectName: projectName || "Idea Builder Project",
        mode,
        qualityTier: "premium",
        mediaChoice: "auto",
        ideaBuilderSessionId: sessionId,
      },
    });
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="border border-amk-line bg-amk-panel">
        <div className="border-b border-amk-line p-5">
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">
            <Lightbulb className="h-4 w-4 text-amk-accent" /> Idea Builder
          </div>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-white">Shape a rough idea into a build-ready prompt.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-amk-fg2">Chat through product, audience, workflow, design, and launch details. When ready, generate a prompt for the main Amarktai build pipeline.</p>
        </div>

        <div className="grid min-h-[520px] grid-rows-[1fr_auto]">
          <div className="space-y-3 overflow-y-auto p-5">
            {messages.length === 0 && (
              <div className="border border-dashed border-amk-line bg-amk-base p-5 text-sm leading-6 text-amk-fg2">
                Try: “I want a cinematic website for an AI software factory that helps agencies ship client apps faster.”
              </div>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`max-w-3xl border p-4 text-sm leading-6 ${
                  message.role === "user"
                    ? "ml-auto border-amk-accent/40 bg-amk-accent/10 text-white"
                    : "border-amk-line bg-amk-base text-amk-fg2"
                }`}
              >
                <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{message.role}</div>
                <div className="whitespace-pre-wrap">{message.content}</div>
              </div>
            ))}
          </div>

          <form onSubmit={send} className="border-t border-amk-line p-4">
            <div className="flex gap-2">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={3}
                placeholder="Describe the idea, audience, workflow, or look you want..."
                className="field-input resize-none leading-6"
              />
              <Button type="submit" disabled={busy || !draft.trim()} className="h-auto w-14 bg-amk-accent text-black hover:bg-emerald-300" title="Send">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </form>
        </div>
      </section>

      <aside className="space-y-4">
        <div className="border border-amk-line bg-amk-panel p-4">
          <Label>Project name</Label>
          <input value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="Amarktai Builder" className="field-input" />

          <div className="mt-4">
            <Label>Build mode</Label>
            <div className="grid grid-cols-2 gap-2">
              {MODES.map(([id, label]) => (
                <button key={id} type="button" onClick={() => setMode(id)} className={`border p-3 text-left font-mono text-[10px] uppercase tracking-wider ${mode === id ? "border-amk-accent bg-amk-accent/10 text-amk-accent" : "border-amk-line bg-amk-base text-amk-fg3 hover:bg-amk-surface"}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          <Button onClick={finalize} disabled={finalizing || busy} className="mt-4 h-11 w-full bg-amk-accent font-mono text-xs uppercase tracking-wider text-black hover:bg-emerald-300">
            {finalizing ? "Generating..." : "Generate build prompt"} <Sparkles className="ml-2 h-4 w-4" />
          </Button>
        </div>

        {finalPrompt && (
          <div className="border border-amk-line bg-amk-panel p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Final prompt</div>
            <div className="mt-3 max-h-72 overflow-y-auto whitespace-pre-wrap border border-amk-line bg-amk-base p-3 text-xs leading-5 text-amk-fg2">
              {finalPrompt}
            </div>
            <Button onClick={startBuild} className="mt-3 h-10 w-full bg-white text-black hover:bg-amk-fg2">
              Use in New Build <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        )}
      </aside>
    </div>
  );
}

function Label({ children }) {
  return <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{children}</label>;
}
