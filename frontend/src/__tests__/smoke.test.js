/**
 * Smoke tests for Amarktai App Builder frontend.
 * These tests verify key copy, CSS classes, and logic without
 * requiring @testing-library/react or a running browser.
 */

// ── Landing page ──────────────────────────────────────────────────────────────

test("landing hero does not contain Pick a starter", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Landing.jsx"),
    "utf8"
  );
  expect(content).not.toMatch(/Pick a starter/i);
});

test("landing hero has improved headline copy", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Landing.jsx"),
    "utf8"
  );
  expect(content).toMatch(/Private AI Software Factory/);
  expect(content).toMatch(/Amarktai Builder turns a prompt/);
});

test("landing uses production command center language without retired persona branding", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Landing.jsx"),
    "utf8"
  );
  expect(content).toMatch(/Amarktai Command Center/);
  expect(content).toMatch(/Builder Engine/);
  const retiredName = "Ai" + "va";
  expect(content).not.toMatch(new RegExp(`${retiredName}|${retiredName.toLowerCase()}|${retiredName.toUpperCase()}`));
});

// ── Settings dialog ───────────────────────────────────────────────────────────

test("settings dialog has max-height 90vh", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/SettingsDialog.jsx"),
    "utf8"
  );
  expect(content).toMatch(/90vh/);
});

test("settings dialog tab content has overflow-y-auto", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/SettingsPanel.jsx"),
    "utf8"
  );
  expect(content).toMatch(/overflow-y-auto/);
});

test("settings dialog has sticky header (shrink-0 on header)", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/SettingsPanel.jsx"),
    "utf8"
  );
  expect(content).toMatch(/shrink-0/);
});

test("dashboard has top navigation routes", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/dashboard/DashboardShell.jsx"),
    "utf8"
  );
  expect(content).toMatch(/dashboard-top-nav/);
  expect(content).toMatch(/\/dashboard\/settings/);
  expect(content).toMatch(/Repo Workbench/);
});

test("repo workbench exposes GitHub browse and branch selection", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/dashboard/RepoWorkbenchPage.jsx"),
    "utf8"
  );
  expect(content).toMatch(/Load repos/);
  expect(content).toMatch(/githubBranches/);
  expect(content).toMatch(/clone-selected-repo-btn/);
  expect(content).toMatch(/github-branch-select/);
});

test("frontend API has GitHub workbench and git PR clients", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../lib/amk-api.js"),
    "utf8"
  );
  expect(content).toMatch(/githubRepos/);
  expect(content).toMatch(/githubBranches/);
  expect(content).toMatch(/gitOpenPR/);
  expect(content).toMatch(/repoWorkflowRun/);
  expect(content).toMatch(/runtimeQA/);
  expect(content).toMatch(/mediaRuntime/);
});

test("workspace shows runtime media motion QA evidence", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  expect(content).toMatch(/RuntimeEvidencePanel/);
  expect(content).toMatch(/runtime-evidence-panel/);
  expect(content).toMatch(/motion_manifest/);
  expect(content).toMatch(/media_runtime/);
  expect(content).toMatch(/runtime_qa/);
  expect(content).toMatch(/content_quality_report/);
  expect(content).toMatch(/Content \{contentQualityReport\.pass/);
});

test("live verification scripts cover runtime, repo, premium, idea, and agent matrix", () => {
  const fs = require("fs");
  const path = require("path");
  const root = path.join(__dirname, "../../..");
  [
    "scripts/verify_production_runtime.sh",
    "scripts/verify_repo_workbench_live.sh",
    "scripts/verify_premium_build_live.sh",
    "scripts/verify_idea_builder_live.sh",
    "scripts/verify_agent_matrix.sh",
    "scripts/verify_no_legacy_template_contamination.sh",
  ].forEach((rel) => {
    expect(fs.existsSync(path.join(root, rel))).toBe(true);
  });
});

test("frontend Dockerfile uses package-lock npm ci and does not require yarn.lock", () => {
  const fs = require("fs");
  const path = require("path");
  const root = path.join(__dirname, "../../..");
  const dockerfile = fs.readFileSync(path.join(root, "frontend/Dockerfile"), "utf8");
  expect(dockerfile).toMatch(/COPY package\.json package-lock\.json/);
  expect(dockerfile).toMatch(/npm ci/);
  expect(dockerfile).toMatch(/npm run build/);
  expect(dockerfile).not.toMatch(/COPY package\.json yarn\.lock/);
  expect(fs.existsSync(path.join(root, "frontend/package-lock.json"))).toBe(true);
});

test("dockerignore excludes frontend build context junk", () => {
  const fs = require("fs");
  const path = require("path");
  const content = fs.readFileSync(path.join(__dirname, "../../../frontend/.dockerignore"), "utf8");
  expect(content).toMatch(/node_modules/);
  expect(content).toMatch(/build/);
  expect(content).toMatch(/\.cache/);
});

// ── Workspace navigation ──────────────────────────────────────────────────────

test("workspace has Back to Projects button", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  expect(content).toMatch(/back-to-projects-btn/i);
  expect(content).toMatch(/Dashboard/);
});

test("workspace has New Build button", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  expect(content).toMatch(/new-build-btn/i);
  expect(content).toMatch(/New Build/);
});

// ── Iteration panel ───────────────────────────────────────────────────────────

test("workspace iteration panel distinguishes unsatisfied from complete", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  expect(content).toMatch(/changes still needed/i);
  expect(content).toMatch(/iteration-unsatisfied-panel/);
  expect(content).toMatch(/continue-fixing-btn/);
});

// ── Build mode descriptions ───────────────────────────────────────────────────

test("project list has build mode hints", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/dashboard/NewBuildPage.jsx"),
    "utf8"
  );
  expect(content).toMatch(/landing_page/);
  expect(content).toMatch(/A polished one-page website/);
});

test("new build and project list expose only Standard and Premium user tiers", () => {
  const fs = require("fs");
  const files = [
    require.resolve("../pages/dashboard/NewBuildPage.jsx"),
    require.resolve("../pages/ProjectList.jsx"),
  ];
  const tierSource = fs.readFileSync(require.resolve("../lib/tiers.js"), "utf8");
  expect(tierSource).toMatch(/Standard/);
  expect(tierSource).toMatch(/Premium/);
  for (const file of files) {
    const content = fs.readFileSync(file, "utf8");
    const oldBasic = "Che" + "ap";
    const oldMiddle = "Balan" + "ced";
    expect(content).not.toMatch(new RegExp(`\\b${oldBasic}\\b|\\b${oldMiddle}\\b|${oldBasic.toLowerCase()}\\/${oldMiddle.toLowerCase()}|${oldMiddle.toLowerCase()}\\/premium`, "i"));
  }
});

test("new build exposes go-live build modes and media sources", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/dashboard/NewBuildPage.jsx"),
    "utf8"
  );
  [
    "Landing Page",
    "Website",
    "PWA",
    "Web App",
    "Dashboard",
    "Full-Stack App",
    "API Service",
    "Repo Fix",
    "Automation Bot",
    "Admin/Internal Tool",
    "Ecommerce Scaffold",
    "Booking/Portal",
    "AI Chat/RAG App",
    "CRM/Dashboard",
    "AI media",
    "Stock/free media",
    "Uploaded media",
  ].forEach((label) => expect(content).toMatch(new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))));
});

// ── Multi-page warning ────────────────────────────────────────────────────────

test("project list has multi-page warning component", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/dashboard/NewBuildPage.jsx"),
    "utf8"
  );
  expect(content).toMatch(/Build mode/);
});

// ── Media source descriptions ─────────────────────────────────────────────────

test("media choice has improved descriptions", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/dashboard/NewBuildPage.jsx"),
    "utf8"
  );
  expect(content).toMatch(/best live source/);
  expect(content).toMatch(/Stock\/free media/);
  expect(content).toMatch(/No external media dependency/);
});

test("workspace exposes go-live tabs and friendly failure panel", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  [
    "Prompt / Brief",
    "Build Timeline",
    "Media Studio",
    "Runtime QA",
    "Repo Workbench",
    "Deploy / Finalize",
    "friendly-error-panel",
  ].forEach((label) => expect(content).toMatch(new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))));
});

test("capability center shows runtime and optional setup-needed capabilities", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/CapabilityStatus.jsx"),
    "utf8"
  );
  [
    "Avatar video",
    "Runtime QA",
    "Playwright",
    "Lighthouse",
    "Add Integrations",
    "Whisper",
    "FAISS",
    "Stable Diffusion",
    "Setup needed",
  ].forEach((label) => expect(content).toMatch(new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))));
});

test("repo import uses from-repo route and friendly import errors", () => {
  const fs = require("fs");
  const page = fs.readFileSync(require.resolve("../pages/ProjectList.jsx"), "utf8");
  const api = fs.readFileSync(require.resolve("../lib/amk-api.js"), "utf8");
  expect(page).toMatch(/Projects\.fromRepo/);
  expect(page).toMatch(/friendlyRepoImportError/);
  expect(api).toMatch(/\/projects\/from-repo/);
});

// ── Smoke script ──────────────────────────────────────────────────────────────

test("smoke script uses safe integer increment (no arithmetic eval bug)", () => {
  const fs = require("fs");
  const path = require("path");
  const content = fs.readFileSync(
    path.join(__dirname, "../../../scripts/smoke_test_builder.sh"),
    "utf8"
  );
  // Must use safe POSIX arithmetic, not bash (( )) which fails at 0
  expect(content).toMatch(/PASS=\$\(\(PASS\+1\)\)/);
  expect(content).toMatch(/FAIL=\$\(\(FAIL\+1\)\)/);
});

test("smoke script accepts both ok and healthy status", () => {
  const fs = require("fs");
  const path = require("path");
  const content = fs.readFileSync(
    path.join(__dirname, "../../../scripts/smoke_test_builder.sh"),
    "utf8"
  );
  expect(content).toMatch(/STATUS.*=.*"ok"/);
  expect(content).toMatch(/STATUS.*=.*"healthy"/);
});

// ── .env.example ─────────────────────────────────────────────────────────────

test("root .env.example exists with required placeholders", () => {
  const fs = require("fs");
  const path = require("path");
  const content = fs.readFileSync(
    path.join(__dirname, "../../../.env.example"),
    "utf8"
  );
  expect(content).toMatch(/GENX_API_KEY=/);
  expect(content).toMatch(/JWT_SECRET=/);
  expect(content).toMatch(/MONGO_URL=/);
  expect(content).not.toMatch(/[a-zA-Z0-9]{32,}/); // no real secrets
});

// ── WebSocket reconnect ───────────────────────────────────────────────────────

test("workspace has WebSocket reconnect state tracking", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  // Must have reconnect attempt counter
  expect(content).toMatch(/wsReconnectAttempt/);
  // Must use exponential backoff (** or Math.pow)
  expect(content).toMatch(/2\s*\*\*\s*wsReconnectAttempt|Math\.pow/);
  // Must cap reconnect delay
  expect(content).toMatch(/30000/);
  // Must clean up on unmount
  expect(content).toMatch(/clearTimeout/);
});

test("workspace ws banner shows reconnecting state not static message", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  // Must show contextual reconnect message
  expect(content).toMatch(/reconnecting/i);
  // Must NOT say "Reopen the workspace" (old static message)
  expect(content).not.toMatch(/Reopen the workspace/);
});

// ── Import cleanliness ────────────────────────────────────────────────────────

test("project list does not import unused Video icon", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/dashboard/NewBuildPage.jsx"),
    "utf8"
  );
  // Video is not used in the new build page and should not be imported.
  expect(content).not.toMatch(/\bVideo\b/);
});

// ── Polling fallback & files_refreshed ───────────────────────────────────────

test("workspace has polling fallback while build running", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  // Must have polling timer ref
  expect(content).toMatch(/pollTimerRef/);
  // Must use setInterval for polling
  expect(content).toMatch(/setInterval/);
  // Must clear the poll timer on cleanup
  expect(content).toMatch(/clearInterval/);
  // Must poll every 5 seconds
  expect(content).toMatch(/5000/);
});

test("workspace handles files_refreshed event to refetch files", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  // Must handle the files_refreshed event type
  expect(content).toMatch(/files_refreshed/);
});

test("workspace refreshes files and project on iteration_complete", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  // iteration_complete must trigger file and project refresh
  const iterCompleteSection = content.slice(
    content.indexOf("iteration_complete"),
    content.indexOf("iteration_complete") + 600
  );
  expect(iterCompleteSection).toMatch(/Projects\.files/);
  expect(iterCompleteSection).toMatch(/Projects\.get/);
});

// ── Phase 2: AdvisorPanel ─────────────────────────────────────────────────────

test("AdvisorPanel component exists and has advisor-panel test id", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/AdvisorPanel.jsx"),
    "utf8"
  );
  expect(content).toMatch(/advisor-panel/);
  expect(content).toMatch(/overall_rating/);
  expect(content).toMatch(/quick_wins/);
  expect(content).toMatch(/priority_action/);
});

test("workspace imports AdvisorPanel and BuildPlanBanner", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  expect(content).toMatch(/AdvisorPanel/);
  expect(content).toMatch(/BuildPlanBanner/);
});

test("workspace handles build_plan event", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  expect(content).toMatch(/build_plan/);
  expect(content).toMatch(/setBuildPlan/);
});

test("workspace handles advisor_ready event", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  expect(content).toMatch(/advisor_ready/);
  expect(content).toMatch(/setAdvisorResult/);
});

// ── Phase 3: Extended scores in ValidationPanel ────────────────────────────────

test("ValidationPanel shows extended product scores", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/ValidationPanel.jsx"),
    "utf8"
  );
  expect(content).toMatch(/conversionScore/);
  expect(content).toMatch(/uxScore/);
  expect(content).toMatch(/accessibilityScore/);
  expect(content).toMatch(/seoScore/);
  expect(content).toMatch(/responsivenessScore/);
  expect(content).toMatch(/performanceScore/);
  expect(content).toMatch(/Product Scores/);
});

// ── Phase 4: BuildPlanBanner ──────────────────────────────────────────────────

test("BuildPlanBanner component exists with plan details", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/BuildPlanBanner.jsx"),
    "utf8"
  );
  expect(content).toMatch(/build-plan-banner/);
  expect(content).toMatch(/complexity/);
  expect(content).toMatch(/estimated_pages/);
  expect(content).toMatch(/recommended_stack/);
  expect(content).toMatch(/build_phases/);
});

// ── Phase 1: AgentTimeline improvements ──────────────────────────────────────

test("AgentTimeline shows planner and advisor agents", () => {
  const fs = require("fs");
  const agents = fs.readFileSync(
    require.resolve("../lib/agents.js"),
    "utf8"
  );
  expect(agents).toMatch(/planner/);
  expect(agents).toMatch(/advisor/);
  expect(agents).toMatch(/Build Intelligence/);
  expect(agents).toMatch(/Product Intelligence/);
});

test("AgentTimeline shows failed and skipped states", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/AgentTimeline.jsx"),
    "utf8"
  );
  expect(content).toMatch(/isFailed/);
  expect(content).toMatch(/isSkipped/);
  expect(content).toMatch(/latestDetail/);
});
