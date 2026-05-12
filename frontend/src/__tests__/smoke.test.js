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
  expect(content).toMatch(/Build websites, apps/);
  expect(content).toMatch(/GitHub-ready/);
});

test("landing imports Cpu icon", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Landing.jsx"),
    "utf8"
  );
  expect(content).toMatch(/Cpu/);
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
    require.resolve("../components/SettingsDialog.jsx"),
    "utf8"
  );
  expect(content).toMatch(/overflow-y-auto/);
});

test("settings dialog has sticky header (shrink-0 on header)", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../components/SettingsDialog.jsx"),
    "utf8"
  );
  expect(content).toMatch(/shrink-0/);
});

// ── Workspace navigation ──────────────────────────────────────────────────────

test("workspace has Back to Projects button", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/Workspace.jsx"),
    "utf8"
  );
  expect(content).toMatch(/back-to-projects-btn/i);
  expect(content).toMatch(/Projects/);
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
    require.resolve("../pages/ProjectList.jsx"),
    "utf8"
  );
  expect(content).toMatch(/build-mode-hint/);
  expect(content).toMatch(/landing_page/);
  expect(content).toMatch(/A single polished page/);
});

// ── Multi-page warning ────────────────────────────────────────────────────────

test("project list has multi-page warning component", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/ProjectList.jsx"),
    "utf8"
  );
  expect(content).toMatch(/multi-page-warning/);
  expect(content).toMatch(/MULTI_PAGE_PATTERN/);
});

// ── Media source descriptions ─────────────────────────────────────────────────

test("media choice has improved descriptions", () => {
  const fs = require("fs");
  const content = fs.readFileSync(
    require.resolve("../pages/ProjectList.jsx"),
    "utf8"
  );
  expect(content).toMatch(/Use the best available source/);
  expect(content).toMatch(/Requires Pixabay API key/);
  expect(content).toMatch(/No external images/);
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
    require.resolve("../pages/ProjectList.jsx"),
    "utf8"
  );
  // Video is not used anywhere in ProjectList — should not be imported
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

