/** #99 — pull-to-refresh resistance math, per design-system.md (Pull-to-Refresh · Briefing).
 *  Threshold 60px (on the resisted offset), rubber-band `Math.min(distance * 0.4, 80)`. */
export const PULL_THRESHOLD = 60;
export const PULL_RESISTANCE = 0.4;
export const PULL_CAP = 80;

/** Resisted (rubber-band) offset for a raw downward pull distance. Negatives clamp to 0. */
export function pullOffset(distance: number): number {
  if (distance <= 0) return 0;
  return Math.min(distance * PULL_RESISTANCE, PULL_CAP);
}

/** Whether a given resisted offset has crossed the refresh threshold. */
export function pullTriggersRefresh(offset: number): boolean {
  return offset >= PULL_THRESHOLD;
}
