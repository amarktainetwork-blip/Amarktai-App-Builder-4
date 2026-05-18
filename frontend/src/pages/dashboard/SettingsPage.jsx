import SettingsPanel from "@/components/SettingsPanel";

export default function SettingsPage() {
  return (
    <section className="min-h-[calc(100vh-9rem)] overflow-hidden rounded-3xl border border-amk-line bg-amk-panel/80 shadow-[0_24px_80px_rgba(0,0,0,.28)]">
      <div className="border-b border-amk-line p-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-accent">Capability Center</div>
        <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-white">Settings and provider truth</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-amk-fg2">
          Configure secrets and review setup-dependent capabilities without turning discovery into false availability.
        </p>
      </div>
      <SettingsPanel active embedded />
    </section>
  );
}
