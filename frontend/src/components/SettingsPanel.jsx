import { useEffect, useState } from "react";
import { Settings as SettingsApi, System } from "@/lib/amk-api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Check, X, Trash2, RefreshCw, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

const QWEN_FIELDS = [
  { key: "QWEN_API_KEY", label: "Qwen API Key", hint: "Optional. Enables Qwen-backed video, audio, voice, and direct provider workflows when configured.", inputType: "password", inputPlaceholder: "Paste key..." },
  { key: "QWEN_BASE_URL", label: "Qwen Base URL", hint: "Optional. Custom Qwen endpoint.", inputType: "text", inputPlaceholder: "https://..." },
  { key: "QWEN_MODEL_CHAT", label: "Qwen Chat Model", hint: "Optional model override.", inputType: "text", inputPlaceholder: "Model ID..." },
  { key: "QWEN_MODEL_CODE", label: "Qwen Code Model", hint: "Optional model override.", inputType: "text", inputPlaceholder: "Model ID..." },
  { key: "QWEN_MODEL_IMAGE", label: "Qwen Image Model", hint: "Optional image model override.", inputType: "text", inputPlaceholder: "Model ID..." },
  { key: "QWEN_MODEL_VIDEO", label: "Qwen Video Model", hint: "Optional. Requires QWEN_API_KEY before video can be used.", inputType: "text", inputPlaceholder: "Model ID..." },
  { key: "QWEN_MODEL_AUDIO", label: "Qwen Audio Model", hint: "Optional. Requires QWEN_API_KEY before audio or voice can be used.", inputType: "text", inputPlaceholder: "Model ID..." },
];

const STATUS_KEYS = [
  { key: "GENX_API_KEY", label: "GenX", capability: "text_generation" },
  { key: "QWEN_API_KEY", label: "Qwen", capability: "video_generation" },
  { key: "GITHUB_PAT", label: "GitHub PAT", capability: "github_integration" },
  { key: "BRAVE_SEARCH_API_KEY", label: "Brave Search", capability: "web_research" },
  { key: "PIXABAY_API_KEY", label: "Pixabay", capability: "stock_media" },
];

export default function SettingsPanel({ active = true, onClose, embedded = false }) {
  const [state, setState] = useState({});
  const [values, setValues] = useState({});
  const [github, setGithub] = useState(null);
  const [capabilities, setCapabilities] = useState(null);
  const [saving, setSaving] = useState(false);

  const setValue = (key, v) => setValues((prev) => ({ ...prev, [key]: v }));

  const refresh = async () => {
    const fresh = await SettingsApi.get();
    setState(fresh);
    Promise.allSettled([System.githubStatus(), System.capabilitiesStatus()]).then(([gh, caps]) => {
      setGithub(gh.status === "fulfilled" ? gh.value : null);
      setCapabilities(caps.status === "fulfilled" ? caps.value : null);
    });
  };

  useEffect(() => {
    if (active) refresh().catch(() => toast.error("Failed to load settings"));
  }, [active]);

  const save = async () => {
    setSaving(true);
    try {
      const dirty = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""));
      if (Object.keys(dirty).length === 0) {
        toast.message("No changes to save.");
      } else {
        await SettingsApi.update(dirty);
        toast.success("Settings updated.");
        setValues({});
        await refresh();
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const clear = async (key) => {
    try {
      await SettingsApi.clear(key);
      toast.success("Setting cleared.");
      await refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to clear setting");
    }
  };

  return (
    <div data-testid="settings-panel" className={`flex min-h-0 flex-col ${embedded ? "h-full" : ""}`}>
      <div className="shrink-0 border-b border-amk-line px-5 py-4">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Settings / Integrations</div>
        <h1 className="mt-1 font-display text-2xl font-semibold tracking-tight text-white">Provider and runtime setup</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-amk-fg2">
          Secret fields show live configuration state. Missing provider keys are shown as Requires setup or Not configured; the UI does not claim those capabilities are available.
        </p>
      </div>

      <ProviderSummary settings={state} capabilities={capabilities} />

      <Tabs defaultValue="ai" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="h-auto shrink-0 justify-start gap-0 overflow-x-auto rounded-none border-b border-amk-line bg-transparent p-0">
          {[
            { v: "ai", label: "AI Providers" },
            { v: "media", label: "Media" },
            { v: "github", label: "GitHub" },
            { v: "search", label: "Search" },
            { v: "system", label: "System" },
          ].map(({ v, label }) => (
            <TabsTrigger
              key={v}
              value={v}
              className="h-10 shrink-0 rounded-none border-r border-amk-line px-4 font-mono text-[10px] uppercase tracking-wider text-amk-fg3 data-[state=active]:bg-amk-base data-[state=active]:text-white data-[state=active]:shadow-none"
            >
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="ai" className="m-0 flex-1 space-y-5 overflow-y-auto p-5">
          <SettingRow
            fieldKey="GENX_API_KEY"
            label="GenX API Key"
            hint="Required for Amarktai Coding Agents, reasoning, text generation, image generation, and repo analysis."
            optional={false}
            info={state.GENX_API_KEY || {}}
            value={values.GENX_API_KEY}
            onChange={(v) => setValue("GENX_API_KEY", v)}
            onClear={clear}
          />
          <div className="border-t border-amk-line pt-4">
            <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Qwen optional provider</div>
            <div className="grid gap-4 md:grid-cols-2">
              {QWEN_FIELDS.map((field) => (
                <SettingRow
                  key={field.key}
                  fieldKey={field.key}
                  label={field.label}
                  hint={field.hint}
                  optional
                  info={state[field.key] || {}}
                  value={values[field.key]}
                  onChange={(v) => setValue(field.key, v)}
                  onClear={clear}
                  inputType={field.inputType}
                  inputPlaceholder={field.inputPlaceholder}
                />
              ))}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="media" className="m-0 flex-1 space-y-4 overflow-y-auto p-5">
          <SettingRow
            fieldKey="PIXABAY_API_KEY"
            label="Pixabay API Key"
            hint="Optional. Enables stock image and video search. Without it, stock media is Not configured."
            optional
            info={state.PIXABAY_API_KEY || {}}
            value={values.PIXABAY_API_KEY}
            onChange={(v) => setValue("PIXABAY_API_KEY", v)}
            onClear={clear}
          />
          <CapabilityNote label="AI media" capability={capabilities?.summary?.image_generation} />
          <CapabilityNote label="Qwen video/audio" capability={capabilities?.summary?.video_generation || capabilities?.summary?.voice_generation} />
        </TabsContent>

        <TabsContent value="github" className="m-0 flex-1 space-y-4 overflow-y-auto p-5">
          <SettingRow
            fieldKey="GITHUB_PAT"
            label="GitHub Personal Access Token"
            hint="Optional. Required for private repo import, PR opening, and repo creation."
            optional
            info={state.GITHUB_PAT || {}}
            value={values.GITHUB_PAT}
            onChange={(v) => setValue("GITHUB_PAT", v)}
            onClear={clear}
          />
          <GithubStatusBlock github={github} onRefresh={refresh} showBadge />
        </TabsContent>

        <TabsContent value="search" className="m-0 flex-1 space-y-4 overflow-y-auto p-5">
          <SettingRow
            fieldKey="BRAVE_SEARCH_API_KEY"
            label="Brave Search API Key"
            hint="Optional. Enables web research. Without it, research is limited to configured model knowledge."
            optional
            info={state.BRAVE_SEARCH_API_KEY || {}}
            value={values.BRAVE_SEARCH_API_KEY}
            onChange={(v) => setValue("BRAVE_SEARCH_API_KEY", v)}
            onClear={clear}
          />
        </TabsContent>

        <TabsContent value="system" className="m-0 flex-1 space-y-4 overflow-y-auto p-5">
          <GithubStatusBlock github={github} onRefresh={refresh} showBadge />
          <div className="grid gap-2 md:grid-cols-2">
            {Object.entries(capabilities?.summary || {}).map(([key, value]) => (
              <CapabilityRow key={key} name={key} capability={value} />
            ))}
          </div>
        </TabsContent>
      </Tabs>

      <div className="flex shrink-0 items-center justify-end gap-2 border-t border-amk-line px-5 py-3">
        {onClose && (
          <Button type="button" variant="ghost" onClick={onClose} className="h-9 font-mono text-xs hover:bg-amk-surface">
            Close
          </Button>
        )}
        <Button data-testid="settings-save-btn" onClick={save} disabled={saving} className="h-9 bg-white font-mono text-xs text-black hover:bg-zinc-200">
          {saving ? "Saving..." : "Save"}
        </Button>
      </div>
    </div>
  );
}

function ProviderSummary({ settings, capabilities }) {
  return (
    <div className="grid shrink-0 gap-px border-b border-amk-line bg-amk-line md:grid-cols-5">
      {STATUS_KEYS.map(({ key, label, capability }) => {
        const configured = !!settings[key]?.configured;
        const cap = capabilities?.summary?.[capability];
        const status = capabilityStatusLabel(cap, configured, key === "GENX_API_KEY");
        return (
          <div key={key} className="bg-amk-panel px-4 py-3">
            <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{label}</div>
            <StatusText status={status} />
          </div>
        );
      })}
    </div>
  );
}

function capabilityStatusLabel(capability, configured, required = false) {
  if (capability?.live_status === "key_present_live_ok") return "Available";
  if (capability?.live_status === "key_present_live_fail" || capability?.live_status === "provider_timeout") return "Live check failed";
  if (configured || capability?.configured) return "Configured / not live tested";
  if (capability?.available) return "Available";
  return required ? "Requires setup" : "Not configured";
}

function StatusText({ status }) {
  const color = status === "Available" ? "#00E676" : status === "Live check failed" ? "#FF5722" : status === "Coming soon" ? "#A1A1AA" : "#FFC107";
  return <div className="mt-1 font-mono text-xs uppercase tracking-wider" style={{ color }}>{status}</div>;
}

function CapabilityRow({ name, capability }) {
  const status = capability?.available ? "Available" : capability?.coming_soon ? "Coming soon" : "Requires setup";
  return (
    <div className="border border-amk-line bg-amk-base p-3">
      <div className="font-mono text-[11px] uppercase tracking-wider text-white">{name.replace(/_/g, " ")}</div>
      <StatusText status={status} />
      {capability?.reason && <p className="mt-2 text-xs leading-5 text-amk-fg3">{capability.reason}</p>}
    </div>
  );
}

function CapabilityNote({ label, capability }) {
  const status = capability?.available ? "Available" : "Requires setup";
  return (
    <div className="border border-amk-line bg-amk-base p-3">
      <div className="font-mono text-xs text-amk-fg">{label}</div>
      <StatusText status={status} />
      {capability?.reason && <p className="mt-1 font-mono text-[10px] text-amk-fg3">{capability.reason}</p>}
    </div>
  );
}

function SettingRow({ fieldKey, label, hint, optional, info, value, onChange, onClear, inputType = "password", inputPlaceholder }) {
  const [show, setShow] = useState(false);
  const isSet = !!info?.configured;
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label className="flex items-center gap-1.5 font-mono text-xs tracking-tight">
          {label}
          {optional
            ? <span className="text-[10px] font-normal normal-case text-amk-fg3">optional</span>
            : <span className="text-[10px] font-normal normal-case text-agent-scout">required</span>}
        </Label>
        <span
          data-testid={`setting-status-${fieldKey}`}
          className="inline-flex shrink-0 items-center gap-1 font-mono text-[10px] uppercase tracking-wider"
          style={{ color: isSet ? "#00E676" : optional ? "#FFC107" : "#FF5722" }}
        >
          {isSet ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
          {isSet ? `${info.source || "set"} / ${info.preview}` : optional ? "not configured" : "requires setup"}
        </span>
      </div>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input
            data-testid={`setting-input-${fieldKey}`}
            type={inputType === "password" ? (show ? "text" : "password") : inputType}
            placeholder={isSet ? "Replace value..." : (inputPlaceholder || "Paste key...")}
            value={value || ""}
            onChange={(e) => onChange(e.target.value)}
            className="h-9 border-amk-line bg-amk-base pr-8 font-mono text-xs text-amk-fg focus-visible:border-white focus-visible:ring-0"
          />
          {inputType === "password" && (
            <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-2 top-1/2 -translate-y-1/2 text-amk-fg3 hover:text-white" tabIndex={-1}>
              {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            </button>
          )}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={!isSet || info?.source === "env"}
          onClick={() => onClear(fieldKey)}
          title={info?.source === "env" ? "Environment values must be removed on the server" : "Clear saved value"}
          className="h-9 shrink-0 border border-amk-line px-2"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      <p className="font-mono text-[10px] leading-5 text-amk-fg3">{hint}</p>
    </div>
  );
}

function GithubStatusBlock({ github, onRefresh, showBadge = false }) {
  const good = github?.status === "ok" || github?.valid || github?.detail?.includes("Authenticated");
  return (
    <div className="border border-amk-line bg-amk-base p-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-xs text-amk-fg">GitHub status</div>
        <Button type="button" variant="ghost" size="sm" onClick={onRefresh} className="h-7 px-2">
          <RefreshCw className="h-3 w-3" />
        </Button>
      </div>
      <p className="mt-1 font-mono text-[10px] text-amk-fg3">
        {github?.detail || "GitHub status has not been checked yet."}
      </p>
      {showBadge && github && (
        <div className="mt-2 font-mono text-[10px]">
          <span className="inline-flex items-center gap-1 uppercase tracking-wider" style={{ color: good ? "#00E676" : "#FFC107" }}>
            {good ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
            {good ? "available" : "requires setup"}
          </span>
        </div>
      )}
    </div>
  );
}
