/** #104 — percentage-based discover-swipe commit thresholds (design-system.md: landscape/orientation).
 *  Horizontal commit at 40% of viewport width, vertical (up = save) at 25% of card height — so the
 *  card commits proportionally in any orientation instead of at fixed pixels. */
export const SWIPE_X_RATIO = 0.4;
export const SWIPE_Y_RATIO = 0.25;

export function swipeThresholds(width: number, height: number): { x: number; y: number } {
  return {
    x: Math.round(Math.max(0, width) * SWIPE_X_RATIO),
    y: -Math.round(Math.max(0, height) * SWIPE_Y_RATIO), // up is negative
  };
}
