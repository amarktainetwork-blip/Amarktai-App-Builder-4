export const AGENTS = {
  scout:     { label: "Scout",     color: "#FF5722", role: "Research" },
  architect: { label: "Architect", color: "#2962FF", role: "System Design" },
  coder:     { label: "Coder",     color: "#00E676", role: "Implementation" },
  reviewer:  { label: "Reviewer",  color: "#FFC107", role: "QA & Audit" },
  iteration: { label: "Iteration", color: "#FAFAFA", role: "Quick Edit" },
};

export const AGENT_ORDER = ["scout", "architect", "coder", "reviewer"];

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
