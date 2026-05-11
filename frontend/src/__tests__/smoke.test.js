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
