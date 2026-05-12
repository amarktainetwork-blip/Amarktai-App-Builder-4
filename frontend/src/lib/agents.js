export const AGENTS = {
  planner:   { label: "Planner",   color: "#9C27B0", role: "Build Intelligence" },
  scout:     { label: "Scout",     color: "#FF5722", role: "Research" },
  architect: { label: "Architect", color: "#2962FF", role: "System Design" },
  coder:     { label: "Coder",     color: "#00E676", role: "Implementation" },
  reviewer:  { label: "Reviewer",  color: "#FFC107", role: "QA & Audit" },
  advisor:   { label: "Advisor",   color: "#00BCD4", role: "Product Intelligence" },
  iteration: { label: "Iteration", color: "#FAFAFA", role: "Quick Edit" },
};

export const AGENT_ORDER = ["planner", "scout", "architect", "coder", "reviewer", "advisor"];

export function fileLanguage(path) {
  const ext = (path.split(".").pop() || "").toLowerCase();
  return {
    html: "html", htm: "html",
    css: "css",
    js: "javascript", jsx: "javascript", mjs: "javascript",
    ts: "typescript", tsx: "typescript",
    json: "json",
    md: "markdown",
    py: "python",
  }[ext] || "text";
}
