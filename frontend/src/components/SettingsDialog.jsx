import { useEffect, useState } from "react";
import { Settings as SettingsApi, System } from "@/lib/amk-api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Check, X, Trash2, RefreshCw, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

const QWEN_FIELDS = [
  { key: "QWEN_API_KEY",      label: "Qwen API Key",      hint: "Optional. Direct Qwen access for chat, coding, reasoning, and media.",    inputType: "password", inputPlaceholder: "Paste key..." },
  { key: "QWEN_BASE_URL",     label: "Qwen Base URL",     hint: "Optional. Custom Qwen endpoint.",                                          inputType: "text",     inputPlaceholder: "https://..." },
  { key: "QWEN_MODEL_CHAT",   label: "Qwen Chat Model",   hint: "Optional. e.g. qwen-turbo",                                                inputType: "text",     inputPlaceholder: "Model ID..." },
  { key: "QWEN_MODEL_CODE",   label: "Qwen Code Model",   hint: "Optional. e.g. qwen-coder-turbo",                                          inputType: "text",     inputPlaceholder: "Model ID..." },
  { key: "QWEN_MODEL_IMAGE",  label: "Qwen Image Model",  hint: "Optional. e.g. wanx-v1",                                                   inputType: "text",     inputPlaceholder: "Model ID..." },
  { key: "QWEN_MODEL_VIDEO",  label: "Qwen Video Model",  hint: "Optional. Configure if Qwen video generation is available.",               inputType: "text",     inputPlaceholder: "Model ID..." },
  { key: "QWEN_MODEL_AUDIO",  label: "Qwen Audio Model",  hint: "Optional. Configure if Qwen voice/audio generation is available.",         inputType: "text",     inputPlaceholder: "Model ID..." },
];

function SettingRow({ fieldKey, label, hint, optional, info, value, onChange, onClear, inputType = "password", inputPlaceholder }) {
  const [show, setShow] = useState(false);
  const isSet = !!info?.configured;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <Label className="font-mono text-xs tracking-tight flex items-center gap-1.5">
          {label}
          {optional
            ? <span className="text-amk-fg3 normal-case font-normal">(optional)</span>
            : <span className="text-agent-scout normal-case font-normal text-[10px]">required</span>}
        </Label>
        <span
          data-testid={`setting-status-${fieldKey}`}
          className="font-mono text-[10px] uppercase tracking-wider inline-flex items-center gap-1 shrink-0"
          style={{ color: isSet ? "#00E676" : optional ? "#888888" : "#FF5722" }}
        >
          {isSet ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
          {isSet ? `${info.source || "set"} / ${info.preview}` : "not configured"}
        </span>
      </div>
      <div className="flex gap-2">
        <div className="flex-1 relative">
          <Input
            data-testid={`setting-input-${fieldKey}`}
            type={inputType === "password" ? (show ? "text" : "password") : inputType}
            placeholder={isSet ? "Replace value..." : (inputPlaceholder || "Paste key...")}
            value={value || ""}
            onChange={(e) => onChange(e.target.value)}
            className="bg-amk-base border-amk-line text-amk-fg font-mono text-xs h-9 focus-visible:ring-0 focus-visible:border-white pr-8"
          />
          {inputType === "password" && (
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-amk-fg3 hover:text-white"
              tabIndex={-1}
            >
              {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
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
          className="h-9 px-2 border border-amk-line shrink-0"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </Button>
      </div>
      <p className="font-mono text-[10px] text-amk-fg3">{hint}</p>
    </div>
  );
}

function GithubStatusBlock({ github, onRefresh, showBadge = false }) {
  return (
    <div className="border border-amk-line bg-amk-base p-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-xs text-amk-fg">GitHub status</div>
        <Button type="button" variant="ghost" size="sm" onClick={onRefresh} className="h-7 px-2">
          <RefreshCw className="w-3 h-3" />
        </Button>
      </div>
      <p className="mt-1 font-mono text-[10px] text-amk-fg3">
        {github?.detail || "GitHub status has not been checked yet."}
      </p>
      {showBadge && github && (
        <div className="mt-2 font-mono text-[10px]">
          <span
            className="inline-flex items-center gap-1 uppercase tracking-wider"
            style={{ color: github.status === "ok" || github.detail?.includes("Authenticated") ? "#00E676" : "#FF5722" }}
          >
            {github.status === "ok" || github.detail?.includes("Authenticated")
              ? <Check className="w-3 h-3" />
              : <X className="w-3 h-3" />}
            {github.status || "unknown"}
          </span>
        </div>
      )}
    </div>
  );
}

export default function SettingsDialog({ open, onOpenChange }) {
  const [state, setState] = useState({});
  const [values, setValues] = useState({});
  const [github, setGithub] = useState(null);
  const [saving, setSaving] = useState(false);

  const setValue = (key, v) => setValues((prev) => ({ ...prev, [key]: v }));

  const refresh = async () => {
    const fresh = await SettingsApi.get();
    setState(fresh);
    System.githubStatus().then(setGithub).catch(() => setGithub(null));
  };

  useEffect(() => {
    if (open) refresh().catch(() => toast.error("Failed to load settings"));
  }, [open]);

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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="settings-dialog"
        className="bg-amk-panel border border-amk-line text-amk-fg max-w-2xl w-full p-0 rounded-md flex flex-col"
        style={{ maxHeight: "90vh" }}
      >
        {/* Sticky header */}
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-amk-line shrink-0">
          <DialogTitle className="font-mono text-sm tracking-tight uppercase">// Settings / Integrations</DialogTitle>
          <DialogDescription className="font-mono text-[11px] text-amk-fg3">
            Secrets are encrypted in MongoDB. Only GENX_API_KEY is required — all other keys are optional.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="ai" className="flex flex-col flex-1 min-h-0">
          {/* Sticky tab bar */}
          <TabsList className="bg-transparent p-0 gap-0 border-b border-amk-line w-full justify-start rounded-none h-10 shrink-0 flex-wrap">
            {[
              { v: "ai",     label: "AI Providers" },
              { v: "media",  label: "Media" },
              { v: "github", label: "GitHub" },
              { v: "search", label: "Search" },
              { v: "system", label: "System" },
            ].map(({ v, label }) => (
              <TabsTrigger
                key={v}
                value={v}
                className="font-mono text-[10px] uppercase tracking-wider px-4 h-10 rounded-none border-r border-amk-line data-[state=active]:bg-amk-base data-[state=active]:text-white data-[state=active]:shadow-none text-amk-fg3"
              >
                {label}
              </TabsTrigger>
            ))}
          </TabsList>

          {/* Scrollable tab content */}
          {/* AI Providers tab */}
          <TabsContent value="ai" className="m-0 p-5 space-y-5 overflow-y-auto flex-1 min-h-0">
            {/* GenX (required) */}
            <SettingRow
              fieldKey="GENX_API_KEY"
              label="GenX API Key"
              hint="Required for Amarktai Coding Agents and Amarktai Assistant. This is the only required key."
              optional={false}
              info={state["GENX_API_KEY"] || {}}
              value={values["GENX_API_KEY"]}
              onChange={(v) => setValue("GENX_API_KEY", v)}
              onClear={clear}
              inputType="password"
            />
            {/* Qwen section */}
            <div className="border-t border-amk-line pt-4">
              <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-3">
                // Qwen — optional direct provider
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                {QWEN_FIELDS.map((f) => (
                  <SettingRow
                    key={f.key}
                    fieldKey={f.key}
                    label={f.label}
                    hint={f.hint}
                    optional={true}
                    info={state[f.key] || {}}
                    value={values[f.key]}
                    onChange={(v) => setValue(f.key, v)}
                    onClear={clear}
                    inputType={f.inputType}
                    inputPlaceholder={f.inputPlaceholder}
                  />
                ))}
              </div>
            </div>
          </TabsContent>

          {/* Media tab */}
          <TabsContent value="media" className="m-0 p-5 space-y-4 overflow-y-auto flex-1 min-h-0">
            <SettingRow
              fieldKey="PIXABAY_API_KEY"
              label="Pixabay API Key"
              hint="Optional. Enables stock image and video insertion in generated projects."
              optional={true}
              info={state["PIXABAY_API_KEY"] || {}}
              value={values["PIXABAY_API_KEY"]}
              onChange={(v) => setValue("PIXABAY_API_KEY", v)}
              onClear={clear}
              inputType="password"
            />
            <p className="font-mono text-[10px] text-amk-fg3 leading-relaxed">
              Pixabay provides royalty-free images and videos. Attribution is shown on all Pixabay assets.
              Get a free key at <span className="text-amk-fg">pixabay.com/api/docs</span>.
            </p>
          </TabsContent>

          {/* GitHub tab */}
          <TabsContent value="github" className="m-0 p-5 space-y-4 overflow-y-auto flex-1 min-h-0">
            <SettingRow
              fieldKey="GITHUB_PAT"
              label="GitHub Personal Access Token"
              hint="Optional. Enables private repo import, PRs, and repo creation."
              optional={true}
              info={state["GITHUB_PAT"] || {}}
              value={values["GITHUB_PAT"]}
              onChange={(v) => setValue("GITHUB_PAT", v)}
              onClear={clear}
              inputType="password"
            />
            <GithubStatusBlock github={github} onRefresh={refresh} />
          </TabsContent>

          {/* Search tab */}
          <TabsContent value="search" className="m-0 p-5 space-y-4 overflow-y-auto flex-1 min-h-0">
            <SettingRow
              fieldKey="BRAVE_SEARCH_API_KEY"
              label="Brave Search API Key"
              hint="Optional. Enables live web research for the Scout agent during builds. Without this key, Scout uses model knowledge only."
              optional={true}
              info={state["BRAVE_SEARCH_API_KEY"] || {}}
              value={values["BRAVE_SEARCH_API_KEY"]}
              onChange={(v) => setValue("BRAVE_SEARCH_API_KEY", v)}
              onClear={clear}
              inputType="password"
            />
            <p className="font-mono text-[10px] text-amk-fg3 leading-relaxed">
              Get a free Brave Search API key at <span className="text-amk-fg">search.brave.com/app</span>. Amarktai uses it for research-mode builds and Scout agent context gathering.
            </p>
          </TabsContent>

          {/* System tab */}
          <TabsContent value="system" className="m-0 p-5 space-y-4 overflow-y-auto flex-1 min-h-0">
            <GithubStatusBlock github={github} onRefresh={refresh} showBadge />
            <p className="font-mono text-[10px] text-amk-fg3">
              Secrets are encrypted in MongoDB. Use the refresh button to re-check live provider status.
            </p>
          </TabsContent>
        </Tabs>

        {/* Sticky footer */}
        <DialogFooter className="px-5 pb-5 pt-3 border-t border-amk-line shrink-0">
          <Button data-testid="settings-cancel-btn" variant="ghost" onClick={() => onOpenChange(false)}
            className="font-mono text-xs h-9 hover:bg-amk-surface">Cancel</Button>
          <Button data-testid="settings-save-btn" onClick={save} disabled={saving}
            className="bg-white text-black hover:bg-zinc-200 font-mono text-xs h-9">
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
