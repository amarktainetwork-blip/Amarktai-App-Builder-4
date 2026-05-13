import { Dialog, DialogContent } from "@/components/ui/dialog";
import SettingsPanel from "@/components/SettingsPanel";

export default function SettingsDialog({ open, onOpenChange }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="settings-dialog"
        className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-md border border-amk-line bg-amk-panel p-0 text-amk-fg"
      >
        <SettingsPanel active={open} embedded onClose={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
