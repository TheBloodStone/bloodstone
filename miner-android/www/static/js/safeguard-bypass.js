/**
 * Session override — "Just mine" bypasses power, battery, and thermal safeguards.
 */

let justMineActive = false;

export function isJustMineActive() {
  return justMineActive;
}

export function setJustMineActive(active) {
  justMineActive = Boolean(active);
  return justMineActive;
}

export function isSafeguardBypassed() {
  return justMineActive;
}