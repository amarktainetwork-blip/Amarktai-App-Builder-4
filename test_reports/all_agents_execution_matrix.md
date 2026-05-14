# All Agents Execution Matrix
Generated: 2026-05-14

Branch: `fix/final-runtime-agents-production-completion`

## Runtime Status
- Registered agents audited: 28.
- Active registry entries: 28.
- Hard blockers in this implementation report: 0.
- Silent skips are not treated as success; conditional skips must emit an agent event with the exact reason.

## Implemented Runtime Wiring
- Runtime QA now executes through `runtime_qa_service.run_runtime_qa()` with Playwright Chromium, axe-core browser injection, screenshots, console checks, broken link/media checks, and Lighthouse/browser performance evidence.
- Media Director now uses GenX/Qwen image generation when configured and Pixabay image/video fallback, persists real assets under build storage, writes `media_manifest.json`, and injects assets into generated pages.
- Motion/3D runtime patches generated files, writes `motion_manifest.json`, supports reduced motion, and exposes dashboard evidence.
- Premium gates fail closed on missing runtime QA, missing media, missing motion, malformed Reviewer output, placeholder content, broken assets, template contamination, and fallback-only output.
- Repo Workbench supports repo/branch selection, import, analysis, workflow patch, allowed command execution, diff evidence, PR gating, and PR URL persistence.
- Idea Builder persists conversations, finalizes briefs, and hands mode/tier/media/session context into New Build.

## Agent Table
| Agent | Runtime call site | Output/evidence | Blocks when required |
| --- | --- | --- | --- |
| `manager` | build planner and completion gate | build plan, blocker list, `can_finalize` evidence | yes |
| `prompt_optimizer` | pre-build prompt analysis | prompt quality/enriched context | conditional |
| `product_strategist` / `scout` | `_run_build_pipeline` | requirements, audience, features, mode context | yes |
| `creative_director` | `_run_build_pipeline` | design direction and creative blueprint | yes for premium |
| `ux_architect` / `architect` | `_run_build_pipeline` | file plan, stack plan, preview strategy | yes |
| `ui_designer` | design blueprint/section library | design tokens and layout requirements | yes for premium |
| `frontend_coder` | `_run_agent_blocks("coder")` | generated app files | yes |
| `backend_coder` | full-stack/API/dashboard activation | API/auth/db/env files | yes when mode requires backend |
| `data_architect` | full-stack/API/dashboard activation | schema/API contracts | yes when data layer required |
| `tool_integration` | integration audit pass | env/tool requirements | conditional |
| `component_librarian` | post-coder component audit | component evidence | conditional |
| `media_director` | orchestrator media runtime + `/media-runtime` | persisted assets, `media_manifest.json`, dashboard media evidence | yes for premium/media builds |
| `logo_agent` | logo/media routes and shared context | logo/favicon/brand evidence | conditional |
| `motion_3d` | orchestrator deterministic motion runtime | patched files, `motion_manifest.json`, dashboard motion evidence | yes for premium/motion builds |
| `qa_agent` / `reviewer` | Reviewer audit pass and repair loop | compact JSON audit, issues, surgical patches | yes for premium |
| `visual_qa` | runtime QA screenshots and static visual event | screenshots, console/link/media results | yes for premium |
| `accessibility` | runtime QA axe scan + static scoring | axe violations, accessibility score/report | yes for premium |
| `seo_performance` | quality validator + Lighthouse/performance report | SEO/performance scores and blockers | yes for premium |
| `security` | auth/full-stack security review | security report, high/critical violations | yes when security-required |
| `runtime_engineer` | runtime QA, health, preview validation | runtime report and preview checks | yes for premium |
| `deployment` | deployment validation step | deployment checklist/errors | conditional |
| `documentation` | documentation generator/audit | README/setup/env evidence | conditional |
| `repo_engineer` | repo fix/workbench workflow | repo profile, patch plan, diffs, command logs | yes for repo workflows |
| `repair_agent` | validation repair loop | repair attempts, patched files, failure reasons | yes when validation fails |
| `test_runner` / command runner | build storage command routes | allowed command logs and statuses | yes for repo PR workflow |
| `github_pr_agent` | finalize/open PR route | branch diff, commit, push, PR URL | yes for PR flow |
| `export_agent` | export/download routes | package manifest/download archive | conditional |
| `memory_curator` | memory update/curation | build memory and decisions | conditional |
| `advisor` | post-ready advisor | product recommendations after valid completion | no, runs after gates pass |
| `capability_truth` | readiness/capabilities endpoints | provider/model truth and dashboard labels | yes for build start gates |

## Verification
- `python -m pytest -q`: 801 passed, 2 skipped.
- `cd frontend && npm.cmd test -- --watchAll=false`: 36 passed.
- `cd frontend && npm.cmd run build`: compiled successfully.
