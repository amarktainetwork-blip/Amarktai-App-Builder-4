import { readinessBlocksBuild } from "./readiness";

test("readiness WARN without blockers allows builds", () => {
  expect(readinessBlocksBuild({ overall: "WARN", blockers: [] })).toBe(false);
});

test("readiness FAIL or blockers stop builds", () => {
  expect(readinessBlocksBuild({ overall: "FAIL", blockers: [] })).toBe(true);
  expect(readinessBlocksBuild({ overall: "WARN", blockers: ["Missing GENX_API_KEY"] })).toBe(true);
});
