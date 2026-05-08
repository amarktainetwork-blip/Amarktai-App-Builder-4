import { useEffect, useState } from "react";
import { Settings as SettingsApi } from "@/lib/emergent-api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

const FIELDS = [
  { key: "EMERGENT_LLM_KEY",      label: "Emergent LLM Key",  hint: "Universal key for OpenAI / Anthropic / Gemini." },
  { key: "WEBCONTAINER_API_KEY",  label: "WebContainer Key",  hint: "StackBlitz WebContainer (placeholder for now)." },
  { key: "GITHUB_PAT",            label: "GitHub PAT",        hint: "Personal Access Token with repo scope." },
  { key: "BRAVE_SEARCH_API_KEY",  label: "Brave Search Key",  hint: "For the Scout agent's web research." },
];

export default function SettingsDialog({ open, onOpenChange }) {
  const [state, setState] = useState({});
  const [values, setValues] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) SettingsApi.get().then(setState);
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
        const fresh = await SettingsApi.get();
        setState(fresh);
        setValues({});
      }
    } catch (e) {
      toast.error("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="settings-dialog"
        className="bg-emergent-panel border border-emergent-line text-emergent-fg max-w-lg p-0 rounded-md"
      >
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-emergent-line">
          <DialogTitle className="font-mono text-sm tracking-tight uppercase">
            // API Keys
          </DialogTitle>
          <DialogDescription className="font-mono text-[11px] text-emergent-fg3">
            Configure provider keys. Empty fields fall back to mocks.
          </DialogDescription>
        </DialogHeader>
        <div className="p-5 space-y-4">
          {FIELDS.map((f) => {
            const isSet = state[f.key]?.set;
            return (
              <div key={f.key} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label className="font-mono text-xs tracking-tight">{f.label}</Label>
                  <span
                    data-testid={`setting-status-${f.key}`}
                    className="font-mono text-[10px] uppercase tracking-wider inline-flex items-center gap-1"
                    style={{ color: isSet ? "#00E676" : "#71717A" }}
                  >
                    {isSet ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
                    {isSet ? `set · ${state[f.key].preview}` : "not set"}
                  </span>
                </div>
                <Input
                  data-testid={`setting-input-${f.key}`}
                  type="password"
                  placeholder={isSet ? "Replace value..." : "Paste key..."}
                  value={values[f.key] || ""}
                  onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                  className="bg-emergent-base border-emergent-line text-emergent-fg font-mono text-xs h-9 focus-visible:ring-0 focus-visible:border-white"
                />
                <p className="font-mono text-[10px] text-emergent-fg3">{f.hint}</p>
              </div>
            );
          })}
        </div>
        <DialogFooter className="px-5 pb-5 pt-2 border-t border-emergent-line">
          <Button
            data-testid="settings-cancel-btn"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            className="font-mono text-xs h-9 hover:bg-emergent-surface"
          >
            Cancel
          </Button>
          <Button
            data-testid="settings-save-btn"
            onClick={save}
            disabled={saving}
            className="bg-white text-black hover:bg-zinc-200 font-mono text-xs h-9"
          >
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
