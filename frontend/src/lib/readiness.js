export function readinessBlocksBuild(readiness) {
  const blockers = Array.isArray(readiness?.blockers) ? readiness.blockers : [];
  return readiness?.overall === "FAIL" || blockers.length > 0;
}

export function readinessBlockMessage(readiness) {
  const blockers = Array.isArray(readiness?.blockers) ? readiness.blockers : [];
  return blockers[0] || "Readiness is failing. Check Settings and System before starting agents.";
}
