import SettingsPanel from "@/components/SettingsPanel";

export default function SettingsPage() {
  return (
    <section className="min-h-[calc(100vh-9rem)] overflow-hidden border border-amk-line bg-amk-panel">
      <SettingsPanel active embedded />
    </section>
  );
}
