export const QUALITY_TIERS = [
  {
    id: "standard",
    label: "Standard",
    description: "Fast, capable generation using efficient high-quality models.",
  },
  {
    id: "premium",
    label: "Premium",
    description: "Best available models, deeper reasoning, richer media, stronger QA.",
  },
];

export function normalizeQualityTier(value) {
  const raw = String(value || "standard").toLowerCase();
  if (raw === "premium") return "premium";
  return "standard";
}

export function tierLabel(value) {
  return normalizeQualityTier(value) === "premium" ? "Premium" : "Standard";
}
