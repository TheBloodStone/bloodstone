/** Tiny phase tracker — imported by local-node status polling without loading full diagnostics. */

let startingSince = 0;

function syncPhase(status) {
  if (!status) return "idle";
  if (status.chainBootstrapping) return "bootstrap";
  if (status.nodeStarting) {
    const chainBytes = Number(status.chainBytes) || 0;
    if (status.bloodstonedAlive || chainBytes > 512 * 1024) return "loading";
    return "starting";
  }
  if (status.running) return "downloading";
  if (status.syncScheduled || status.batteryDormant) return "scheduled";
  return "idle";
}

export function trackNodePhaseForDiagnostics(status) {
  const phase = syncPhase(status || {});
  if (phase === "starting") {
    if (!startingSince) startingSince = Date.now();
  } else {
    startingSince = 0;
  }
}