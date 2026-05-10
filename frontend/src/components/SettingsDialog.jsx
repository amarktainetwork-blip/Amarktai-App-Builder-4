import { useEffect, useState } from "react";
import { Settings as SettingsApi, System } from "@/lib/amk-api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Check, X, Trash2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const FIELDS = [
  { key: "GENX_API_KEY", label: "GenX API Key", hint: "Required for Amarktai Coding Agents and Amarktai Assistant." },
  { key: "GITHUB_PAT", label: "GitHub PAT", hint: "Optional. Enables private repo import, PRs, and repo creation." },
  { key: "BRAVE_SEARCH_API_KEY", label: "Brave Search Key", hint: "Optional. Enables web research for Scout." },
];

export default function SettingsDialog({ open, onOpenChange }) {
  const [state, setState] = useState({});
  const [values, setValues] = useState({});
  const [github, setGithub] = useState(null);
  const [saving, setSaving] = useState(false);

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
      <DialogContent data-testid="settings-dialog" className="bg-amk-panel border border-amk-line text-amk-fg max-w-lg p-0 rounded-md">
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-amk-line">
          <DialogTitle className="font-mono text-sm tracking-tight uppercase">// Settings / Integrations</DialogTitle>
          <DialogDescription className="font-mono text-[11px] text-amk-fg3">
            Secrets are encrypted in MongoDB. Environment variables are used only when no saved value exists.
          </DialogDescription>
        </DialogHeader>
        <div className="p-5 space-y-4">
          {FIELDS.map((f) => {
            const info = state[f.key] || {};
            const isSet = !!info.configured;
            return (
              <div key={f.key} className="space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                  <Label className="font-mono text-xs tracking-tight">{f.label}</Label>
                  <span
                    data-testid={`setting-status-${f.key}`}
                    className="font-mono text-[10px] uppercase tracking-wider inline-flex items-center gap-1"
                    style={{ color: isSet ? "#00E676" : "#FF5722" }}
                  >
                    {isSet ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
                    {isSet ? `${info.source || "set"} / ${info.preview}` : "not configured"}
                  </span>
                </div>
                <div className="flex gap-2">
                  <Input
                    data-testid={`setting-input-${f.key}`}
                    type="password"
                    placeholder={isSet ? "Replace value..." : "Paste key..."}
                    value={values[f.key] || ""}
                    onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                    className="bg-amk-base border-amk-line text-amk-fg font-mono text-xs h-9 focus-visible:ring-0 focus-visible:border-white"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={!isSet || info.source === "env"}
                    onClick={() => clear(f.key)}
                    title={info.source === "env" ? "Environment values must be removed on the server" : "Clear saved value"}
                    className="h-9 px-2 border border-amk-line"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
                <p className="font-mono text-[10px] text-amk-fg3">{f.hint}</p>
              </div>
            );
          })}
          <div className="border border-amk-line bg-amk-base p-3">
            <div className="flex items-center justify-between">
              <div className="font-mono text-xs text-amk-fg">GitHub status</div>
              <Button type="button" variant="ghost" size="sm" onClick={refresh} className="h-7 px-2">
                <RefreshCw className="w-3 h-3" />
              </Button>
            </div>
            <p className="mt-1 font-mono text-[10px] text-amk-fg3">
              {github?.detail || "GitHub status has not been checked yet."}
            </p>
          </div>
        </div>
        <DialogFooter className="px-5 pb-5 pt-2 border-t border-amk-line">
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
